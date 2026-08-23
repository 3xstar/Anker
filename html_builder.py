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


# ── SVG sparkline ──────────────────────────────────────────────────────────

def build_sparkline_svg(
    data: List[tuple],  # [(label, value), ...], value может быть None
    width: int = 280,
    height: int = 60,
    color: str = "#0078d4",
) -> str:
    """
    Генерирует инлайновый SVG sparkline по дневным значениям метрики.

    Значения None (дни без данных) пропускаются — линия разрывается.
    """
    # Фильтруем только точки с данными
    points = [(i, v) for i, (_, v) in enumerate(data) if v is not None]
    if len(points) < 2:
        return ""

    values = [v for _, v in points]
    min_v = min(values)
    max_v = max(values)
    v_range = max_v - min_v if max_v != min_v else 1.0

    padding_x = 4
    padding_y = 4
    usable_w = width - 2 * padding_x
    usable_h = height - 2 * padding_y

    # Строим polyline points
    coords = []
    for i, v in points:
        x = padding_x + (i / (len(data) - 1)) * usable_w if len(data) > 1 else padding_x
        y = padding_y + usable_h - ((v - min_v) / v_range) * usable_h
        coords.append(f"{x:.1f},{y:.1f}")

    polyline = " ".join(coords)

    # Точки на графике
    dots = ""
    for i, v in points:
        x = padding_x + (i / (len(data) - 1)) * usable_w if len(data) > 1 else padding_x
        y = padding_y + usable_h - ((v - min_v) / v_range) * usable_h
        dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{color}"/>'

    return f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"
     style="display:block;margin:8px auto;">
  <polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2"
   stroke-linecap="round" stroke-linejoin="round"/>
  {dots}
</svg>"""


# ── Шаблоны пояснений для экрана «Почему?» ─────────────────────────────────

def _retention_explanation(retention: Optional[float]) -> str:
    """Готовые фразы-шаблоны для разных диапазонов True Retention."""
    if retention is None:
        return "Недостаточно данных для оценки вспоминаемости."
    if retention < 0.50:
        return (
            "Вспоминаемость ниже 50% значит, что большая часть слов забывается "
            "и требует повторного изучения почти с нуля."
        )
    if retention < 0.70:
        return (
            "Вспоминаемость 50–70% — материал усваивается, но значительная "
            "часть карточек требует повторных усилий."
        )
    if retention < 0.85:
        return (
            "Вспоминаемость 70–85% — хороший уровень. Большинство карточек "
            "вспоминается уверенно, но есть куда расти."
        )
    return (
        "Вспоминаемость выше 85% — отличный результат. Материал усваивается "
        "уверенно, можно подумать об увеличении нагрузки."
    )


def _again_rate_explanation(again_rate: Optional[float]) -> str:
    """Готовые фразы-шаблоны для разных диапазонов Again-rate."""
    if again_rate is None:
        return "Недостаточно данных для оценки доли повторных ошибок."
    if again_rate > 0.25:
        return (
            "Доля ошибок выше 25% — признак перегрузки. Слишком много карточек "
            "приходится переучивать заново."
        )
    if again_rate > 0.15:
        return (
            "Доля ошибок 15–25% — повышенный уровень. Часть материала "
            "забывается быстрее, чем хотелось бы."
        )
    if again_rate > 0.08:
        return (
            "Доля ошибок 8–15% — нормальный рабочий уровень. "
            "Большинство повторений проходит успешно."
        )
    return (
        "Доля ошибок ниже 8% — отлично. Карточки вспоминаются легко "
        "и без усилий."
    )


def _difficulty_explanation(difficulty: Optional[float]) -> str:
    """Готовые фразы-шаблоны для разных диапазонов сложности FSRS."""
    if difficulty is None:
        return "Недостаточно данных для оценки сложности карточек."
    if difficulty > 7.0:
        return (
            "Средняя сложность выше 7 — карточки объективно трудные. "
            "Стоит снизить темп добавления новых."
        )
    if difficulty > 5.0:
        return (
            "Средняя сложность 5–7 — умеренный уровень. Карточки требуют "
            "внимания, но не чрезмерно."
        )
    return (
        "Средняя сложность ниже 5 — карточки относительно лёгкие. "
        "Можно уверенно добавлять новый материал."
    )


# ── HTML-шаблон экрана обоснования ─────────────────────────────────────────

STATS_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
__CSS__
  .stats-container { text-align:center; padding:10px 0; }
  .metric-name { font-size:13px; color:__TEXT_COLOR__; opacity:0.7; margin-bottom:4px; }
  .metric-value { font-size:36px; font-weight:700; color:__TEXT_COLOR__; margin-bottom:4px; }
  .metric-explanation { font-size:13px; color:__TEXT_COLOR__; opacity:0.8;
    line-height:1.45; margin:8px 16px; }
</style></head>
<body>
  <div class="bubble-wrapper">
    <div class="bubble">
      <div class="stats-container">
        <div class="metric-name">__METRIC_NAME__</div>
        <div class="metric-value">__METRIC_VALUE__</div>
        __SPARKLINE__
        <div class="metric-explanation">__EXPLANATION__</div>
      </div>
    </div>
  </div>
  <div class="bottom-area">
    <div class="character"><img src="__IMAGE_URL__" alt="Anker"></div>
    <div class="buttons">
      <button class="btn primary" onclick="pycmd('anker:stats_back')">Назад</button>
    </div>
  </div>
</body></html>"""


def build_stats_html(
    metric_name: str,
    metric_value: str,
    sparkline_svg: str,
    explanation: str,
    image_filename: str,
    theme_colors: Dict[str, str] | None = None,
) -> str:
    """
    Собирает HTML экрана обоснования решения (кнопка «Почему?»).

    Args:
        metric_name: человекочитаемое название метрики.
        metric_value: значение крупным шрифтом (например, "73%").
        sparkline_svg: инлайновый SVG график тренда.
        explanation: 1-2 предложения пояснения простыми словами.
        image_filename: изображение маскота под характер данных.
        theme_colors: цвета темы.
    """
    if theme_colors is None:
        theme_colors = DEFAULT_THEME_COLORS
    css = _apply_theme_colors(SHARED_DIALOG_CSS, theme_colors)
    return (
        STATS_TEMPLATE
        .replace("__CSS__", css)
        .replace("__METRIC_NAME__", metric_name)
        .replace("__METRIC_VALUE__", metric_value)
        .replace("__SPARKLINE__", sparkline_svg)
        .replace("__EXPLANATION__", explanation)
        .replace("__IMAGE_URL__", image_data_uri(image_filename))
        .replace("__TEXT_COLOR__", theme_colors.get("text", DEFAULT_THEME_COLORS["text"]))
    )
