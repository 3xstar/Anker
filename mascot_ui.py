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

from .html_builder import build_dialog_html, build_day_picker_html, DEFAULT_THEME_COLORS

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

    Использует AnkiWebView для рендеринга HTML с кастомным CSS (спич-бабл,
    персонаж, кнопки). Кнопки отправляют pycmd-команды, которые обрабатываются
    через set_bridge_command.
    """

    def __init__(
        self,
        image_filename: str,
        message: str,
        buttons: List[Dict[str, str]],
        on_action: Callable[[str], None],
        parent=None,
    ):
        """
        Args:
            image_filename: имя файла изображения (например, "neutral.png").
            message: текст в спич-бабле.
            buttons: список кнопок (см. html_builder.build_buttons_html).
            on_action: callback при нажатии кнопки, получает action-строку.
        """
        super().__init__(parent or mw)
        self._on_action = on_action
        self.setWindowTitle("Anker")
        self.setFixedSize(460, 380)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)

        colors = _get_theme_colors()
        self.setStyleSheet(f"QDialog {{ background-color: {colors['bg']}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.webview = AnkiWebView()
        self.webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.webview.set_bridge_command(self._handle_pycmd, self)
        self.webview.page().setBackgroundColor(Qt.GlobalColor.transparent)

        html = build_dialog_html(image_filename, message, buttons, colors)
        self.webview.stdHtml(html)
        layout.addWidget(self.webview)

    def _handle_pycmd(self, cmd: str) -> None:
        """Обрабатывает pycmd-команды от кнопок."""
        if cmd.startswith("anker:"):
            action = cmd[len("anker:"):]
            self._on_action(action)
            self.accept()


# ── Фабрики диалогов по сценариям ──────────────────────────────────────────

def show_planned_visit(
    decision: Any,  # Decision из decision_engine
    deck_name: str,
    on_action: Callable[[str], None],
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
    is_too_easy = decision.is_too_easy

    if decision.action == "increase":
        image = IMG_ENTHUSIASTIC
        message = (
            f"«{deck_name}» усваивается уверенно — "
            f"можно немного ускориться и добавить новых карточек."
        )
        buttons = [
            {"label": "Да, давай увеличим", "action": "increase_accept", "primary": True},
            {"label": "Пока оставим как есть", "action": "increase_decline"},
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
        ]
    elif is_stable:
        image = IMG_PROUDED
        message = (
            f"Всё стабильно с колодой «{deck_name}» — "
            f"продолжаем в том же темпе."
        )
        buttons = [
            {"label": "Спасибо!", "action": "prouded_ack", "primary": True},
        ]
    else:
        image = IMG_NEUTRAL
        message = (
            f"Всё стабильно с колодой «{deck_name}» — "
            f"продолжаем в том же темпе."
        )
        buttons = [
            {"label": "Хорошо", "action": "neutral_ack", "primary": True},
        ]

    dialog = MascotDialog(image, message, buttons, on_action)
    dialog.exec()


def show_anomaly_checkin(
    deck_name: str,
    on_action: Callable[[str], None],
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
    ]
    dialog = MascotDialog(image, message, buttons, on_action)
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
    dialog.setFixedSize(460, 420)
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
    dialog.exec()