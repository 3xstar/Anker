"""
test_html_builder.py — тесты для html_builder.py (чистая генерация HTML).

Запуск: python -m pytest tests/test_html_builder.py -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import html_builder as hb


# ── Вспомогательные ────────────────────────────────────────────────────────

def make_buttons(count: int):
    """Создаёт список кнопок с предсказуемыми label/action."""
    return [
        {
            "label": f"Кнопка {i}",
            "action": f"action_{i}",
            "primary": (i == 0),
        }
        for i in range(count)
    ]


# ── Тесты: image_data_uri ──────────────────────────────────────────────────

def test_image_data_uri_returns_base64():
    uri = hb.image_data_uri("neutral.png")
    assert uri.startswith("data:image/png;base64,")
    assert len(uri) > len("data:image/png;base64,")


def test_image_data_uri_missing_file_returns_empty():
    assert hb.image_data_uri("nonexistent.png") == ""


def test_log_error_writes_without_crashing():
    import log
    log.log_error("test_context", ValueError("boom"))
    # Главный контракт: логирование не должно само падать.


def test_font_data_uri_returns_base64():
    uri = hb._font_data_uri("nunito-400.woff2")
    assert uri.startswith("data:font/woff2;base64,")
    assert len(uri) > len("data:font/woff2;base64,")


def test_font_data_uri_missing_file_returns_empty():
    assert hb._font_data_uri("nonexistent.woff2") == ""


def test_font_faces_css_contains_nunito():
    css = hb._font_faces_css()
    assert "@font-face" in css
    assert "Nunito" in css
    assert "data:font/woff2;base64," in css


def test_dialog_html_embeds_nunito_font():
    html = hb.build_dialog_html("neutral.png", "msg", make_buttons(1))
    assert "@font-face" in html
    assert "'Nunito'" in html
    assert "data:font/woff2;base64," in html


# ── Тесты: build_buttons_html ──────────────────────────────────────────────

def test_build_buttons_html_empty():
    assert hb.build_buttons_html([]) == ""


def test_build_buttons_html_single():
    html = hb.build_buttons_html([{"label": "Да", "action": "yes"}])
    assert "Да" in html
    assert "anker:yes" in html


def test_build_buttons_html_primary_class():
    html = hb.build_buttons_html([{"label": "Да", "action": "yes", "primary": True}])
    assert "btn primary" in html


# ── Тесты: build_dialog_html ───────────────────────────────────────────────

def test_all_six_scenarios_generate_without_error():
    images = [
        "neutral.png",
        "worried.png",
        "understanding.png",
        "sad.png",
        "enthusiastic.png",
        "prouded.png",
    ]
    for img in images:
        html = hb.build_dialog_html(img, "Тестовое сообщение", make_buttons(2))
        assert isinstance(html, str)
        assert len(html) > 0
        assert "data:image/png;base64," in html


def test_message_and_image_are_substituted():
    html = hb.build_dialog_html("neutral.png", "Привет, Anker!", make_buttons(1))
    assert "Привет, Anker!" in html
    assert "data:image/png;base64," in html  # картинка встроена как data URI


def test_four_buttons_generate_without_error():
    html = hb.build_dialog_html("neutral.png", "msg", make_buttons(4))
    assert "Кнопка 0" in html
    assert "Кнопка 3" in html
    assert "action_0" in html
    assert "action_3" in html


def test_special_characters_in_message_do_not_break():
    message = 'Фигурные {скобки} и "двойные" и \'одинарные\' кавычки'
    html = hb.build_dialog_html("neutral.png", message, make_buttons(1))
    # Подстановка не должна ломаться и должна сохранить текст как есть
    assert message in html


def test_no_placeholder_markers_remain():
    html = hb.build_dialog_html("neutral.png", "msg", make_buttons(2))
    assert "__CSS__" not in html
    assert "__MESSAGE__" not in html
    assert "__IMAGE_URL__" not in html
    assert "__BUTTONS_HTML__" not in html
    assert "__STATS_BUTTON_LABEL__" not in html


def test_dialog_button_default_label():
    html = hb.build_dialog_html("neutral.png", "msg", make_buttons(1))
    assert "Моя статистика" in html


def test_dialog_button_dynamic_label():
    html = hb.build_dialog_html(
        "neutral.png", "msg", make_buttons(1), deck_name="Английский", period=7
    )
    assert "Статистика Английский (7 дн.)" in html
    assert "Моя статистика" not in html


def test_shared_css_uses_anki_palette():
    html = hb.build_dialog_html("neutral.png", "msg", make_buttons(1))
    # Старая бежевая палитра не должна встречаться
    assert "#f5f0eb" not in html
    assert "#d4c5b9" not in html
    assert "#e8dcc8" not in html
    # Новая палитра в духе Anki должна присутствовать
    assert "#f5f5f7" in html
    assert "#0078d4" in html


# ── Тесты: build_day_picker_html ───────────────────────────────────────────

def test_day_picker_html_substitutes_values():
    checkboxes = '<input type="checkbox" id="day_1" checked> Пн'
    html = hb.build_day_picker_html("neutral.png", "Выберите дни", checkboxes)
    assert "Выберите дни" in html
    assert checkboxes in html
    assert "data:image/png;base64," in html


def test_day_picker_html_no_markers_remain():
    html = hb.build_day_picker_html("neutral.png", "msg", "")
    assert "__CSS__" not in html
    assert "__MESSAGE__" not in html
    assert "__IMAGE_URL__" not in html
    assert "__CHECKBOXES_HTML__" not in html


def test_day_picker_html_uses_anki_palette():
    html = hb.build_day_picker_html("neutral.png", "msg", "")
    assert "#f5f0eb" not in html
    assert "#d4c5b9" not in html
    assert "#e8dcc8" not in html
    assert "#f5f5f7" in html
    assert "#0078d4" in html


# ── Тесты: build_stats_tabbed_html ─────────────────────────────────────────

def make_test_metrics():
    """Создаёт словарь метрик для тестов."""
    return {
        "true_retention": 0.78,
        "new_card_retention": 0.75,
        "button_ratio_young": {"again": 0.12, "hard": 0.30, "good": 0.48, "easy": 0.10},
        "button_ratio_mature": {"again": 0.10, "hard": 0.25, "good": 0.55, "easy": 0.10},
        "avg_difficulty": 5.5,
        "avg_stability": 8.0,
        "low_stability_ratio": 0.18,
        "actual_vs_predicted": 1.1,
        "avg_time_growth": 1.05,
        "consistency": 0.65,
        "relearning_stuck": 4,
        "daily_retention": [("15.08", 0.80), ("16.08", 0.78)],
        "daily_again_rate": [("15.08", 0.10), ("16.08", 0.12)],
    }


def test_stats_tabbed_main_tab():
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="decrease",
        is_anomaly=False,
        is_stable=False,
        active_tab="main",
        image_filename="neutral.png",
    )
    assert "Главное" in html
    assert "Все показатели" in html
    assert "Вспоминаемость" in html
    assert "78%" in html
    assert "data:image/png;base64," in html


def test_stats_tabbed_main_tab_multiple_metrics():
    """Вкладка «Главное» показывает несколько метрик, отсортированных по весу."""
    metrics = make_test_metrics()
    weights = {
        "true_retention": 0.10,
        "new_card_retention": 0.20,
        "avg_difficulty": 0.05,
        "avg_stability": 0.05,
        "low_stability_ratio": 0.05,
        "actual_vs_predicted": 0.05,
        "avg_time_growth": 0.05,
        "consistency": 0.03,
        "relearning_stuck": 0.02,
    }
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="main",
        image_filename="neutral.png",
        metric_weights=weights,
    )
    # Должно быть несколько stats-container блоков
    assert html.count("stats-container") >= 2
    assert "Вспоминаемость" in html
    assert "Новые карточки" in html


def test_stats_tabbed_all_tab_collapsible():
    """Вкладка «Все показатели» содержит сворачиваемые строки."""
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=True,
        active_tab="all",
        image_filename="prouded.png",
    )
    assert "toggleMetricRow" in html
    assert "metric-row-detail" in html
    assert "onclick" in html
    assert "Все показатели" in html
    assert "Вспоминаемость" in html
    assert "Новые карточки" in html
    assert "Средняя сложность" in html
    assert "Регулярность" in html
    assert "Застрявшие карточки" in html
    assert "78%" in html


def test_stats_tabbed_active_class():
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="main",
        image_filename="neutral.png",
    )
    assert 'tab-btn active' in html
    # На вкладке "Все показатели" не должно быть active
    assert html.count('tab-btn active') == 1


def test_stats_tabbed_all_tab_active_class():
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="all",
        image_filename="neutral.png",
    )
    assert 'tab-btn active' in html


def test_stats_tabbed_anomaly_shows_again_rate():
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=True,
        is_stable=False,
        active_tab="main",
        image_filename="worried.png",
    )
    assert "Доля ошибок" in html


def test_stats_tabbed_main_tab_metric_titles_are_headers():
    """Названия показателей во вкладке «Главное» используют класс metric-title."""
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="main",
        image_filename="neutral.png",
    )
    assert 'class="metric-title"' in html
    assert "metric-title" in html
    # CSS-правило для заголовка присутствует
    assert ".stats-container .metric-title" in html


def test_stats_tabbed_summary_tab():
    """Вкладка «Итог» показывает оценку и комментарий."""
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="summary",
        image_filename="neutral.png",
    )
    assert "Итог" in html
    assert "/10" in html
    assert "summary-score" in html


def test_stats_tabbed_tab_order_and_default_active():
    """Вкладки идут «Главное» → «Итог» → «Все показатели», по умолчанию активен «Итог»."""
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="summary",
        image_filename="neutral.png",
    )
    main_pos = html.index('onclick="pycmd(\'anker:stats_tab_main\')"')
    summary_pos = html.index('onclick="pycmd(\'anker:stats_tab_summary\')"')
    all_pos = html.index('onclick="pycmd(\'anker:stats_tab_all\')"')
    assert main_pos < summary_pos < all_pos
    # По умолчанию активна вкладка «Итог» (единственная с классом active)
    assert html.count('class="tab-btn active"') == 1
    assert 'class="tab-btn active"' in html


def test_stats_tabbed_summary_with_compare():
    """Вкладка «Итог» показывает сравнение с прошлым замером."""
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="summary",
        image_filename="neutral.png",
        last_summary_score={"value": 6.0, "date": "2026-08-20"},
    )
    assert "было 6.0/10" in html


def test_stats_tabbed_no_placeholder_markers():
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="main",
        image_filename="neutral.png",
    )
    assert "__CSS__" not in html
    assert "__BODY_CLASS__" not in html
    assert "__TAB_SUMMARY_ACTIVE__" not in html
    assert "__TAB_MAIN_ACTIVE__" not in html
    assert "__TAB_ALL_ACTIVE__" not in html
    assert "__TAB_CONTENT__" not in html
    assert "__IMAGE_URL__" not in html
    assert "__DECK_TITLE_BLOCK__" not in html


def test_stats_tabbed_deck_title():
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="summary",
        image_filename="neutral.png",
        deck_name="Английский",
    )
    assert 'class="stats-deck-title"' in html
    assert "Английский" in html


def test_stats_tabbed_no_deck_title_when_absent():
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="summary",
        image_filename="neutral.png",
    )
    assert '<div class="stats-deck-title">' not in html


def test_stats_tabbed_all_tab_dynamic_period_note():
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="all",
        image_filename="neutral.png",
        period=14,
    )
    assert "за 14 дн." in html
    assert "за всё время" not in html


# ── Тесты: функции пояснений ───────────────────────────────────────────────

def test_retention_explanation_ranges():
    assert "ниже 50%" in hb._retention_explanation(0.30)
    assert "50–70%" in hb._retention_explanation(0.60)
    assert "70–85%" in hb._retention_explanation(0.80)
    assert "выше 85%" in hb._retention_explanation(0.92)
    assert "Недостаточно" in hb._retention_explanation(None)


def test_again_rate_explanation_ranges():
    assert "выше 25%" in hb._again_rate_explanation(0.30)
    assert "15–25%" in hb._again_rate_explanation(0.20)
    assert "8–15%" in hb._again_rate_explanation(0.10)
    assert "ниже 8%" in hb._again_rate_explanation(0.05)
    assert "Недостаточно" in hb._again_rate_explanation(None)


def test_difficulty_explanation_ranges():
    assert "выше 7" in hb._difficulty_explanation(8.0)
    assert "5–7" in hb._difficulty_explanation(6.0)
    assert "ниже 5" in hb._difficulty_explanation(3.0)
    assert "Недостаточно" in hb._difficulty_explanation(None)


def test_stability_explanation_ranges():
    assert "ниже 3" in hb._stability_explanation(2.0)
    assert "3–10" in hb._stability_explanation(5.0)
    assert "выше 10" in hb._stability_explanation(15.0)
    assert "Недостаточно" in hb._stability_explanation(None)


def test_consistency_explanation_ranges():
    assert "низкая" in hb._consistency_explanation(0.2)
    assert "средняя" in hb._consistency_explanation(0.5)
    assert "высокая" in hb._consistency_explanation(0.8)
    assert "Недостаточно" in hb._consistency_explanation(None)


def test_new_card_retention_explanation_ranges():
    assert "тяжело" in hb._new_card_retention_explanation(0.40)
    assert "средне" in hb._new_card_retention_explanation(0.60)
    assert "хорошо" in hb._new_card_retention_explanation(0.80)
    assert "отлично" in hb._new_card_retention_explanation(0.95)
    assert "Недостаточно" in hb._new_card_retention_explanation(None)


# ── Тесты: sparkline ───────────────────────────────────────────────────────

def test_sparkline_empty_on_insufficient_data():
    svg = hb.build_sparkline_svg([("01.01", None), ("02.01", None)])
    assert svg == ""


def test_sparkline_generates_svg():
    data = [("15.08", 0.80), ("16.08", 0.78), ("17.08", 0.85)]
    svg = hb.build_sparkline_svg(data)
    assert "<svg" in svg
    assert "<polyline" in svg
    assert "<circle" in svg


def test_sparkline_single_point_returns_empty():
    svg = hb.build_sparkline_svg([("15.08", 0.80)])
    assert svg == ""


def test_sparkline_draws_value_labels():
    data = [("15.08", 0.80), ("16.08", 0.78), ("17.08", 0.85)]
    svg = hb.build_sparkline_svg(data)
    assert "<text" in svg


def test_sparkline_percent_format():
    data = [("15.08", 0.80), ("16.08", 0.78), ("17.08", 0.85)]
    svg = hb.build_sparkline_svg(data, value_format="percent")
    assert "80%" in svg
    assert "78%" in svg
    assert "85%" in svg


def test_sparkline_number_format():
    data = [("15.08", 4.0), ("16.08", 5.0), ("17.08", 6.5)]
    svg = hb.build_sparkline_svg(data, value_format="number")
    assert ">4<" in svg
    assert ">6.5<" in svg
    assert "%" not in svg


# ── Тесты: build_gauge_svg ─────────────────────────────────────────────────

def test_gauge_none_returns_empty():
    assert hb.build_gauge_svg(None) == ""


def test_gauge_generates_svg():
    svg = hb.build_gauge_svg(5.5)
    assert "<svg" in svg
    assert "<rect" in svg
    assert "<linearGradient" in svg
    assert "5.5" in svg


def test_gauge_clamps_marker_but_shows_actual_value():
    svg = hb.build_gauge_svg(25.0)
    assert "<svg" in svg
    # Подпись показывает фактическое значение, а маркер зажимается к max_value.
    assert "25.0" in svg


def test_gauge_percent_format():
    svg = hb.build_gauge_svg(0.75, min_value=0.0, max_value=1.0, value_format="percent")
    assert "75%" in svg


# ── Тесты: build_donut_svg ─────────────────────────────────────────────────

def test_donut_none_returns_empty():
    assert hb.build_donut_svg(None) == ""


def test_donut_generates_svg():
    svg = hb.build_donut_svg(0.18)
    assert "<svg" in svg
    assert "<circle" in svg
    assert "18%" in svg


def test_donut_clamps_ratio():
    svg = hb.build_donut_svg(1.5)
    assert "<svg" in svg
    assert "100%" in svg


# ── Тесты: build_bar_pair_svg ──────────────────────────────────────────────

def test_bar_pair_both_none_returns_empty():
    assert hb.build_bar_pair_svg("Ожидалось", None, "Фактически", None) == ""


def test_bar_pair_generates_svg():
    svg = hb.build_bar_pair_svg("Ожидалось", 50, "Фактически", 80)
    assert "<svg" in svg
    assert "<rect" in svg
    assert "Ожидалось" in svg
    assert "Фактически" in svg
    assert "50" in svg
    assert "80" in svg


def test_bar_pair_single_value():
    svg = hb.build_bar_pair_svg("Ожидалось", None, "Фактически", 80)
    assert "<svg" in svg
    assert "—" in svg


# ── Тесты: build_bar_chart_svg ─────────────────────────────────────────────

def test_bar_chart_empty_on_no_data():
    assert hb.build_bar_chart_svg([("01.01", None), ("02.01", None)]) == ""


def test_bar_chart_generates_svg():
    data = [("15.08", 153), ("16.08", 139), ("17.08", 147)]
    svg = hb.build_bar_chart_svg(data)
    assert "<svg" in svg
    assert "<rect" in svg
    assert "<text" in svg
    assert "153" in svg
    assert "139" in svg


def test_bar_chart_single_point():
    svg = hb.build_bar_chart_svg([("15.08", 42)])
    assert "<svg" in svg
    assert "42" in svg


# ── Тесты: единая диспетчеризация визуализаций ─────────────────────────────

def test_dispatch_retention_uses_sparkline():
    metrics = make_test_metrics()
    svg = hb._metric_visualization_svg("true_retention", metrics, 0.78)
    assert "<polyline" in svg  # линия, а не столбцы


def test_dispatch_new_cards_uses_gauge_percent():
    metrics = make_test_metrics()
    svg = hb._metric_visualization_svg("new_card_retention", metrics, 0.75)
    assert "linearGradient" in svg
    assert "75%" in svg


def test_dispatch_stability_uses_gauge():
    metrics = make_test_metrics()
    svg = hb._metric_visualization_svg("avg_stability", metrics, 8.0)
    assert "linearGradient" in svg
    assert "8.0" in svg


def test_dispatch_time_uses_bar_pair():
    metrics = make_test_metrics()
    metrics["avg_time_per_card"] = 16.5
    metrics["avg_time_prev"] = 14.5
    svg = hb._metric_visualization_svg("avg_time_growth", metrics, 1.1)
    assert "Раньше" in svg
    assert "Сейчас" in svg
    assert "<rect" in svg


def test_dispatch_consistency_uses_bar_chart():
    metrics = make_test_metrics()
    metrics["daily_review_count"] = [("15.08", 153), ("16.08", 139)]
    svg = hb._metric_visualization_svg("consistency", metrics, 0.65)
    assert "<rect" in svg
    assert "<polyline" not in svg


def test_dispatch_stuck_uses_bar_chart():
    metrics = make_test_metrics()
    metrics["daily_relearning_count"] = [("15.08", 2), ("16.08", 3)]
    svg = hb._metric_visualization_svg("relearning_stuck", metrics, 4)
    assert "<rect" in svg
    assert "<polyline" not in svg


# ── Тесты: визуализации во вкладке «Все показатели» ────────────────────────

def test_all_tab_renders_individual_visualizations():
    metrics = make_test_metrics()
    metrics["actual_vs_predicted_counts"] = {"actual": 80, "predicted": 50}
    metrics["daily_stability"] = [("15.08", 8.0), ("16.08", 9.5)]
    metrics["daily_time"] = [("15.08", 10.0), ("16.08", 12.0)]
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="all",
        image_filename="neutral.png",
    )
    assert "gauge-grad-" in html      # градусник для сложности (уникальный ID)
    assert "linearGradient" in html
    assert "Ожидалось" in html        # парные столбцы для «Факт vs прогноз»
    assert "Фактически" in html
    assert "18%" in html              # donut для доли нестабильных (0.18)


def test_all_tab_renders_chart_captions():
    metrics = make_test_metrics()
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="all",
        image_filename="neutral.png",
    )
    assert "chart-caption" in html
    assert "вспоминаемость по дням" in html
    assert "Считается за последние 30 дней" in html
    assert "уровень сложности от 0 до 10" in html


# ── Тесты: _grade_color ────────────────────────────────────────────────────

def test_grade_color_best():
    assert hb._grade_color(0.95, [0.50, 0.70, 0.85, 0.95], hb._GRADE_COLORS) == "#107c10"


def test_grade_color_worst():
    assert hb._grade_color(0.30, [0.50, 0.70, 0.85, 0.95], hb._GRADE_COLORS) == "#d13438"


def test_grade_color_invert():
    # Для метрик где меньше = лучше (сложность), 9.0 = плохо → красный
    assert hb._grade_color(9.0, [3.0, 5.0, 7.0, 9.0], hb._GRADE_COLORS, invert=True) == "#d13438"
    assert hb._grade_color(2.0, [3.0, 5.0, 7.0, 9.0], hb._GRADE_COLORS, invert=True) == "#107c10"


def test_grade_color_none():
    assert hb._grade_color(None, [0.5, 0.7], ["#a", "#b", "#c"]) == "__TEXT_COLOR__"


def test_metric_color_retention():
    assert hb._metric_color("true_retention", 0.92) == "#8dbf3f"


def test_metric_color_difficulty():
    # Высокая сложность = плохо → красный
    assert hb._metric_color("avg_difficulty", 8.0) == "#e8833a"


# ── Тесты: compute_summary_score ──────────────────────────────────────────

def test_compute_summary_score_no_weights_returns_mid():
    assert hb.compute_summary_score(make_test_metrics(), {}) == 5.0


def test_compute_summary_score_with_weights():
    metrics = {
        "true_retention": 0.90,
        "avg_difficulty": 2.0,
    }
    weights = {"true_retention": 0.5, "avg_difficulty": 0.5}
    score = hb.compute_summary_score(metrics, weights)
    assert 8.0 <= score <= 10.0


# ── Тесты: summary_image_for_score ────────────────────────────────────────

def test_summary_image_for_score_ranges():
    assert hb.summary_image_for_score(1.5) == "sad.png"
    assert hb.summary_image_for_score(2.9) == "sad.png"
    assert hb.summary_image_for_score(3.0) == "worried.png"
    assert hb.summary_image_for_score(4.9) == "worried.png"
    assert hb.summary_image_for_score(5.0) == "neutral.png"
    assert hb.summary_image_for_score(6.9) == "neutral.png"
    assert hb.summary_image_for_score(7.0) == "enthusiastic.png"
    assert hb.summary_image_for_score(8.4) == "enthusiastic.png"
    assert hb.summary_image_for_score(8.5) == "prouded.png"
    assert hb.summary_image_for_score(10.0) == "prouded.png"


# ── Тесты: комментарий на вкладке «Итог» ──────────────────────────────────

def test_summary_comment_uses_new_personal_tone():
    # Без весов score = 5.0 → нейтральный комментарий без намёков на «верный путь».
    html = hb.build_stats_tabbed_html(
        metrics=make_test_metrics(),
        decision_action="decrease",
        is_anomaly=False,
        is_stable=False,
        active_tab="summary",
        image_filename="sad.png",
    )
    assert "Ты держишься в целом нормально" in html
    assert "на верном пути" not in html


# ── Тесты: блок рекомендаций ─────────────────────────────────────────────

def test_summary_recommendations_present_when_weak():
    metrics = make_test_metrics()
    weights = {
        "true_retention": 0.30,
        "new_card_retention": 0.20,
        "avg_difficulty": 0.05,
        "avg_stability": 0.05,
        "low_stability_ratio": 0.05,
        "actual_vs_predicted": 0.05,
        "avg_time_growth": 0.05,
        "consistency": 0.03,
        "relearning_stuck": 0.02,
    }
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="summary",
        image_filename="neutral.png",
        metric_weights=weights,
    )
    assert "Что можно улучшить" in html
    assert "summary-recommendations" in html
    # avg_stability в make_test_metrics = 8.0 → normalized < 0.5
    assert hb._RECOMMENDATION_TEXTS["avg_stability"] in html


def test_summary_recommendations_absent_when_all_good():
    metrics = {
        "true_retention": 0.95,
        "avg_stability": 20.0,
        "consistency": 0.9,
    }
    weights = {"true_retention": 0.5, "avg_stability": 0.3, "consistency": 0.2}
    html = hb.build_stats_tabbed_html(
        metrics=metrics,
        decision_action="hold",
        is_anomaly=False,
        is_stable=False,
        active_tab="summary",
        image_filename="neutral.png",
        metric_weights=weights,
    )
    assert "Что можно улучшить" not in html
    assert "Явных слабых мест не видно" in html


# ── Тесты: уникальные ID градиента в build_gauge_svg ──────────────────────

def test_gauge_gradient_ids_are_unique():
    """Два вызова build_gauge_svg подряд дают разные id у <linearGradient>."""
    svg1 = hb.build_gauge_svg(5.0)
    svg2 = hb.build_gauge_svg(5.0)
    import re
    ids1 = re.findall(r'id="(gauge-grad-[a-f0-9]+)"', svg1)
    ids2 = re.findall(r'id="(gauge-grad-[a-f0-9]+)"', svg2)
    assert len(ids1) == 1
    assert len(ids2) == 1
    assert ids1[0] != ids2[0]


# ── Тесты: параметр reverse в build_gauge_svg ──────────────────────────────

def test_gauge_reverse_red_before_green():
    """При reverse=True красный (#d13438) встречается раньше зелёного (#107c10)."""
    svg = hb.build_gauge_svg(5.0, reverse=True)
    red_pos = svg.index("#d13438")
    green_pos = svg.index("#107c10")
    assert red_pos < green_pos


def test_gauge_default_green_before_red():
    """При reverse=False (по умолчанию) зелёный (#107c10) встречается раньше красного (#d13438)."""
    svg = hb.build_gauge_svg(5.0)
    green_pos = svg.index("#107c10")
    red_pos = svg.index("#d13438")
    assert green_pos < red_pos
