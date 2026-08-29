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
import math
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import log
except ImportError:  # вне Anki (тесты) модуль импортируется как top-level
    import log


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
    except Exception as e:
        log.log_error("html_builder.image_data_uri", e)
        # Пустая строка → img просто не отобразится, без падения диалога.
        return ""


def _font_data_uri(filename: str) -> str:
    """
    Возвращает data URI (base64) для шрифта из assets/fonts/.

    Внешние источники (Google Fonts CDN и т.п.) недоступны, поэтому шрифт
    встраивается локально через @font-face тем же способом, что и PNG персонажа.
    """
    path = os.path.join(_assets_dir(), "fonts", filename)
    try:
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("ascii")
        return f"data:font/woff2;base64,{encoded}"
    except Exception as e:
        log.log_error("html_builder._font_data_uri", e)
        # Пустая строка → шрифт просто не подгрузится, останется системный fallback.
        return ""


def _font_faces_css() -> str:
    """Возвращает @font-face-объявления для Nunito (встроены как base64)."""
    return (
        "@font-face { font-family: 'Nunito'; "
        f"src: url({_font_data_uri('nunito-400.woff2')}) format('woff2'); "
        "font-weight: 400; }\n"
        "@font-face { font-family: 'Nunito'; "
        f"src: url({_font_data_uri('nunito-700.woff2')}) format('woff2'); "
        "font-weight: 700; }\n"
        "@font-face { font-family: 'Nunito'; "
        f"src: url({_font_data_uri('nunito-800.woff2')}) format('woff2'); "
        "font-weight: 800; }"
    )


# ── Общий CSS для всех диалогов (палитра в духе Anki) ──────────────────────

SHARED_DIALOG_CSS = """__FONT_FACES__
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Nunito', -apple-system, "Segoe UI", sans-serif;
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
    padding: 12px 16px;
    font-size: 26px;
    font-family: inherit;
    color: #1f1f23;
    background: #ffffff;
    border: 1px solid #c8c8ce;
    border-radius: 16px;
    cursor: pointer;
    text-align: center;
    transition: background 0.15s;
  }
  .btn:hover {
    background: #f2f2f4;
  }
  .btn:active {
    background: #e4e4e8;
  }
  .btn.primary {
    background: #0078d4;
    border-color: #0067b8;
    color: #ffffff;
    font-weight: 600;
  }
  .btn.primary:hover {
    background: #106ebe;
  }
  .stats-link-row { text-align:center; margin-top:4px; }
  .btn-link {
    background:none; border:none; color:#ffffff;
    font-size:28px; font-weight:600; font-family:inherit;
    cursor:pointer; padding:10px 16px;
    text-decoration:underline; transition:opacity 0.15s;
  }
  .btn-link:hover { opacity:0.85; }
"""


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
  <div class="stats-link-row">
    <button class="btn-link" onclick="pycmd('anker:show_stats')">__STATS_BUTTON_LABEL__</button>
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
        .replace("__FONT_FACES__", _font_faces_css())
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
    deck_name: Optional[str] = None,
    period: Optional[int] = None,
) -> str:
    """
    Собирает полный HTML основного диалога маскота.

    Args:
        image_filename: имя файла изображения (например, "neutral.png").
        message: текст в спич-бабле.
        buttons: список кнопок (см. build_buttons_html).
        theme_colors: словарь цветов темы (bg, frame_bg, text, border, ...).
                      Если None — используются светлые значения по умолчанию.
        deck_name: имя отслеживаемой колоды (для подписи кнопки статистики).
        period: период анализа в днях (для подписи кнопки статистики).

    Returns:
        Готовая HTML-строка для AnkiWebView.
    """
    if theme_colors is None:
        theme_colors = DEFAULT_THEME_COLORS
    css = _apply_theme_colors(SHARED_DIALOG_CSS, theme_colors)

    if deck_name and period:
        stats_button_label = f"Статистика {deck_name} ({period} дн.)"
    else:
        stats_button_label = "Моя статистика"

    return (
        HTML_TEMPLATE
        .replace("__CSS__", css)
        .replace("__MESSAGE__", message)
        .replace("__IMAGE_URL__", image_data_uri(image_filename))
        .replace("__BUTTONS_HTML__", build_buttons_html(buttons))
        .replace("__STATS_BUTTON_LABEL__", stats_button_label)
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
    width: int = 360,
    height: int = 100,
    color: str = "#0078d4",
    value_format: str = "number",  # "percent" | "number"
) -> str:
    """
    Генерирует инлайновый SVG sparkline по дневным значениям метрики.

    Значения None (дни без данных) пропускаются — линия разрывается.
    Над каждой точкой рисуется подпись её значения в нужном формате.
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
    # Сверху запас под подписи значений, снизу — под точки.
    padding_top = 18
    padding_bottom = 4
    usable_w = width - 2 * padding_x
    usable_h = height - padding_top - padding_bottom

    def _fmt(v: float) -> str:
        if value_format == "percent":
            return f"{v * 100:.0f}%"
        if float(v).is_integer():
            return f"{int(v)}"
        return f"{v:.1f}"

    # Строим polyline points
    coords = []
    for i, v in points:
        x = padding_x + (i / (len(data) - 1)) * usable_w if len(data) > 1 else padding_x
        y = padding_top + usable_h - ((v - min_v) / v_range) * usable_h
        coords.append(f"{x:.1f},{y:.1f}")

    polyline = " ".join(coords)

    # Точки на графике + текстовые подписи значений над каждой точкой
    dots = ""
    labels = ""
    for i, v in points:
        x = padding_x + (i / (len(data) - 1)) * usable_w if len(data) > 1 else padding_x
        y = padding_top + usable_h - ((v - min_v) / v_range) * usable_h
        dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{color}"/>'
        labels += (
            f'<text x="{x:.1f}" y="{y - 8:.1f}" font-size="12" '
            f'text-anchor="middle" fill="{color}">{_fmt(v)}</text>'
        )

    return f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"
     style="display:block;margin:8px auto;">
  <polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2"
   stroke-linecap="round" stroke-linejoin="round"/>
  {dots}
  {labels}
</svg>"""


