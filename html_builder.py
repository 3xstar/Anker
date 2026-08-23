"""
html_builder.py — чистая генерация HTML для диалогов Anker.

Модуль НЕ зависит от aqt/Qt/AnkiWebView — только строки и списки словарей
на входе, строка HTML на выходе. Это позволяет тестировать генерацию HTML
вне Anki (см. tests/test_html_builder.py).

Сборка выполняется через .replace() с уникальными маркерами-плейсхолдерами
(__CSS__, __MESSAGE__, __IMAGE_URL__, __BUTTONS_HTML__, __CHECKBOXES_HTML__),
а НЕ через str.format() / f-string с фигурными скобками. Причина: CSS содержит
десятки одиночных фигурных скобок ({ ... }), которые str.format() трактует
как плейсхолдеры и падает с KeyError. Маркеры вида __XXX__ не пересекаются
с CSS/HTML-синтаксисом, поэтому этот класс ошибок исключён навсегда.

Изображения встраиваются в HTML как base64 data URI (а не file:// URL),
потому что Qt WebEngine (на котором построен AnkiWebView) по умолчанию
ограничивает доступ к локальным файлам через file:// из соображений
безопасности. data URI самодостаточен и не зависит от версии/ОС.
"""

import base64
import os
from typing import Dict, List


# ── Пути к изображениям ────────────────────────────────────────────────────

def _assets_dir() -> str:
    """Абсолютный путь к папке assets/ аддона."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def image_data_uri(filename: str) -> str:
    """
    Возвращает data URI (base64) для изображения из assets/.

    Встраивание напрямую в HTML вместо file:// URL — это надёжнее, так как
    Qt WebEngine (на котором построен AnkiWebView) по умолчанию ограничивает
    доступ к файлам через file:// из соображений безопасности.
    """
    path = os.path.join(_assets_dir(), filename)
    try:
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        # Пустая строка → img просто не отобразится, без падения диалога.
        return ""


# ── Общий CSS для всех диалогов (палитра в духе Anki) ──────────────────────

SHARED_DIALOG_CSS = """  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, "Segoe UI", sans-serif;
    background: __BG_COLOR__;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 20px;
  }

  /* ── Спич-бабл ── */
  .bubble-wrapper {
    width: 100%;
    max-width: 420px;
    margin-bottom: 10px;
  }
  .bubble {
    position: relative;
    background: __FRAME_BG_COLOR__;
    border: 2px solid __BORDER_COLOR__;
    border-radius: 20px;
    padding: 18px 22px;
    font-size: 15px;
    line-height: 1.55;
    color: __TEXT_COLOR__;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }
  /* Хвостик спич-бабла — указывает точно на центр персонажа.
     Центр .character: body padding 20px + img 96px/2 = 68px от левого края webview.
     Отступ от padding edge .bubble: 68 - (body padding 20 + border 2) = 46px.
     translateX(-50%) центрирует сам хвостик на этой координате. */
  .bubble::after {
    content: "";
    position: absolute;
    bottom: -14px;
    left: 46px;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 12px solid transparent;
    border-right: 12px solid transparent;
    border-top: 14px solid __FRAME_BG_COLOR__;
  }
  .bubble::before {
    content: "";
    position: absolute;
    bottom: -18px;
    left: 46px;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 14px solid transparent;
    border-right: 14px solid transparent;
    border-top: 16px solid __BORDER_COLOR__;
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
    color: __TEXT_COLOR__;
    background: __FRAME_BG_COLOR__;
    border: 2px solid __BORDER_COLOR__;
    border-radius: 14px;
    cursor: pointer;
    text-align: center;
    transition: background 0.15s;
  }
  .btn:hover {
    background: __BTN_HOVER_COLOR__;
  }
  .btn:active {
    background: __BTN_ACTIVE_COLOR__;
  }
  .btn.primary {
    background: #0078d4;
    border-color: #0067b8;
    color: #ffffff;
    font-weight: 600;
  }
  .btn.primary:hover {
    background: #106ebe;
  }"""


# ── HTML-шаблон основного диалога ──────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
__CSS__
</style>
</head>
<body>
  <div class="bubble-wrapper">
    <div class="bubble">__MESSAGE__</div>
  </div>
  <div class="bottom-area">
    <div class="character">
      <img src="__IMAGE_URL__" alt="Anker">
    </div>
    <div class="buttons">
      __BUTTONS_HTML__
    </div>
  </div>
</body>
</html>"""


