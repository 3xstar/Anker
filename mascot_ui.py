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

from .html_builder import build_dialog_html, build_day_picker_html

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.webview = AnkiWebView()
        self.webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.webview.set_bridge_command(self._handle_pycmd, self)

        html = build_dialog_html(image_filename, message, buttons)
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
    on_action: Callable[[str], None],
) -> None:
    """
    Показывает плановый визит маскота (раздел 5.2 ТЗ).

    Выбор ветки привязан к decision.action (который уже учитывает cooldown,
    историю и floor/ceiling), чтобы не предлагать изменение, которое всё равно
    не применится:

      - action == "increase" → enthusiastic.png (сценарий «слишком легко»)
      - action == "decrease" → understanding.png (плавный тренд перегрузки)
      - action == "hold" + is_stable_streak → prouded.png
      - action == "hold" иначе → neutral.png

    Правило приоритета из раздела 4: enthusiastic при «слишком легко» имеет
    приоритет над prouded — это уже заложено в action (increase > hold).
    """
    is_stable = decision.is_stable_streak
    is_too_easy = decision.is_too_easy

    if decision.action == "increase":
        image = IMG_ENTHUSIASTIC
        if is_too_easy:
            message = (
                "Похоже, учёба идёт отлично! Ты стабильно всё запоминаешь, "
                "и карточки даются очень легко. Может, попробуем увеличить "
                "количество новых карточек в день?"
            )
        else:
            message = (
                "Ты справляешься лучше, чем нужно! Вижу, что нагрузку можно "
                "немного увеличить. Попробуем добавить новых карточек?"
            )
        buttons = [
            {"label": "Да, давай увеличим", "action": "increase_accept", "primary": True},
            {"label": "Пока оставим как есть", "action": "increase_decline"},
        ]
    elif decision.action == "decrease":
        image = IMG_UNDERSTANDING
        message = (
            "Я заметил, что в последнее время тебе тяжеловато. "
            "Давай немного снизим количество новых карточек, чтобы ты мог "
            "восстановиться?"
        )
        buttons = [
            {"label": "Да, давай снизим", "action": "decrease_accept", "primary": True},
            {"label": "Нет, я справлюсь", "action": "decrease_decline"},
        ]
    elif is_stable:
        image = IMG_PROUDED
        message = (
            "Я тобой горжусь! Уже больше двух недель ты держишь стабильный ритм "
            "без единого срыва. Это впечатляет. Продолжай в том же духе!"
        )
        buttons = [
            {"label": "Спасибо!", "action": "prouded_ack", "primary": True},
        ]
    else:
        image = IMG_NEUTRAL
        message = (
            "Привет! Всё идёт своим чередом. "
            "Нагрузка сейчас в норме — продолжаем без изменений. "
            "Как ты себя чувствуешь?"
        )
        buttons = [
            {"label": "Нормально, продолжаем", "action": "neutral_ack", "primary": True},
        ]

    dialog = MascotDialog(image, message, buttons, on_action)
    dialog.exec()


def show_anomaly_checkin(
    on_action: Callable[[str], None],
) -> None:
    """
    Показывает anomaly check-in диалог (раздел 5.1 ТЗ).
    Изображение: worried.png.
    """
    image = IMG_WORRIED
    message = (
        "Сегодня тебе явно тяжелее, чем обычно. "
        "Что случилось?"
    )
    buttons = [
        {"label": "Лень / не хочется", "action": "anomaly_lazy"},
        {"label": "Занят(а) сегодня", "action": "anomaly_busy"},
        {"label": "Само пройдёт", "action": "anomaly_dismiss", "primary": True},
    ]
    dialog = MascotDialog(image, message, buttons, on_action)
    dialog.exec()


def show_anomaly_lazy(
    on_action: Callable[[str], None],
) -> None:
    """
    Реакция на «Лень / не хочется»: sad.png, предложение лёгкого режима.
    """
    image = IMG_SAD
    message = (
        "Бывает. Ничего страшного — иногда всем нужно отдохнуть. "
        "Давай включим временный лёгкий режим? "
        "Я снижу количество новых карточек, а через несколько дней всё вернётся."
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
    on_action: Callable[[str], None],
) -> None:
    """
    Реакция на «Занят(а) сегодня»: understanding.png, выбор дней недели.
    """
    image = IMG_UNDERSTANDING
    message = (
        "Понимаю, бывает. Хочешь настроить дни, в которые новые карточки "
        "не будут добавляться? Выбери дни недели, и я запомню."
    )
    buttons = [
        {"label": "Настроить дни недели", "action": "busy_setup_days", "primary": True},
        {"label": "Не сегодня, закроем", "action": "busy_dismiss"},
    ]
    dialog = MascotDialog(image, message, buttons, on_action)
    dialog.exec()


def show_day_of_week_picker(
    current_rules: Dict[int, float],
    on_action: Callable[[str], None],
) -> None:
    """
    Показывает диалог выбора дней недели для повторяющегося снижения нагрузки.
    Использует neutral.png (нейтральный контекст настройки).

    current_rules: {weekday: multiplier, ...}, weekday 1=Пн..7=Вс.
                   Ключи могут быть int или str (после JSON round-trip).
    """
    # Нормализуем ключи: после JSON round-trip они становятся строками
    normalized_rules: Dict[int, float] = {}
    for k, v in current_rules.items():
        normalized_rules[int(k)] = v

    image = IMG_NEUTRAL
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    # Строим чекбоксы как HTML (внутри спич-бабла)
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
        "В какие дни недели снижать количество новых карточек? "
        "Отметь нужные дни — в эти дни новые карточки добавляться не будут."
    )

    html = build_day_picker_html(image, message, checkboxes_html)

    dialog = QDialog(mw)
    dialog.setWindowTitle("Anker — дни недели")
    dialog.setFixedSize(460, 420)
    dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)

    webview = AnkiWebView()
    webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # Собираем переключения дней.
    # ВАЖНО: предзаполняем уже существующими правилами, чтобы при нажатии
    # «Готово» без изменений ранее сохранённые дни не стёрлись.
    toggled_days: Dict[int, bool] = {day: True for day in normalized_rules}

    def handle_pycmd(cmd: str) -> None:
        nonlocal toggled_days
        if cmd.startswith("anker:day_toggle_"):
            # формат: "anker:day_toggle_1:true"
            rest = cmd[len("anker:day_toggle_"):]
            parts = rest.split(":", 1)
            if len(parts) == 2:
                day = int(parts[0])
                checked = parts[1] == "true"
                toggled_days[day] = checked
        elif cmd == "anker:days_done":
            # Передаём все выбранные дни
            for day in range(1, 8):
                if toggled_days.get(day, False):
                    on_action(f"day_rule_set:{day}")
                else:
                    on_action(f"day_rule_remove:{day}")
            dialog.accept()
        elif cmd == "anker:days_cancel":
            dialog.reject()

    webview.set_bridge_command(handle_pycmd, dialog)
    webview.stdHtml(html)
    layout.addWidget(webview)
    dialog.exec()