# ── SVG gauge (градусник) ──────────────────────────────────────────────────

def build_gauge_svg(
    value: Optional[float],
    min_value: float = 0.0,
    max_value: float = 10.0,
    width: int = 360,
    height: int = 100,
    value_format: str = "number",
) -> str:
    """
    Горизонтальная шкала-градусник (градиент зелёный→красный слева направо)
    с маркером текущего значения и подписью значения у маркера.

    Маркер зажимается в диапазон [min_value, max_value], но подпись показывает
    фактическое значение (актуально для стабильности, где значение может
    выходить за верхнюю границу шкалы).
    """
    if value is None:
        return ""

    def _fmt(v: float) -> str:
        if value_format == "percent":
            return f"{v * 100:.0f}%"
        return f"{v:.1f}"

    raw = float(value)
    clamped = max(min_value, min(max_value, raw))
    span = max_value - min_value
    frac = (clamped - min_value) / span if span > 0 else 0.0

    pad = 20
    track_w = width - 2 * pad
    bar_h = 16
    bar_y = height / 2 - bar_h / 2
    marker_x = pad + frac * track_w

    return f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"
     style="display:block;margin:8px auto;">
  <defs>
    <linearGradient id="gauge-grad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#107c10"/>
      <stop offset="50%" stop-color="#e8c93a"/>
      <stop offset="100%" stop-color="#d13438"/>
    </linearGradient>
  </defs>
  <rect x="{pad:.1f}" y="{bar_y:.1f}" width="{track_w:.1f}" height="{bar_h:.1f}"
   rx="{bar_h / 2:.1f}" fill="url(#gauge-grad)"/>
  <circle cx="{marker_x:.1f}" cy="{bar_y + bar_h / 2:.1f}" r="6"
   fill="__TEXT_COLOR__" stroke="#ffffff" stroke-width="2"/>
  <text x="{marker_x:.1f}" y="{bar_y - 8:.1f}" font-size="13" text-anchor="middle"
   fill="__TEXT_COLOR__">{_fmt(raw)}</text>
</svg>"""


# ── SVG donut (кольцевая диаграмма) ────────────────────────────────────────

def build_donut_svg(
    ratio: Optional[float],
    size: int = 170,
    stable_color: str = "#107c10",
    unstable_color: str = "#d13438",
) -> str:
    """
    Кольцевая диаграмма на чистом SVG: два дуговых сегмента — стабильные
    (зелёный) и нестабильные (красный). В центре — процент нестабильных.
    """
    if ratio is None:
        return ""
    ratio = max(0.0, min(1.0, float(ratio)))

    stroke_w = 14
    cx = cy = size / 2
    r = (size - stroke_w) / 2
    circumference = 2 * math.pi * r
    unstable_len = ratio * circumference
    stable_len = (1.0 - ratio) * circumference

    return f"""<svg width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg"
     style="display:block;margin:8px auto;">
  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" stroke="#e0e0e0"
   stroke-width="{stroke_w}" fill="none"/>
  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" stroke="{stable_color}"
   stroke-width="{stroke_w}" fill="none"
   stroke-dasharray="{stable_len:.1f} {circumference:.1f}" stroke-dashoffset="0"
   transform="rotate(-90 {cx:.1f} {cy:.1f})"/>
  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" stroke="{unstable_color}"
   stroke-width="{stroke_w}" fill="none"
   stroke-dasharray="{unstable_len:.1f} {circumference:.1f}"
   stroke-dashoffset="{-stable_len:.1f}"
   transform="rotate(-90 {cx:.1f} {cy:.1f})"/>
  <text x="{cx:.1f}" y="{cy:.1f}" font-size="26" font-weight="800"
   text-anchor="middle" dominant-baseline="central"
   fill="__TEXT_COLOR__">{int(ratio * 100)}%</text>
