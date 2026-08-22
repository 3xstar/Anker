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

import os
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from aqt import mw
from aqt.qt import (
    QDialog,
    QVBoxLayout,
    Qt,
    QSizePolicy,
)
from aqt.webview import AnkiWebView


# ── Пути к изображениям ────────────────────────────────────────────────────

def _assets_dir() -> str:
    """Абсолютный путь к папке assets/ аддона."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _image_url(filename: str) -> str:
    """file:// URL для изображения из assets/."""
    path = os.path.join(_assets_dir(), filename)
    # На Windows путь нужно преобразовать: C:\... → file:///C:/...
    path = path.replace("\\", "/")
    return f"file:///{path}"


# ── Константы изображений по сценариям ─────────────────────────────────────

IMG_NEUTRAL = "neutral.png"
IMG_WORRIED = "worried.png"
IMG_UNDERSTANDING = "understanding.png"
IMG_SAD = "sad.png"
IMG_ENTHUSIASTIC = "enthusiastic.png"
IMG_PROUDED = "prouded.png"


# ── HTML-шаблон ────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, "Segoe UI", sans-serif;
    background: #f5f0eb;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-end;
    min-height: 100vh;
    padding: 20px 20px 0 20px;
  }

  /* ── Спич-бабл ── */
  .bubble-wrapper {
    width: 100%;
    max-width: 420px;
    margin-bottom: 10px;
  }
  .bubble {
    position: relative;
    background: #ffffff;
    border: 2px solid #d4c5b9;
    border-radius: 20px;
    padding: 18px 22px;
    font-size: 15px;
    line-height: 1.55;
    color: #3a322e;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }
  /* Хвостик спич-бабла (указывает на персонажа слева снизу) */
  .bubble::after {
    content: "";
    position: absolute;
    bottom: -14px;
    left: 50px;
    width: 0;
    height: 0;
    border-left: 12px solid transparent;
    border-right: 12px solid transparent;
    border-top: 14px solid #ffffff;
  }
  .bubble::before {
    content: "";
    position: absolute;
    bottom: -18px;
    left: 48px;
    width: 0;
    height: 0;
    border-left: 14px solid transparent;
    border-right: 14px solid transparent;
    border-top: 16px solid #d4c5b9;
  }

  /* ── Персонаж + кнопки ── */
  .bottom-area {
    display: flex;
    align-items: flex-end;
    width: 100%;
    max-width: 420px;
    gap: 16px;
    margin-bottom: 16px;
  }
  .character {
    flex-shrink: 0;
  }
  .character img {
    width: 96px;
    height: auto;
    image-rendering: pixelated;
    display: block;
  }
  .buttons {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-bottom: 8px;
  }
  .btn {
    display: block;
    width: 100%;
    padding: 10px 14px;
    font-size: 14px;
    font-family: inherit;
    color: #3a322e;
    background: #ffffff;
    border: 2px solid #c4b5a5;
    border-radius: 14px;
    cursor: pointer;
    text-align: center;
    transition: background 0.15s;
  }
  .btn:hover {
    background: #f0e8dd;
  }
  .btn:active {
    background: #e0d5c5;
  }
  .btn.primary {
    background: #e8dcc8;
    border-color: #b8a080;
    font-weight: 600;
  }
  .btn.primary:hover {
    background: #dccca8;
  }
</style>
</head>
<body>
  <div class="bubble-wrapper">
    <div class="bubble">{message}</div>
  </div>
  <div class="bottom-area">
    <div class="character">
      <img src="{image_url}" alt="Anker">
    </div>
    <div class="buttons">
      {buttons_html}
    </div>
  </div>
</body>
</html>"""


def _build_buttons_html(buttons: List[Dict[str, str]]) -> str:
    """
    Генерирует HTML для кнопок.

    Каждая кнопка — словарь с ключами:
      - label: текст на кнопке
      - action: pycmd-команда (без префикса "anker:")
      - primary: bool (опционально, добавляет класс primary)
    """
    parts = []
    for btn in buttons:
        label = btn.get("label", "")
        action = btn.get("action", "")
        css_class = "btn"
        if btn.get("primary"):
            css_class += " primary"
        parts.append(
            f'<button class="{css_class}" onclick="pycmd(\'anker:{action}\')">{label}</button>'
        )
    return "\n".join(parts)


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
            buttons: список кнопок (см. _build_buttons_html).
            on_action: callback при нажатии кнопки, получает action-строку.
        """
        super().__init__(parent or mw)
        self._on_action = on_action
        self.setWindowTitle("Anker")
        self.setMinimumSize(460, 380)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.webview = AnkiWebView()
        self.webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.webview.set_bridge_command(self._handle_pycmd)

        html = HTML_TEMPLATE.format(
            message=message,
            image_url=_image_url(image_filename),
            buttons_html=_build_buttons_html(buttons),
        )
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
    """
    image = IMG_NEUTRAL
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    # Строим чекбоксы как HTML (внутри спич-бабла)
    checkboxes_html = ""
    for i, name in enumerate(day_names, 1):
        checked = "checked" if i in current_rules else ""
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

    # Для этого диалога нужен кастомный HTML с чекбоксами
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: -apple-system, "Segoe UI", sans-serif;
    background: #f5f0eb;
    display: flex; flex-direction: column; align-items: center;
    justify-content: flex-end; min-height: 100vh; padding: 20px 20px 0 20px;
  }}
  .bubble-wrapper {{ width:100%; max-width:420px; margin-bottom:10px; }}
  .bubble {{
    position:relative; background:#fff; border:2px solid #d4c5b9;
    border-radius:20px; padding:18px 22px; font-size:15px; line-height:1.55;
    color:#3a322e; box-shadow:0 2px 8px rgba(0,0,0,0.06);
  }}
  .bubble::after {{
    content:""; position:absolute; bottom:-14px; left:50px;
    border-left:12px solid transparent; border-right:12px solid transparent;
    border-top:14px solid #fff;
  }}
  .bubble::before {{
    content:""; position:absolute; bottom:-18px; left:48px;
    border-left:14px solid transparent; border-right:14px solid transparent;
    border-top:16px solid #d4c5b9;
  }}
  .bottom-area {{ display:flex; align-items:flex-end; width:100%; max-width:420px; gap:16px; margin-bottom:16px; }}
  .character img {{ width:96px; height:auto; image-rendering:pixelated; display:block; }}
  .buttons {{ flex:1; display:flex; flex-direction:column; gap:8px; padding-bottom:8px; }}
  .btn {{
    display:block; width:100%; padding:10px 14px; font-size:14px; font-family:inherit;
    color:#3a322e; background:#fff; border:2px solid #c4b5a5; border-radius:14px;
    cursor:pointer; text-align:center;
  }}
  .btn:hover {{ background:#f0e8dd; }}
  .btn.primary {{ background:#e8dcc8; border-color:#b8a080; font-weight:600; }}
  .btn.primary:hover {{ background:#dccca8; }}
  .day-checkboxes {{ margin:10px 0; }}
  .day-checkboxes label {{ display:inline-block; margin:4px 8px; cursor:pointer; font-size:14px; }}
</style></head>
<body>
  <div class="bubble-wrapper">
    <div class="bubble">
      {message}
      <div class="day-checkboxes">{checkboxes_html}</div>
    </div>
  </div>
  <div class="bottom-area">
    <div class="character"><img src="{_image_url(image)}" alt="Anker"></div>
    <div class="buttons">
      <button class="btn primary" onclick="pycmd('anker:days_done')">Готово</button>
      <button class="btn" onclick="pycmd('anker:days_cancel')">Отмена</button>
    </div>
  </div>
</body></html>"""

    dialog = QDialog(mw)
    dialog.setWindowTitle("Anker — дни недели")
    dialog.setMinimumSize(460, 420)
    dialog.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)

    webview = AnkiWebView()
    webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # Собираем переключения дней
    toggled_days: Dict[int, bool] = {}

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

    webview.set_bridge_command(handle_pycmd)
    webview.stdHtml(html)
    layout.addWidget(webview)
    dialog.exec()