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
    build_stats_html,
    build_sparkline_svg,
    DEFAULT_THEME_COLORS,
    _retention_explanation,
    _again_rate_explanation,
    _difficulty_explanation,
)

try:
    from aqt import mw
    from aqt.qt import (
        QDialog,
        QTimer,
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
    QTimer = object
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
    except Exception:
        return dict(DEFAULT_THEME_COLORS)


# ── Константы изображений по сценариям ─────────────────────────────────────

IMG_NEUTRAL = "neutral.png"
IMG_WORRIED = "worried.png"
IMG_UNDERSTANDING = "understanding.png"
IMG_SAD = "sad.png"
IMG_ENTHUSIASTIC = "enthusiastic.png"
IMG_PROUDED = "prouded.png"


# ── Класс диалога ──────────────────────────────────────────────────────────

class MascotDialog(QDialog):
    """
    Модальное диалоговое окно с маскотом Anker.

    Поддерживает кнопку «Почему?» — при нажатии заменяет содержимое
    на экран обоснования с метриками и графиком, без закрытия диалога.
    Кнопка «Назад» возвращает к основному сообщению.

    Размер окна адаптируется под высоту контента (от 320 до 700 px),
    окно центрируется относительно главного окна Anki.
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
            stats_context: данные для экрана «Почему?» (метрики, решение).
        """
        super().__init__(parent or mw)
        self._on_action = on_action
        self._stats_context = stats_context
        self._colors = _get_theme_colors()

        # Сохраняем параметры для восстановления после экрана статистики
        self._main_image = image_filename
        self._main_message = message
        self._main_buttons = buttons

        self.setWindowTitle("Anker")
        self.setMinimumSize(460, 320)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(f"QDialog {{ background-color: {self._colors['bg']}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.webview = AnkiWebView()
        self.webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.webview.set_bridge_command(self._handle_pycmd, self)
        self.webview.page().setBackgroundColor(Qt.GlobalColor.transparent)

        self._show_main()
        layout.addWidget(self.webview)

    def _show_main(self) -> None:
        """Показывает основной экран диалога."""
        html = build_dialog_html(
            self._main_image, self._main_message, self._main_buttons, self._colors
        )
        self.webview.stdHtml(html)
        QTimer.singleShot(150, self._resize_to_content)

    def _show_stats(self) -> None:
        """Показывает экран обоснования (кнопка «Почему?»)."""
        ctx = self._stats_context or {}
        metrics = ctx.get("metrics", {})
        decision_action = ctx.get("decision_action", "hold")

        # Выбираем, какую метрику показать, в зависимости от причины решения
        if decision_action == "decrease":
            ret = metrics.get("true_retention_14d")
            daily = metrics.get("daily_retention_14d", [])
            metric_name = "Вспоминаемость карточек"
            metric_value = f"{int(ret * 100)}%" if ret is not None else "—"
            sparkline = build_sparkline_svg(daily, color="#d13438") if daily else ""
            explanation = _retention_explanation(ret)
            image = IMG_SAD
        elif decision_action == "increase":
            ret = metrics.get("true_retention_14d")
            daily = metrics.get("daily_retention_14d", [])
            metric_name = "Вспоминаемость карточек"
            metric_value = f"{int(ret * 100)}%" if ret is not None else "—"
            sparkline = build_sparkline_svg(daily, color="#107c10") if daily else ""
            explanation = _retention_explanation(ret)
            image = IMG_ENTHUSIASTIC
        elif ctx.get("is_anomaly"):
            again = None
            daily = metrics.get("daily_again_rate_14d", [])
            if daily:
                today_data = daily[-1] if daily else None
                again = today_data[1] if today_data else None
            metric_name = "Доля ошибок (сегодня)"
            metric_value = f"{int(again * 100)}%" if again is not None else "—"
            sparkline = build_sparkline_svg(daily, color="#d13438") if daily else ""
            explanation = _again_rate_explanation(again)
            image = IMG_WORRIED
        else:
            ret = metrics.get("true_retention_14d")
            daily = metrics.get("daily_retention_14d", [])
            metric_name = "Вспоминаемость карточек"
            metric_value = f"{int(ret * 100)}%" if ret is not None else "—"
            sparkline = build_sparkline_svg(daily) if daily else ""
            explanation = _retention_explanation(ret)
            image = IMG_PROUDED if ctx.get("is_stable") else IMG_NEUTRAL

        html = build_stats_html(
            metric_name=metric_name,
            metric_value=metric_value,
            sparkline_svg=sparkline,
            explanation=explanation,
            image_filename=image,
            theme_colors=self._colors,
        )
        self.webview.stdHtml(html)
        QTimer.singleShot(150, self._resize_to_content)

    def _resize_to_content(self) -> None:
        """Измеряет реальную высоту контента и подгоняет размер окна."""
        js = "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
        self.webview.page().runJavaScript(
            js,
            lambda h: self._apply_content_height(int(h) if h else 380),
        )

    def _apply_content_height(self, height: int) -> None:
        """Применяет высоту окна с разумными пределами и центрирует."""
        target = min(max(height + 40, 320), 700)
        self.setFixedSize(460, target)
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
            if action == "why":
                self._show_stats()
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
            f"«{deck_name}» усваивается уверенно — "
            f"можно немного ускориться и добавить новых карточек."
        )
        buttons = [
            {"label": "Да, давай увеличим", "action": "increase_accept", "primary": True},
            {"label": "Пока оставим как есть", "action": "increase_decline"},
            {"label": "Почему?", "action": "why"},
        ]
    elif decision.action == "decrease":
        image = IMG_UNDERSTANDING
        message = (
            f"Колоде «{deck_name}» в последнее время тяжело даются повторения. "
            f"Есть смысл ненадолго снизить количество новых карточек."
        )
        buttons = [
            {"label": "Да, давай снизим", "action": "decrease_accept", "primary": True},
            {"label": "Нет, я справлюсь", "action": "decrease_decline"},
            {"label": "Почему?", "action": "why"},
        ]
    elif is_stable:
        image = IMG_PROUDED
        message = (
            f"Всё стабильно с колодой «{deck_name}» — "
            f"продолжаем в том же темпе."
        )
        buttons = [
            {"label": "Спасибо!", "action": "prouded_ack", "primary": True},
            {"label": "Почему?", "action": "why"},
        ]
    else:
        image = IMG_NEUTRAL
        message = (
            f"Всё стабильно с колодой «{deck_name}» — "
            f"продолжаем в том же темпе."
        )
        buttons = [
            {"label": "Хорошо", "action": "neutral_ack", "primary": True},
            {"label": "Почему?", "action": "why"},
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
        f"Сегодня заметно тяжелее обычного с «{deck_name}». "
        f"Что случилось?"
    )
    buttons = [
        {"label": "Лень / не хочется", "action": "anomaly_lazy"},
        {"label": "Занят(а) сегодня", "action": "anomaly_busy"},
        {"label": "Само пройдёт", "action": "anomaly_dismiss", "primary": True},
        {"label": "Почему?", "action": "why"},
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
        f"Бывает. Давай включим временный лёгкий режим для «{deck_name}»? "
        f"Я снижу количество новых карточек, а через несколько дней всё вернётся."
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
        f"Понимаю. Хочешь настроить дни без новых карточек для «{deck_name}»?"
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
        f"В какие дни недели снижать новые карточки для «{deck_name}»?"
    )

    colors = _get_theme_colors()
    html = build_day_picker_html(image, message, checkboxes_html, colors)

    dialog = QDialog(mw)
    dialog.setWindowTitle("Anker — дни недели")
    dialog.setMinimumSize(460, 320)
    dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
    dialog.setStyleSheet(f"QDialog {{ background-color: {colors['bg']}; }}")
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)

    webview = AnkiWebView()
    webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    webview.page().setBackgroundColor(Qt.GlobalColor.transparent)

    toggled_days: Dict[int, bool] = {day: True for day in normalized_rules}

    def _resize_day_picker() -> None:
        js = "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
        webview.page().runJavaScript(
            js,
            lambda h: _apply_day_picker_height(int(h) if h else 420),
        )

    def _apply_day_picker_height(height: int) -> None:
        target = min(max(height + 40, 320), 700)
        dialog.setFixedSize(460, target)
        if mw is not None:
            try:
                parent_geo = mw.geometry()
                x = parent_geo.x() + (parent_geo.width() - dialog.width()) // 2
                y = parent_geo.y() + (parent_geo.height() - dialog.height()) // 2
                dialog.move(max(0, x), max(0, y))
            except Exception:
                pass

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
    QTimer.singleShot(150, _resize_day_picker)
    dialog.exec()