</svg>"""


# ── SVG парная столбчатая диаграмма ────────────────────────────────────────

def build_bar_pair_svg(
    left_label: str,
    left_value: Optional[float],
    right_label: str,
    right_value: Optional[float],
    left_color: str = "#0078d4",
    right_color: str = "#d13438",
    width: int = 360,
    height: int = 140,
    value_format: str = "number",
) -> str:
    """
    Парная столбчатая диаграмма: два столбца разной высоты рядом,
    с подписанными числами над каждым столбцом и подписями под столбцами.
    """
    if left_value is None and right_value is None:
        return ""

    def _fmt(v: Optional[float]) -> str:
        if v is None:
            return "—"
        if value_format == "percent":
            return f"{v * 100:.0f}%"
        if float(v).is_integer():
            return f"{int(v)}"
        return f"{v:.1f}"

    non_none = [v for v in (left_value, right_value) if v is not None]
    max_v = max(non_none) if non_none else 1.0
    if max_v <= 0:
        max_v = 1.0

    gap = 32
    chart_w = width - 40  # боковые поля
    bar_w = min(88.0, (chart_w - gap) / 2)
    total_w = 2 * bar_w + gap
    start_x = (width - total_w) / 2

    pad_top = 24   # под подписи значений
    pad_bottom = 24  # под подписи столбцов
    plot_h = height - pad_top - pad_bottom

    def _bar(x: float, v: Optional[float], color: str) -> str:
        h = (v / max_v) * plot_h if v is not None else 0.0
        y = pad_top + (plot_h - h)
        cx = x + bar_w / 2
        return (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'rx="4" fill="{color}"/>'
            f'<text x="{cx:.1f}" y="{y - 6:.1f}" font-size="13" text-anchor="middle" '
            f'fill="__TEXT_COLOR__">{_fmt(v)}</text>'
        )

    left_x = start_x
    right_x = start_x + bar_w + gap
    bars = _bar(left_x, left_value, left_color) + _bar(right_x, right_value, right_color)

    labels = (
        f'<text x="{left_x + bar_w / 2:.1f}" y="{height - 8:.1f}" font-size="13" '
        f'text-anchor="middle" fill="__TEXT_COLOR__">{left_label}</text>'
        f'<text x="{right_x + bar_w / 2:.1f}" y="{height - 8:.1f}" font-size="13" '
        f'text-anchor="middle" fill="__TEXT_COLOR__">{right_label}</text>'
    )

    return f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"
     style="display:block;margin:8px auto;">
  {bars}
  {labels}
</svg>"""


# ── SVG столбчатый график по дневным точкам ────────────────────────────────

def build_bar_chart_svg(
    data: List[tuple],  # [(label, value), ...], value может быть None
    width: int = 360,
    height: int = 120,
    color: str = "#0078d4",
    value_format: str = "number",
) -> str:
    """
    Столбчатый график по дневным точкам (аналог sparkline, но <rect> вместо
    линии+точек). Значения None пропускаются. Над каждым столбцом — подпись
    значения.
    """
    points = [(i, v) for i, (_, v) in enumerate(data) if v is not None]
    if not points:
        return ""

    values = [v for _, v in points]
    max_v = max(values) if values else 1.0
    if max_v <= 0:
        max_v = 1.0

    padding_x = 4
    padding_top = 18
    padding_bottom = 4
    usable_w = width - 2 * padding_x
    usable_h = height - padding_top - padding_bottom

    def _fmt(v: float) -> str:
        if value_format == "percent":
            return f"{v * 100:.0f}%"
        if float(v).is_integer():
            return f"{int(v)}"
        return f"{v:.1f}"

    n = len(points)
    slot = usable_w / n if n > 1 else usable_w
    bar_w = max(4.0, slot * 0.6)

    bars = ""
    labels = ""
    for i, v in points:
        x_center = padding_x + slot * i + slot / 2
        h = (v / max_v) * usable_h
        x = x_center - bar_w / 2
        y = padding_top + (usable_h - h)
        bars += (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'rx="2" fill="{color}"/>'
        )
        labels += (
            f'<text x="{x_center:.1f}" y="{y - 6:.1f}" font-size="12" '
            f'text-anchor="middle" fill="{color}">{_fmt(v)}</text>'
        )

    return f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"
     style="display:block;margin:8px auto;">
  {bars}
  {labels}
