"""
mascot_ui.py — обёртка над AnkiWebView, генерация HTML, привязка изображений
(раздел 4 ТЗ), обработка pycmd-команд.

Реализует диалоговое окно в стиле комикса:
  - закруглённый спич-бабл с текстом,
  - изображение персонажа Anker снизу слева,
  - 2-4 кнопки выбора под текстом.

Изображения загружаются из папки assets/ через file:// URL.
Никаких внешних CDN/шрифтов/скриптов — всё офлайн.
"""

from typing import Any, Callable, Dict, List

from .html_builder import (
    build_dialog_html,
    build_day_picker_html,
    build_stats_tabbed_html,
    build_sparkline_svg,
    compute_summary_score,
    summary_image_for_score,
    DEFAULT_THEME_COLORS,
    _retention_explanation,
    _again_rate_explanation,
    _difficulty_explanation,
)
from . import log

try:
    from aqt import mw
    from aqt.qt import (
        QDialog,
        QVBoxLayout,
        Qt,
        QSizePolicy,
    )
    from aqt.webview import AnkiWebView
    _ANKI_AVAILABLE = True
except ImportError:
    _ANKI_AVAILABLE = False
    # Заглушки для импорта вне Anki (например, в тестах)
    QDialog = object
    QVBoxLayout = object
    Qt = object
    QSizePolicy = object
    AnkiWebView = object
    mw = None


# ── Цвета темы Anki ────────────────────────────────────────────────────────

def _get_theme_colors() -> Dict[str, str]:
    """
    Получает актуальные цвета текущей темы Anki (светлой/тёмной),
    чтобы диалог Anker визуально не выбивался из интерфейса.

    Использует QPalette — низкоуровневое Qt API, не зависящее от
    специфичных для Anki именованных цветов, которые могут отличаться
    между версиями. При недоступности возвращает светлую палитру.
    """
    try:
        from aqt.qt import QPalette
        palette = mw.app.palette()
        bg = palette.color(QPalette.ColorRole.Window).name()
        text = palette.color(QPalette.ColorRole.WindowText).name()
        border = palette.color(QPalette.ColorRole.Mid).name()
        frame_bg = palette.color(QPalette.ColorRole.Base).name()

        colors = {
            "bg": bg,
            "frame_bg": frame_bg,
            "text": text,
            "border": border,
            "btn_hover": "rgba(128,128,128,0.15)",
            "btn_active": "rgba(128,128,128,0.25)",
        }

        # DEBUG: выводим реальные цвета при первом открытии диалога,
        # чтобы диагностировать расхождения на машине пользователя.
        try:
            from aqt.utils import tooltip
            tooltip(
                f"Anker theme: bg={bg} text={text} border={border} frame={frame_bg}",
                period=3000,
            )
        except Exception:
            pass

        return colors
    except Exception as e:
        log.log_error("_get_theme_colors", e)
        return dict(DEFAULT_THEME_COLORS)


# ── Константы изображений по сценариям ─────────────────────────────────────

IMG_NEUTRAL = "neutral.png"
IMG_WORRIED = "worried.png"
IMG_UNDERSTANDING = "understanding.png"
IMG_SAD = "sad.png"
IMG_ENTHUSIASTIC = "enthusiastic.png"
IMG_PROUDED = "prouded.png"


# ── Фиксированные размеры окон (пункт 1 ТЗ) ────────────────────────────────

# Размеры подобраны под самый длинный реалистичный контент каждого типа
# (с учётом увеличенных кнопок из пункта 5 ТЗ). Окно каждого типа всегда
# открывается строго одного размера — без динамического измерения высоты.
DIALOG_SIZE = (460, 440)      # обычный диалог (сообщение + до 4 кнопок)
STATS_SIZE = (760, 700)       # экран статистики (любая из трёх вкладок)
DAY_PICKER_SIZE = (460, 340)  # диалог выбора дней недели


# ── Класс диалога ──────────────────────────────────────────────────────────

