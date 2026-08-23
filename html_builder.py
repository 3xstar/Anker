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
from typing import Any, Dict, List, Optional


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
    justify-content: center;
    min-height: 100vh;
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
    color: #1f1f23;
    background: #ffffff;
    border: 1px solid #c8c8ce;
    border-radius: 14px;
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
        return "Недостаточно данных о времени ответа."
    if growth > 1.3:
        return "Время на карточку растёт — признак растущей когнитивной нагрузки."
    if growth > 1.1:
        return "Время на карточку немного выросло."
    if growth > 0.9:
        return "Время на карточку стабильно."
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
    flex:1; padding:8px 0; font-size:13px; font-family:inherit;
    background:#ffffff; color:#1f1f23; border:1px solid #c8c8ce;
    cursor:pointer; text-align:center; transition:background 0.15s;
  }
  .tab-btn:first-child { border-radius:10px 0 0 10px; }
  .tab-btn:last-child { border-radius:0 10px 10px 0; }
  .tab-btn.active { background:#0078d4; border-color:#0067b8; color:#ffffff; font-weight:600; }
  .stats-container { text-align:center; padding:10px 0; }
  .metric-name { font-size:13px; color:__TEXT_COLOR__; opacity:0.7; margin-bottom:4px; }
  .metric-value { font-size:36px; font-weight:700; color:__TEXT_COLOR__; margin-bottom:4px; }
  .metric-explanation { font-size:13px; color:__TEXT_COLOR__; opacity:0.8;
    line-height:1.45; margin:8px 16px; }
  .all-metrics { text-align:left; max-height:280px; overflow-y:auto; }
  .stats-note { font-size:11px; color:__TEXT_COLOR__; opacity:0.55;
    padding:4px 0 8px 0; line-height:1.35; }
  .metric-row { display:flex; justify-content:space-between; align-items:center;
    padding:6px 0; border-bottom:1px solid __BORDER_COLOR__; }
  .metric-row-name { font-size:13px; color:__TEXT_COLOR__; }
  .metric-row-value { font-size:14px; font-weight:600; color:__TEXT_COLOR__; }
  .metric-row-desc { font-size:11px; color:__TEXT_COLOR__; opacity:0.6; }
  .metric-row { cursor:pointer; user-select:none; }
  .metric-row-detail { display:none; padding-top:6px; }
  .metric-row.expanded .metric-row-detail { display:block; }
</style>
<script>
function toggleMetricRow(el) { el.classList.toggle('expanded'); }
</script></head>
<body>
  <div class="bubble-wrapper">
    <div class="bubble">
      <div class="tabs">
        <button class="tab-btn __TAB_MAIN_ACTIVE__"
         onclick="pycmd('anker:stats_tab_main')">Главное</button>
        <button class="tab-btn __TAB_ALL_ACTIVE__"
         onclick="pycmd('anker:stats_tab_all')">Все показатели</button>
      </div>
      __TAB_CONTENT__
    </div>
  </div>
  <div class="bottom-area">
    <div class="character"><img src="__IMAGE_URL__" alt="Anker"></div>
    <div class="buttons">
      <button class="btn primary" onclick="pycmd('anker:stats_back')">Назад</button>
    </div>
  </div>
</body></html>"""


# ── Определения метрик для вкладки «Главное» ────────────────────────────────

# (key, name, explain_fn, suffix, daily_series_key, color)
_MAIN_METRIC_DEFS: List[tuple] = [
    ("true_retention_14d", "Вспоминаемость", _retention_explanation, "%", "daily_retention_14d", "#0078d4"),
    ("true_retention_7d", "Вспоминаемость (7 дн.)", _retention_explanation, "%", None, "#0078d4"),
    ("new_card_retention", "Новые карточки", _new_card_retention_explanation, "%", None, "#107c10"),
    ("avg_difficulty", "Средняя сложность", _difficulty_explanation, "", None, "#d13438"),
    ("avg_stability", "Средняя стабильность", _stability_explanation, " дн.", None, "#0078d4"),
    ("low_stability_ratio", "Доля нестабильных", _low_stability_explanation, "%", None, "#d13438"),
    ("actual_vs_predicted", "Факт vs прогноз", _load_ratio_explanation, "", None, "#0078d4"),
    ("avg_time_growth", "Время на карточку", _time_growth_explanation, "", None, "#d13438"),
    ("consistency", "Регулярность", _consistency_explanation, "%", None, "#0078d4"),
    ("relearning_stuck", "Застрявшие", _stuck_explanation, "", None, "#d13438"),
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
    for key, name, explain_fn, suffix, daily_key, color in _MAIN_METRIC_DEFS:
        value = _resolve_metric_value(metrics, key)
        if value is None:
            continue
        weight = metric_weights.get(key, 0.0)
        scored.append((weight, key, name, explain_fn, suffix, daily_key, color, value))

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
                        "daily_again_rate_14d",
                        "#d13438",
                        again,
                    ))

    # Сортируем по весу, берём топ-5
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:5]

    parts: List[str] = []
    for _, key, name, explain_fn, suffix, daily_key, color, value in top:
        if suffix == "%":
            display = f"{int(value * 100)}%"
        elif suffix == " дн.":
            display = f"{value:.1f}{suffix}"
        else:
            display = f"{value:.1f}" if isinstance(value, float) else str(value)

        daily = metrics.get(daily_key, []) if daily_key else []
        sparkline = build_sparkline_svg(daily, color=color) if daily else ""
        explanation = explain_fn(value)

        parts.append('<div class="stats-container">')
        parts.append(f'<div class="metric-name">{name}</div>')
        parts.append(f'<div class="metric-value">{display}</div>')
        if sparkline:
            parts.append(sparkline)
        parts.append(f'<div class="metric-explanation">{explanation}</div>')
        parts.append('</div>')

    return "\n".join(parts) if parts else '<div class="stats-container"><div class="metric-name">Нет данных</div></div>'


def _build_all_tab_content(metrics: Dict[str, Any]) -> str:
    """Собирает HTML для вкладки «Все показатели»."""
    rows_def = [
        ("Вспоминаемость (7 дн.)", "true_retention_7d", _retention_explanation, "%", None),
        ("Вспоминаемость (14 дн.)", "true_retention_14d", _retention_explanation, "%", "daily_retention_14d"),
        ("Новые карточки", "new_card_retention", _new_card_retention_explanation, "%", None),
        ("Средняя сложность", "avg_difficulty", _difficulty_explanation, "", None),
        ("Средняя стабильность", "avg_stability", _stability_explanation, " дн.", None),
        ("Доля нестабильных", "low_stability_ratio", _low_stability_explanation, "%", None),
        ("Факт vs прогноз", "actual_vs_predicted", _load_ratio_explanation, "", None),
        ("Время на карточку", "avg_time_growth", _time_growth_explanation, "", None),
        ("Регулярность", "consistency", _consistency_explanation, "%", None),
        ("Застрявшие карточки", "relearning_stuck", _stuck_explanation, "", None),
    ]

    parts = [
        '<div class="stats-note">Показатели ниже — за последние 7–14 дней, а не за всё время. Поэтому они могут отличаться от общей статистики в Anki (Stats).</div>',
        '<div class="all-metrics">',
    ]
    for name, key, explain_fn, suffix, daily_key in rows_def:
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

        # Sparkline для сворачиваемого блока
        sparkline_html = ""
        if daily_key:
            daily = metrics.get(daily_key, [])
            if daily:
                sparkline_html = build_sparkline_svg(daily)

        detail_html = ""
        if sparkline_html:
            detail_html = f'<div class="metric-row-detail">{sparkline_html}</div>'

        parts.append(
            f'<div class="metric-row" onclick="toggleMetricRow(this)">'
            f'<div><div class="metric-row-name">{name}</div>'
            f'<div class="metric-row-desc">{desc}</div></div>'
            f'<div class="metric-row-value">{display}</div>'
            f'{detail_html}'
            f'</div>'
        )
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
) -> str:
    """
    Собирает HTML экрана обоснования с вкладками «Главное» и «Все показатели».

    Args:
        metrics: словарь метрик из metrics.collect_metrics().
        decision_action: "increase"/"decrease"/"hold".
        is_anomaly: флаг anomaly-сценария.
        is_stable: флаг стабильной серии.
        active_tab: "main" или "all".
        image_filename: изображение маскота.
        theme_colors: цвета темы.
        metric_weights: веса метрик из конфига для сортировки на вкладке «Главное».
    """
    if theme_colors is None:
        theme_colors = DEFAULT_THEME_COLORS
    css = _apply_theme_colors(SHARED_DIALOG_CSS, theme_colors)

    tab_main_active = "active" if active_tab == "main" else ""
    tab_all_active = "active" if active_tab == "all" else ""

    if active_tab == "all":
        content = _build_all_tab_content(metrics)
    else:
        content = _build_main_tab_content(metrics, decision_action, is_anomaly, metric_weights)

    return (
        STATS_TABBED_TEMPLATE
        .replace("__CSS__", css)
        .replace("__TAB_MAIN_ACTIVE__", tab_main_active)
        .replace("__TAB_ALL_ACTIVE__", tab_all_active)
        .replace("__TAB_CONTENT__", content)
        .replace("__IMAGE_URL__", image_data_uri(image_filename))
        .replace("__TEXT_COLOR__", theme_colors.get("text", DEFAULT_THEME_COLORS["text"]))
        .replace("__BORDER_COLOR__", theme_colors.get("border", DEFAULT_THEME_COLORS["border"]))
    )