</svg>"""


# ── Единая диспетчеризация визуализации по типу метрики ────────────────────

def _metric_visualization_svg(
    key: str, metrics: Dict[str, Any], value: Optional[float]
) -> str:
    """
    Возвращает SVG-визуализацию для метрики по её ключу, либо "" если
    визуализировать нечего. Единая логика выбора используется и вкладкой
    «Главное», и вкладкой «Все показатели», чтобы она не дублировалась.
    """
    if key == "true_retention":
        return build_sparkline_svg(metrics.get("daily_retention", []), value_format="percent")
    if key in ("again_rate_young", "again_rate_mature"):
        return build_sparkline_svg(metrics.get("daily_again_rate", []), value_format="percent")
    if key == "new_card_retention":
        return build_gauge_svg(value, min_value=0.0, max_value=1.0, value_format="percent")
    if key == "avg_difficulty":
        return build_gauge_svg(value, min_value=0.0, max_value=10.0)
    if key == "avg_stability":
        return build_gauge_svg(value, min_value=0.0, max_value=60.0)
    if key == "low_stability_ratio":
        return build_donut_svg(value)
    if key == "actual_vs_predicted":
        counts = metrics.get("actual_vs_predicted_counts") or {}
        return build_bar_pair_svg(
            "Ожидалось", counts.get("predicted"),
            "Фактически", counts.get("actual"),
        )
    if key == "avg_time_growth":
        return build_bar_pair_svg(
            "Раньше", metrics.get("avg_time_prev"),
            "Сейчас", metrics.get("avg_time_per_card"),
        )
    if key == "consistency":
        return build_bar_chart_svg(metrics.get("daily_review_count", []))
    if key == "relearning_stuck":
        return build_bar_chart_svg(metrics.get("daily_relearning_count", []))
    return ""


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


# ── Шаблоны пояснений для всех метрик ──────────────────────────────────────

def _stability_explanation(stability: Optional[float]) -> str:
    if stability is None:
        return "Недостаточно данных для оценки стабильности."
    if stability < 3:
        return "Стабильность ниже 3 дней — карточки быстро забываются, интервалы короткие."
    if stability < 10:
        return "Стабильность 3–10 дней — нормальный уровень, карточки закрепляются."
    return "Стабильность выше 10 дней — отлично, интервалы между повторениями большие."


def _load_ratio_explanation(ratio: Optional[float]) -> str:
    if ratio is None:
        return "Недостаточно данных для сравнения нагрузки."
    if ratio > 1.3:
        return "Фактическая нагрузка заметно выше прогноза — лимит, возможно, завышен."
    if ratio > 1.1:
        return "Фактическая нагрузка немного выше прогноза."
    if ratio > 0.9:
        return "Фактическая нагрузка близка к прогнозу — всё в порядке."
    return "Фактическая нагрузка ниже прогноза."


def _time_growth_explanation(growth: Optional[float]) -> str:
    if growth is None:
        return "Недостаточно данных о времени на карточку."
    if growth > 1.3:
        return "На карточки стало уходить заметно больше времени, чем раньше, — возможно, ты устаёшь."
    if growth > 1.1:
        return "Время на карточку немного выросло по сравнению с прошлым периодом."
    if growth > 0.9:
        return "Время на карточку стабильно — без резких скачков вверх или вниз."
    return "Время на карточку снижается — материал усваивается быстрее."


def _consistency_explanation(consistency: Optional[float]) -> str:
    if consistency is None:
        return "Недостаточно данных о регулярности занятий."
    if consistency < 0.3:
        return "Регулярность низкая — занятия проходят нестабильно, это мешает закреплению."
    if consistency < 0.6:
        return "Регулярность средняя — есть пропуски, но в целом ритм держится."
    return "Регулярность высокая — стабильный график занятий."


def _stuck_explanation(stuck: Optional[float]) -> str:
    if stuck is None:
        return "Нет данных о застрявших карточках."
    if stuck > 10:
        return "Много карточек застряло в переучивании — стоит обратить на них внимание."
    if stuck > 3:
        return "Несколько карточек застряло в переучивании."
    return "Застрявших карточек мало или нет."


def _new_card_retention_explanation(ret: Optional[float]) -> str:
    if ret is None:
        return "Недостаточно данных по новым карточкам."
    if ret < 0.50:
        return "Новые карточки запоминаются тяжело — больше половины забывается."
    if ret < 0.70:
        return "Новые карточки усваиваются средне."
    if ret < 0.85:
        return "Новые карточки усваиваются хорошо."
    return "Новые карточки усваиваются отлично."


def _low_stability_explanation(ratio: Optional[float]) -> str:
    if ratio is None:
        return "Недостаточно данных о нестабильных карточках."
    if ratio > 0.4:
        return "Много карточек с низкой стабильностью — материал ещё не закрепился."
    if ratio > 0.2:
        return "Умеренная доля нестабильных карточек."
    return "Мало нестабильных карточек — материал закрепляется хорошо."


# ── HTML-шаблон экрана обоснования с вкладками ─────────────────────────────

STATS_TABBED_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
__CSS__
  .tabs { display:flex; gap:0; margin-bottom:8px; }
  .tab-btn {
    flex:1; padding:10px 0; font-size:34px; font-family:inherit;
    background:#ffffff; color:#1f1f23; border:1px solid #c8c8ce;
    cursor:pointer; text-align:center; transition:background 0.15s;
    border-radius: 0;
  }
  .tab-btn.active { background:#0078d4; border-color:#0067b8; color:#ffffff; font-weight:600; }
  .stats-deck-title { font-family:'Nunito',sans-serif; font-weight:700; font-size:48px;
    color:__TEXT_COLOR__; text-align:left; margin-bottom:8px; }
  .stats-container { text-align:center; padding:10px 0; }
  .stats-container .metric-title {
    font-family: 'Nunito', sans-serif;
    font-weight: 700;
    font-size: 22px;
    color: __TEXT_COLOR__;
    margin-bottom: 4px;
  }
  .metric-value { font-size:52px; font-weight:800; color:__TEXT_COLOR__; margin-bottom:4px; }
  .metric-explanation { font-size:18px; color:__TEXT_COLOR__; opacity:0.8;
    line-height:1.45; margin:8px 16px; }
  .all-metrics { text-align:left; }
  /* Внутренний скролл содержимого вкладки: окно фиксировано, поэтому
     длинный контент (несколько развёрнутых показателей) скроллится только
     внутри, не растягивая окно. */
  .tab-content-scroll { max-height:480px; overflow-y:auto; }
  .stats-note { font-size:15px; color:__TEXT_COLOR__; opacity:0.55;
    padding:4px 0 8px 0; line-height:1.35; }
  .metric-row { display:flex; justify-content:space-between; align-items:center;
    padding:6px 0; border-bottom:1px solid __BORDER_COLOR__; }
  .metric-row-name { font-size:17px; font-weight:700; color:__TEXT_COLOR__; }
  .metric-row-value { font-size:19px; font-weight:600; color:__TEXT_COLOR__; }
  .metric-row-desc { font-size:15px; color:__TEXT_COLOR__; opacity:0.6; }
  .chart-caption { font-size:13px; color:__TEXT_COLOR__; opacity:0.55;
    text-align:center; margin-top:4px; line-height:1.35; }
  .metric-row { display:block; cursor:pointer; user-select:none;
    padding:8px 0; border-bottom:1px solid __BORDER_COLOR__; }
  .metric-row-header { display:flex; justify-content:space-between; align-items:center; }
  .metric-row-detail { display:none; padding-top:8px; }
  .metric-row.expanded .metric-row-detail { display:block; }
  .summary-tab-content { display:flex; flex-direction:column;
    justify-content:center; align-items:center; min-height:100%; }
  .summary-score { font-size:64px; font-weight:800; margin:8px 0; }
  .summary-comment { font-size:19px; color:__TEXT_COLOR__; line-height:1.45; margin:8px 16px; }
  .summary-compare { font-size:16px; color:__TEXT_COLOR__; opacity:0.65; margin-top:8px; }
  .summary-recommendations { margin:12px 16px; text-align:left; }
  .summary-recommendations-title { font-size:17px; font-weight:700; color:__TEXT_COLOR__; margin-bottom:6px; }
  .summary-recommendations-list { padding-left:18px; margin:0; }
  .summary-recommendations-list li { font-size:16px; color:__TEXT_COLOR__; line-height:1.4; margin-bottom:4px; }
  .summary-recommendations-empty { font-size:16px; color:__TEXT_COLOR__; opacity:0.7; margin:12px 16px; }
  /* Экран статистики — шире, чем простой диалог */
  .stats-screen .bubble-wrapper { max-width:720px; }
  .stats-screen .bubble { max-width:720px; }
  .stats-screen .bottom-area { max-width:720px; }
</style>
<script>
function toggleMetricRow(el) { el.classList.toggle('expanded'); }
</script></head>
<body class="__BODY_CLASS__">
  <div class="bubble-wrapper">
    <div class="bubble">
      __DECK_TITLE_BLOCK__
      <div class="tabs">
        <button class="tab-btn __TAB_MAIN_ACTIVE__"
         onclick="pycmd('anker:stats_tab_main')">Главное</button>
        <button class="tab-btn __TAB_SUMMARY_ACTIVE__"
         onclick="pycmd('anker:stats_tab_summary')">Итог</button>
        <button class="tab-btn __TAB_ALL_ACTIVE__"
         onclick="pycmd('anker:stats_tab_all')">Все показатели</button>
      </div>
      <div class="tab-content-scroll">__TAB_CONTENT__</div>
    </div>
  </div>
  <div class="bottom-area">
    <div class="character"><img src="__IMAGE_URL__" alt="Anker"></div>
    <div class="buttons">
      <button class="btn primary" onclick="pycmd('anker:stats_back')">Назад</button>
    </div>
  </div>
</body></html>"""