class MascotDialog(QDialog):
    """
    Модальное диалоговое окно с маскотом Anker.

    Поддерживает кнопку «Моя статистика» — при нажатии заменяет содержимое
    на экран статистики с вкладками, без закрытия диалога.
    Кнопка «Назад» возвращает к основному сообщению.

    Размер окна строго фиксирован: 460×440 для обычного диалога и 560×520
    для экрана статистики. Высота не измеряется динамически.
    """

    def __init__(
        self,
        image_filename: str,
        message: str,
        buttons: List[Dict[str, str]],
        on_action: Callable[[str], None],
        parent=None,
        stats_context: Dict[str, Any] | None = None,
    ):
        """
        Args:
            image_filename: имя файла изображения (например, "neutral.png").
            message: текст в спич-бабле.
            buttons: список кнопок (см. html_builder.build_buttons_html).
            on_action: callback при нажатии кнопки, получает action-строку.
            stats_context: данные для экрана «Моя статистика» (метрики, решение).
        """
        super().__init__(parent or mw)
        self._on_action = on_action
        self._stats_context = stats_context
        self._colors = _get_theme_colors()

        # Имя колоды и период анализа — для подписей кнопки статистики
        # и заголовка экрана статистики.
        self._deck_name = (stats_context or {}).get("deck_name")
        self._period = (stats_context or {}).get("period")

        # Сохраняем параметры для восстановления после экрана статистики
        self._main_image = image_filename
        self._main_message = message
        self._main_buttons = buttons
        self._active_stats_tab = "summary"
        self._is_stats_screen = False

        self.setWindowTitle("Anker")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(f"QDialog {{ background-color: {self._colors['bg']}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.webview = AnkiWebView()
        self.webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.webview.set_bridge_command(self._handle_pycmd, self)
        self.webview.page().setBackgroundColor(Qt.GlobalColor.transparent)

        layout.addWidget(self.webview)
        self._show_main()

    def _render_html(self, html: str) -> None:
        """
        Загружает новый HTML с явным сбросом DOM. setHtml("") гарантирует
        полную замену страницы, а не наложение поверх предыдущего состояния,
        что предотвращает накопительный рост scrollHeight между рендерами.
        """
        self.webview.page().setHtml("")
        self.webview.stdHtml(html)

    def _show_main(self) -> None:
        """Показывает основной экран диалога."""
        self._is_stats_screen = False
        html = build_dialog_html(
            self._main_image,
            self._main_message,
            self._main_buttons,
            self._colors,
            deck_name=self._deck_name,
            period=self._period,
        )
        self._render_html(html)
        self._apply_fixed_size()

    def _show_stats(self, tab: str = "summary") -> None:
        """Показывает экран статистики с вкладками «Итог» / «Главное» / «Все показатели»."""
        self._is_stats_screen = True
        self._active_stats_tab = tab
        ctx = self._stats_context or {}
        metrics = ctx.get("metrics", {})
        decision_action = ctx.get("decision_action", "hold")
        is_anomaly = ctx.get("is_anomaly", False)
        is_stable = ctx.get("is_stable", False)

        # Выбираем изображение: на вкладке «Итог» — по самой оценке,
        # на остальных вкладках — по решению движка / характеру данных.
        if tab == "summary":
            score = compute_summary_score(metrics, ctx.get("metric_weights"))
            image = summary_image_for_score(score)
        elif decision_action == "decrease":
            image = IMG_SAD
        elif decision_action == "increase":
            image = IMG_ENTHUSIASTIC
        elif is_anomaly:
            image = IMG_WORRIED
        elif is_stable:
            image = IMG_PROUDED
        else:
            image = IMG_NEUTRAL

        html = build_stats_tabbed_html(
            metrics=metrics,
            decision_action=decision_action,
            is_anomaly=is_anomaly,
            is_stable=is_stable,
            active_tab=tab,
            image_filename=image,
            theme_colors=self._colors,
            metric_weights=ctx.get("metric_weights"),
            last_summary_score=ctx.get("last_summary_score"),
            deck_name=self._deck_name,
            period=self._period,
        )
        self._render_html(html)
        self._apply_fixed_size()

    def _apply_fixed_size(self) -> None:
        """Применяет фиксированный размер окна для текущего экрана."""
        width, height = STATS_SIZE if self._is_stats_screen else DIALOG_SIZE
        self.setFixedSize(width, height)
        self._center_on_parent()

    def _center_on_parent(self) -> None:
        """Центрирует окно относительно главного окна Anki."""
        if mw is not None:
            try:
                parent_geo = mw.geometry()
                x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
                y = parent_geo.y() + (parent_geo.height() - self.height()) // 2
                self.move(max(0, x), max(0, y))
            except Exception:
                pass

    def _handle_pycmd(self, cmd: str) -> None:
        """Обрабатывает pycmd-команды от кнопок."""
        if cmd.startswith("anker:"):
            action = cmd[len("anker:"):]
            if action == "show_stats":
                self._show_stats("summary")
                return
            if action == "stats_tab_summary":
                self._show_stats("summary")
                return
            if action == "stats_tab_main":
                self._show_stats("main")
                return
            if action == "stats_tab_all":
                self._show_stats("all")
                return
            if action == "stats_back":
                self._show_main()
                return
            self._on_action(action)
            self.accept()


# ── Фабрики диалогов по сценариям ──────────────────────────────────────────

def show_planned_visit(
    decision: Any,
    deck_name: str,
    on_action: Callable[[str], None],
    stats_context: Dict[str, Any] | None = None,
) -> None:
    """
    Показывает плановый визит маскота.

    Выбор ветки привязан к decision.action:
      - action == "increase" → enthusiastic.png
      - action == "decrease" → understanding.png
      - action == "hold" + is_stable_streak → prouded.png
      - action == "hold" иначе → neutral.png
    """
    is_stable = decision.is_stable_streak

    if decision.action == "increase":
        image = IMG_ENTHUSIASTIC
        message = (
            f"Ты уверенно справляешься с колодой «{deck_name}» — "
            f"можно немного ускориться и добавить новых карточек."
        )
        buttons = [
            {"label": "Да, давай увеличим", "action": "increase_accept", "primary": True},
            {"label": "Пока оставим как есть", "action": "increase_decline"},
        ]
    elif decision.action == "decrease":
        image = IMG_UNDERSTANDING
        message = (
            f"Тебе в последнее время нелегко даются повторения колоды «{deck_name}». "
            f"Есть смысл ненадолго снизить количество новых карточек, "
            f"чтобы закрепить то, что уже выучено."
        )
        buttons = [
            {"label": "Да, давай снизим", "action": "decrease_accept", "primary": True},
            {"label": "Нет, я справлюсь", "action": "decrease_decline"},
        ]
    elif is_stable:
        image = IMG_PROUDED
        message = (
            f"Ты стабильно хорошо закрепляешь материал колоды «{deck_name}» — "
            f"и уже не первую неделю. Не расслабляйся, но темп отличный!"
        )
        buttons = [
            {"label": "Спасибо!", "action": "prouded_ack", "primary": True},
        ]
    else:
        image = IMG_NEUTRAL
        message = (
            f"У тебя всё ровно с колодой «{deck_name}» — продолжай в своём темпе."
        )
        buttons = [
            {"label": "Хорошо", "action": "neutral_ack", "primary": True},
        ]

    dialog = MascotDialog(image, message, buttons, on_action, stats_context=stats_context)
    dialog.exec()


def show_anomaly_checkin(
    deck_name: str,
    on_action: Callable[[str], None],
    stats_context: Dict[str, Any] | None = None,
) -> None:
    """Показывает anomaly check-in диалог. Изображение: worried.png."""
    image = IMG_WORRIED
    message = (
        f"Сегодня тебе явно тяжелее обычного даётся «{deck_name}». Что случилось?"
    )
    buttons = [
        {"label": "Лень / не хочется", "action": "anomaly_lazy"},
        {"label": "Занят(а) сегодня", "action": "anomaly_busy"},
        {"label": "Само пройдёт", "action": "anomaly_dismiss", "primary": True},
    ]
    dialog = MascotDialog(image, message, buttons, on_action, stats_context=stats_context)
    dialog.exec()


def show_anomaly_lazy(
    deck_name: str,
    on_action: Callable[[str], None],
) -> None:
    """Реакция на «Лень / не хочется»: sad.png, предложение лёгкого режима."""
    image = IMG_SAD
    message = (
        f"Бывает у всех, не переживай. Давай включим для тебя временный лёгкий "
        f"режим по «{deck_name}» — я ненадолго снижу количество новых карточек, "
        f"а потом всё вернётся как было."
    )
    buttons = [
        {"label": "Лёгкий режим на 3 дня", "action": "light_3d", "primary": True},
        {"label": "Лёгкий режим на 5 дней", "action": "light_5d"},
        {"label": "Лёгкий режим на 7 дней", "action": "light_7d"},
        {"label": "Не надо, я в порядке", "action": "light_decline"},
    ]
    dialog = MascotDialog(image, message, buttons, on_action)
    dialog.exec()


def show_anomaly_busy(
    deck_name: str,
    on_action: Callable[[str], None],
) -> None:
    """Реакция на «Занят(а) сегодня»: understanding.png, выбор дней недели."""
    image = IMG_UNDERSTANDING
    message = (
        f"Понимаю, бывают такие дни. Хочешь, я настрою для тебя дни недели "
        f"без новых карточек по «{deck_name}»?"
    )
    buttons = [
        {"label": "Настроить дни недели", "action": "busy_setup_days", "primary": True},
        {"label": "Не сегодня", "action": "busy_dismiss"},
    ]
    dialog = MascotDialog(image, message, buttons, on_action)
    dialog.exec()


def show_day_of_week_picker(
    current_rules: Dict[int, float],
    deck_name: str,
    on_action: Callable[[str], None],
    on_done: Callable[[], None],
) -> None:
    """
    Показывает диалог выбора дней недели для повторяющегося снижения нагрузки.

    current_rules: {weekday: multiplier, ...}, weekday 1=Пн..7=Вс.
    """
    normalized_rules: Dict[int, float] = {}
    for k, v in current_rules.items():
        normalized_rules[int(k)] = v

    image = IMG_NEUTRAL
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    checkboxes_html = ""
    for i, name in enumerate(day_names, 1):
        checked = "checked" if i in normalized_rules else ""
        checkboxes_html += (
            f'<label style="display:inline-block;margin:4px 8px;cursor:pointer;">'
            f'<input type="checkbox" id="day_{i}" {checked} '
            f'onchange="pycmd(\'anker:day_toggle_{i}:\' + this.checked)"> '
            f'{name}</label>'
        )

    message = (
        f"В какие дни тебе обычно не до новых карточек по «{deck_name}»? "
        f"Отметь их — я подстроюсь."
    )

    colors = _get_theme_colors()
    html = build_day_picker_html(image, message, checkboxes_html, colors)

    dialog = QDialog(mw)
    dialog.setWindowTitle("Anker — дни недели")
    dialog.setFixedSize(*DAY_PICKER_SIZE)
    dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
    dialog.setStyleSheet(f"QDialog {{ background-color: {colors['bg']}; }}")
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)

    webview = AnkiWebView()
    webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    webview.page().setBackgroundColor(Qt.GlobalColor.transparent)

    toggled_days: Dict[int, bool] = {day: True for day in normalized_rules}

    def handle_pycmd(cmd: str) -> None:
        nonlocal toggled_days
        if cmd.startswith("anker:day_toggle_"):
            rest = cmd[len("anker:day_toggle_"):]
            parts = rest.split(":", 1)
            if len(parts) == 2:
                day = int(parts[0])
                checked = parts[1] == "true"
                toggled_days[day] = checked
        elif cmd == "anker:days_done":
            for day in range(1, 8):
                if toggled_days.get(day, False):
                    on_action(f"day_rule_set:{day}")
                else:
                    on_action(f"day_rule_remove:{day}")
            dialog.accept()
            on_done()
        elif cmd == "anker:days_cancel":
            dialog.reject()
            on_done()

    webview.set_bridge_command(handle_pycmd, dialog)
    webview.stdHtml(html)
    layout.addWidget(webview)

    # Центрируем относительно главного окна Anki
    if mw is not None:
        try:
            parent_geo = mw.geometry()
            x = parent_geo.x() + (parent_geo.width() - dialog.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - dialog.height()) // 2
            dialog.move(max(0, x), max(0, y))
        except Exception:
            pass

    dialog.exec()