# ── HTML-шаблон диалога выбора дней недели ────────────────────────────────

DAY_PICKER_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
__CSS__
  .day-checkboxes { margin:10px 0; }
  .day-checkboxes label { display:inline-block; margin:4px 8px; cursor:pointer; font-size:14px; }
</style></head>
<body>
  <div class="bubble-wrapper">
    <div class="bubble">
      __MESSAGE__
      <div class="day-checkboxes">__CHECKBOXES_HTML__</div>
    </div>
  </div>
  <div class="bottom-area">
    <div class="character"><img src="__IMAGE_URL__" alt="Anker"></div>
    <div class="buttons">
      <button class="btn primary" onclick="pycmd('anker:days_done')">Готово</button>
      <button class="btn" onclick="pycmd('anker:days_cancel')">Отмена</button>
    </div>
  </div>
</body></html>"""


# ── Цвета темы по умолчанию (светлая тема Anki) ────────────────────────────

DEFAULT_THEME_COLORS: Dict[str, str] = {
    "bg": "#f5f5f7",
    "frame_bg": "#ffffff",
    "text": "#1f1f23",
    "border": "#d0d0d5",
    "btn_hover": "#eceef1",
    "btn_active": "#dfe1e5",
}


def _apply_theme_colors(css: str, colors: Dict[str, str]) -> str:
    """Подставляет цвета темы в CSS-шаблон через маркеры __KEY__."""
    return (
        css
        .replace("__BG_COLOR__", colors.get("bg", DEFAULT_THEME_COLORS["bg"]))
        .replace("__FRAME_BG_COLOR__", colors.get("frame_bg", DEFAULT_THEME_COLORS["frame_bg"]))
        .replace("__TEXT_COLOR__", colors.get("text", DEFAULT_THEME_COLORS["text"]))
        .replace("__BORDER_COLOR__", colors.get("border", DEFAULT_THEME_COLORS["border"]))
        .replace("__BTN_HOVER_COLOR__", colors.get("btn_hover", DEFAULT_THEME_COLORS["btn_hover"]))
        .replace("__BTN_ACTIVE_COLOR__", colors.get("btn_active", DEFAULT_THEME_COLORS["btn_active"]))
    )


# ── Чистые функции сборки HTML ─────────────────────────────────────────────

def build_buttons_html(buttons: List[Dict[str, str]]) -> str:
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


def build_dialog_html(
    image_filename: str,
    message: str,
    buttons: List[Dict[str, str]],
    theme_colors: Dict[str, str] | None = None,
) -> str:
    """
    Собирает полный HTML основного диалога маскота.

    Args:
        image_filename: имя файла изображения (например, "neutral.png").
        message: текст в спич-бабле.
        buttons: список кнопок (см. build_buttons_html).
        theme_colors: словарь цветов темы (bg, frame_bg, text, border, ...).
                      Если None — используются светлые значения по умолчанию.

    Returns:
        Готовая HTML-строка для AnkiWebView.
    """
    if theme_colors is None:
        theme_colors = DEFAULT_THEME_COLORS
    css = _apply_theme_colors(SHARED_DIALOG_CSS, theme_colors)
    return (
        HTML_TEMPLATE
        .replace("__CSS__", css)
        .replace("__MESSAGE__", message)
        .replace("__IMAGE_URL__", image_data_uri(image_filename))
        .replace("__BUTTONS_HTML__", build_buttons_html(buttons))
    )


def build_day_picker_html(
    image_filename: str,
    message: str,
    checkboxes_html: str,
    theme_colors: Dict[str, str] | None = None,
) -> str:
    """
    Собирает полный HTML диалога выбора дней недели.

    Args:
        image_filename: имя файла изображения (например, "neutral.png").
        message: текст в спич-бабле.
        checkboxes_html: готовый HTML чекбоксов дней недели.
        theme_colors: словарь цветов темы (bg, frame_bg, text, border, ...).
                      Если None — используются светлые значения по умолчанию.

    Returns:
        Готовая HTML-строка для AnkiWebView.
    """
    if theme_colors is None:
        theme_colors = DEFAULT_THEME_COLORS
    css = _apply_theme_colors(SHARED_DIALOG_CSS, theme_colors)
    return (
        DAY_PICKER_TEMPLATE
        .replace("__CSS__", css)
        .replace("__MESSAGE__", message)
        .replace("__IMAGE_URL__", image_data_uri(image_filename))
        .replace("__CHECKBOXES_HTML__", checkboxes_html)
    )