# ── Цветовая шкала для значений метрик ──────────────────────────────────────

def _grade_color(
    value: Optional[float],
    thresholds: List[float],
    colors: List[str],
    invert: bool = False,
) -> str:
    """
    Возвращает CSS-цвет для значения метрики на основе порогов.

    thresholds — границы диапазонов по возрастанию, colors — цвета для каждого
    диапазона (len(colors) == len(thresholds) + 1). invert=True переворачивает
    направление (когда МЕНЬШЕ значит ЛУЧШЕ, например для доли ошибок).
    """
    if value is None:
        return "__TEXT_COLOR__"
    idx = 0
    for t in thresholds:
        if value >= t:
            idx += 1
        else:
            break
    if invert:
        idx = len(colors) - 1 - idx
    return colors[idx]


# Палитра: плохо → ближе к плохому → средне → ближе к хорошему → хорошо
_GRADE_COLORS = ["#d13438", "#e8833a", "#e8c93a", "#8dbf3f", "#107c10"]

# Пороги для каждой метрики (согласованы с _xxx_explanation)
_METRIC_THRESHOLDS: Dict[str, tuple] = {
    "true_retention":        ([0.50, 0.70, 0.85, 0.95], False),
    "new_card_retention":    ([0.50, 0.70, 0.85, 0.95], False),
    "avg_difficulty":        ([3.0, 5.0, 7.0, 9.0], True),
    "avg_stability":         ([3.0, 10.0, 20.0, 40.0], False),
    "low_stability_ratio":   ([0.10, 0.20, 0.30, 0.40], True),
    "actual_vs_predicted":   ([0.90, 1.10, 1.30, 1.50], True),
    "avg_time_growth":       ([0.90, 1.10, 1.30, 1.50], True),
    "consistency":           ([0.30, 0.50, 0.70, 0.90], False),
    "relearning_stuck":      ([2.0, 5.0, 10.0, 20.0], True),
    "again_rate_young":      ([0.05, 0.10, 0.20, 0.30], True),
    "again_rate_mature":     ([0.05, 0.10, 0.20, 0.30], True),
}


# Готовые формулировки рекомендаций по метрикам (пункт 6 ТЗ).
# Ключ совпадает с ключом метрики в _METRIC_THRESHOLDS.
_RECOMMENDATION_TEXTS: Dict[str, str] = {
    "true_retention": "Уделяй чуть больше внимания повторениям — вспоминаемость сейчас ниже, чем хотелось бы.",
    "new_card_retention": "Не спеши добавлять много новых карточек сразу — дай свежим словам закрепиться получше.",
    "avg_difficulty": "Многие карточки объективно трудные — попробуй снизить темп добавления новых на время.",
    "avg_stability": "Часть материала пока нестабильна в памяти — не лишним будет вернуться к нему через повторение.",
    "low_stability_ratio": "Заметная доля карточек ещё не закрепилась прочно — им нужно больше времени и внимания.",
    "actual_vs_predicted": "Нагрузка ощутимо выше, чем задумано, — стоит пересмотреть лимит новых карточек.",
    "avg_time_growth": "На карточки уходит больше времени, чем раньше, — возможно, стоит сделать паузу или снизить темп.",
    "consistency": "Занятия проходят нерегулярно — постарайся заниматься примерно в одном ритме, это помогает лучше запоминать.",
    "relearning_stuck": "Немало карточек застряло в переучивании — стоит отдельно поработать именно над ними.",
}


def _metric_color(key: str, value: Optional[float]) -> str:
    """Возвращает цвет для значения метрики по её ключу."""
    entry = _METRIC_THRESHOLDS.get(key)
    if entry is None:
        return "__TEXT_COLOR__"
    thresholds, invert = entry
    return _grade_color(value, list(thresholds), _GRADE_COLORS, invert)


# ── Определения метрик для вкладки «Главное» ────────────────────────────────

# (key, name, explain_fn, suffix)
_MAIN_METRIC_DEFS: List[tuple] = [
    ("true_retention", "Вспоминаемость", _retention_explanation, "%"),
    ("new_card_retention", "Новые карточки", _new_card_retention_explanation, "%"),
    ("avg_difficulty", "Средняя сложность", _difficulty_explanation, ""),
    ("avg_stability", "Средняя стабильность", _stability_explanation, " дн."),
    ("low_stability_ratio", "Доля нестабильных", _low_stability_explanation, "%"),
    ("actual_vs_predicted", "Факт vs прогноз", _load_ratio_explanation, ""),
    ("avg_time_growth", "Время на карточку", _time_growth_explanation, ""),
    ("consistency", "Регулярность", _consistency_explanation, "%"),
    ("relearning_stuck", "Застрявшие", _stuck_explanation, ""),
]


def _resolve_metric_value(metrics: Dict[str, Any], key: str) -> Optional[float]:
    """Извлекает значение метрики, в т.ч. again_rate из button_ratio."""
    if key in ("again_rate_young", "again_rate_mature"):
        maturity = "young" if key == "again_rate_young" else "mature"
        ratio_dict = metrics.get(f"button_ratio_{maturity}")
        if ratio_dict and isinstance(ratio_dict, dict):
            return ratio_dict.get("again")
        return None
    return metrics.get(key)


def _build_main_tab_content(
    metrics: Dict[str, Any],
    decision_action: str,
    is_anomaly: bool,
    metric_weights: Dict[str, float] | None = None,
) -> str:
    """
    Собирает HTML для вкладки «Главное» — 3-5 самых значимых метрик,
    отсортированных по весу из конфига.
    """
    if metric_weights is None:
        metric_weights = {}

    # Собираем доступные метрики с их весами
    scored: List[tuple] = []
    for key, name, explain_fn, suffix in _MAIN_METRIC_DEFS:
        value = _resolve_metric_value(metrics, key)
        if value is None:
            continue
        weight = metric_weights.get(key, 0.0)
        scored.append((weight, key, name, explain_fn, suffix, value))

    # При anomaly добавляем again_rate как приоритетную
    if is_anomaly:
        for maturity in ("young", "mature"):
            ratio_dict = metrics.get(f"button_ratio_{maturity}")
            if ratio_dict and isinstance(ratio_dict, dict):
                again = ratio_dict.get("again")
                if again is not None:
                    weight = metric_weights.get(f"again_rate_{maturity}", 0.05) + 0.10  # бонус за anomaly
                    scored.append((
                        weight,
                        f"again_rate_{maturity}",
                        f"Доля ошибок ({'новые' if maturity == 'young' else 'зрелые'})",
                        _again_rate_explanation,
                        "%",
                        again,
                    ))

    # Сортируем по весу, берём топ-5
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:5]

    parts: List[str] = []
    for _, key, name, explain_fn, suffix, value in top:
        if suffix == "%":
            display = f"{int(value * 100)}%"
        elif suffix == " дн.":
            display = f"{value:.1f}{suffix}"
        else:
            display = f"{value:.1f}" if isinstance(value, float) else str(value)

        svg = _metric_visualization_svg(key, metrics, value)
        explanation = explain_fn(value)
        value_color = _metric_color(key, value)

        parts.append('<div class="stats-container">')
        parts.append(f'<div class="metric-title">{name}</div>')
        parts.append(f'<div class="metric-value" style="color:{value_color};">{display}</div>')
        if svg:
            parts.append(svg)
        parts.append(f'<div class="metric-explanation">{explanation}</div>')
        parts.append('</div>')

    return "\n".join(parts) if parts else '<div class="stats-container"><div class="metric-title">Нет данных</div></div>'


def _metric_detail_html(
    key: str,
    metrics: Dict[str, Any],
    value: Optional[float],
    caption: Optional[str] = None,
) -> str:
    """
    Возвращает HTML детализации (визуализации) для сворачиваемого блока
    конкретной метрики, либо пустую строку, если визуализировать нечего.
    При наличии caption — выводит его под визуализацией.
    """
    svg = _metric_visualization_svg(key, metrics, value)
    if not svg:
        return ""
    parts = [svg]
    if caption:
        parts.append(f'<div class="chart-caption">{caption}</div>')
    return f'<div class="metric-row-detail">{"".join(parts)}</div>'


def _build_all_tab_content(metrics: Dict[str, Any], period: int = 7) -> str:
    """Собирает HTML для вкладки «Все показатели»."""
    rows_def = [
        ("Вспоминаемость", "true_retention", _retention_explanation, "%",
         "На графике — вспоминаемость по дням, в процентах."),
        ("Новые карточки", "new_card_retention", _new_card_retention_explanation, "%",
         "Шкала показывает долю успешно вспомненных новых карточек (0–100%). "
         "Считается за последние 30 дней — не зависит от периода анализа."),
        ("Средняя сложность", "avg_difficulty", _difficulty_explanation, "",
         "Шкала показывает текущий уровень сложности от 0 до 10."),
        ("Средняя стабильность", "avg_stability", _stability_explanation, " дн.",
         "Шкала показывает стабильность карточек — количество дней, за которое "
         "вспоминаемость падает до 90%."),
        ("Доля нестабильных", "low_stability_ratio", _low_stability_explanation, "%",
         "Показывает, какая доля карточек ещё нестабильна (могут забыться быстро)."),
        ("Факт vs прогноз", "actual_vs_predicted", _load_ratio_explanation, "",
         "Сравнение количества повторений: ожидалось vs фактически было пройдено."),
        ("Время на карточку", "avg_time_growth", _time_growth_explanation, "",
         "Сравнение среднего времени на карточку: раньше vs сейчас (в секундах)."),
        ("Регулярность", "consistency", _consistency_explanation, "%",
         "На графике — количество карточек, пройденных в этот день."),
        ("Застрявшие карточки", "relearning_stuck", _stuck_explanation, "",
         "На графике — количество карточек, застрявших в переучивании, по дням."),
    ]

    note = (
        f"Ниже представлены показатели за {period} дн. "
        "Они могут отличаться от общей статистики в Anki (Stats)."
    )
    parts = [
        f'<div class="stats-note">{note}</div>',
        '<div class="all-metrics">',
    ]
    for name, key, explain_fn, suffix, caption in rows_def:
        value = metrics.get(key)
        if value is None:
            display = "—"
        elif suffix == "%":
            display = f"{int(value * 100)}%"
        elif suffix == " дн.":
            display = f"{value:.1f}{suffix}"
        else:
            display = f"{value:.1f}" if isinstance(value, float) else str(value)

        desc = explain_fn(value)
        color = _metric_color(key, value)

        # Визуализация для сворачиваемого блока (sparkline/gauge/donut/столбцы)
        detail_html = _metric_detail_html(key, metrics, value, caption)

        parts.append(
            f'<div class="metric-row" onclick="toggleMetricRow(this)">'
            f'<div class="metric-row-header">'
            f'<div><div class="metric-row-name">{name}</div>'
            f'<div class="metric-row-desc">{desc}</div></div>'
            f'<div class="metric-row-value" style="color:{color};">{display}</div>'
            f'</div>'
            f'{detail_html}'
            f'</div>'
        )
    parts.append('</div>')
    return "\n".join(parts)


def _score_components(
    metrics: Dict[str, Any],
    metric_weights: Dict[str, float] | None = None,
) -> Tuple[float, List[Tuple[str, float, float]]]:
    """
    Возвращает (score, [(metric_key, normalized, weight), ...]).

    score — итоговая оценка 1-10; normalized — положение значения метрики
    на шкале 0..1 (0 = плохо, 1 = хорошо). Единый расчёт используется и для
    оценки на вкладке «Итог», и для блока рекомендаций.
    """
    if metric_weights is None:
        metric_weights = {}
    total_weight = 0.0
    weighted_sum = 0.0
    scored: List[Tuple[str, float, float]] = []
    for key, (thresholds, invert) in _METRIC_THRESHOLDS.items():
        value = metrics.get(key)
        if value is None:
            continue
        weight = metric_weights.get(key, 0.0)
        if weight <= 0:
            continue
        idx = 0
        for t in thresholds:
            if value >= t:
                idx += 1
            else:
                break
        if invert:
            idx = len(thresholds) - idx
        normalized = idx / len(thresholds)
        weighted_sum += normalized * weight
        total_weight += weight
        scored.append((key, normalized, weight))

    score = 1.0 + (weighted_sum / total_weight) * 9.0 if total_weight > 0 else 5.0
    return score, scored


def compute_summary_score(
    metrics: Dict[str, Any],
    metric_weights: Dict[str, float] | None = None,
) -> float:
    """Итоговая оценка 1-10 по метрикам и их весам (для выбора лица маскота)."""
    score, _ = _score_components(metrics, metric_weights)
    return score


def summary_image_for_score(score: float) -> str:
    """Имя файла изображения персонажа по итоговой оценке 1-10."""
    if score < 3.0:
        return "sad.png"
    if score < 5.0:
        return "worried.png"
    if score < 7.0:
        return "neutral.png"
    if score < 8.5:
        return "enthusiastic.png"
    return "prouded.png"


def _build_summary_tab_content(
    metrics: Dict[str, Any],
    metric_weights: Dict[str, float] | None,
    last_summary_score: Dict[str, Any] | None,
) -> str:
    """Собирает HTML для вкладки «Итог» — оценка 1-10 + сравнение с прошлым."""
    score, scored = _score_components(metrics, metric_weights)

    score_display = f"{score:.1f}"
    score_color = _grade_color(score / 10.0, [0.3, 0.5, 0.7, 0.9], _GRADE_COLORS, False)

    # Комментарий по диапазону — описывает только текущее состояние,
    # без намёков на тренд (тренд покрывает блок сравнения с прошлым ниже).
    if score < 3.0:
        comment = "Сейчас тебе непросто — материал плохо закрепляется, и это чувствуется. Ничего страшного, бывает у всех. Стоит притормозить и меньше нагружать себя, пока не наверстаешь."
    elif score < 5.0:
        comment = "Результаты сейчас ниже обычного — часть материала выветривается быстрее, чем хотелось бы. Стоит немного сбавить темп и уделить время повторению того, что уже проходил."
    elif score < 7.0:
        comment = "Ты держишься в целом нормально — ничего критичного, но и без большого запаса прочности. Есть куда расти, если добавить чуть больше внимания к повторениям."
    elif score < 8.5:
        comment = "У тебя хорошо получается — материал закрепляется уверенно, сбоев почти нет. Продолжай в том же духе."
    else:
        comment = "Отличный результат — ты закрепляешь материал очень уверенно и стабильно. Можно даже немного ускориться, если хочется двигаться быстрее."

    # Сравнение с прошлым
    compare_html = ""
    if last_summary_score and last_summary_score.get("value") is not None:
        prev = last_summary_score["value"]
        diff = score - prev
        if diff > 0.5:
            compare_html = f"Стало заметно лучше, чем в прошлый раз (было {prev:.1f}/10)"
        elif diff < -0.5:
            compare_html = f"Немного просело по сравнению с прошлым разом (было {prev:.1f}/10)"
        else:
            compare_html = f"Держится примерно на том же уровне (было {prev:.1f}/10)"

    # Блок рекомендаций: топ-3 худших метрик (normalized < 0.5), отсортированных
    # по весу × насколько далеки от хорошего значения.
    weak = [
        (key, normalized, weight)
        for key, normalized, weight in scored
        if normalized < 0.5 and key in _RECOMMENDATION_TEXTS
    ]
    weak.sort(key=lambda x: x[2] * (0.5 - x[1]), reverse=True)
    weak = weak[:3]

    if weak:
        items = "\n".join(
            f"<li>{_RECOMMENDATION_TEXTS[key]}</li>" for key, _, _ in weak
        )
        recommendations_html = (
            '<div class="summary-recommendations">'
            '<div class="summary-recommendations-title">Что можно улучшить</div>'
            f'<ul class="summary-recommendations-list">{items}</ul>'
            '</div>'
        )
    else:
        recommendations_html = (
            '<div class="summary-recommendations-empty">'
            'Явных слабых мест не видно — можно просто продолжать в том же духе.'
            '</div>'
        )

    parts = [
        '<div class="summary-tab-content">',
        '<div class="stats-container">',
        f'<div class="summary-score" style="color:{score_color};">{score_display}<span style="font-size:26px;">/10</span></div>',
        f'<div class="summary-comment">{comment}</div>',
    ]
    if compare_html:
        parts.append(f'<div class="summary-compare">{compare_html}</div>')
    parts.append(recommendations_html)
    parts.append('</div>')
    parts.append('</div>')
    return "\n".join(parts)


def build_stats_tabbed_html(
    metrics: Dict[str, Any],
    decision_action: str,
    is_anomaly: bool,
    is_stable: bool,
    active_tab: str,
    image_filename: str,
    theme_colors: Dict[str, str] | None = None,
    metric_weights: Dict[str, float] | None = None,
    last_summary_score: Dict[str, Any] | None = None,
    deck_name: Optional[str] = None,
    period: Optional[int] = None,
) -> str:
    """
    Собирает HTML экрана обоснования с вкладками «Итог», «Главное» и «Все показатели».

    Args:
        metrics: словарь метрик из metrics.collect_metrics().
        decision_action: "increase"/"decrease"/"hold".
        is_anomaly: флаг anomaly-сценария.
        is_stable: флаг стабильной серии.
        active_tab: "summary", "main" или "all".
        image_filename: изображение маскота.
        theme_colors: цвета темы.
        metric_weights: веса метрик из конфига.
        last_summary_score: предыдущая оценка для сравнения {"value": 7.3, "date": "..."}.
        deck_name: имя колоды (для заголовка экрана статистики).
        period: период анализа в днях (для подписи во вкладке «Все показатели»).
    """
    if theme_colors is None:
        theme_colors = DEFAULT_THEME_COLORS
    css = _apply_theme_colors(SHARED_DIALOG_CSS, theme_colors)

    tab_summary_active = "active" if active_tab == "summary" else ""
    tab_main_active = "active" if active_tab == "main" else ""
    tab_all_active = "active" if active_tab == "all" else ""

    if active_tab == "all":
        content = _build_all_tab_content(metrics, period or 7)
    elif active_tab == "main":
        content = _build_main_tab_content(metrics, decision_action, is_anomaly, metric_weights)
    else:
        content = _build_summary_tab_content(metrics, metric_weights, last_summary_score)

    deck_title_block = f'<div class="stats-deck-title">{deck_name}</div>' if deck_name else ""

    return (
        STATS_TABBED_TEMPLATE
        .replace("__CSS__", css)
        .replace("__BODY_CLASS__", "stats-screen")
        .replace("__TAB_SUMMARY_ACTIVE__", tab_summary_active)
        .replace("__TAB_MAIN_ACTIVE__", tab_main_active)
        .replace("__TAB_ALL_ACTIVE__", tab_all_active)
        .replace("__TAB_CONTENT__", content)
        .replace("__DECK_TITLE_BLOCK__", deck_title_block)
        .replace("__IMAGE_URL__", image_data_uri(image_filename))
        .replace("__TEXT_COLOR__", theme_colors.get("text", DEFAULT_THEME_COLORS["text"]))
        .replace("__BORDER_COLOR__", theme_colors.get("border", DEFAULT_THEME_COLORS["border"]))
    )
