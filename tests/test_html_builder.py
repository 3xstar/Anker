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
    assert "Вспоминаемость (7 дн.)" in html
    assert "Вспоминаемость (14 дн.)" in html
    assert "Новые карточки" in html
    assert "Средняя сложность" in html
    assert "Регулярность" in html
    assert "Застрявшие карточки" in html
    assert "82%" in html
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
    assert "__TAB_MAIN_ACTIVE__" not in html
    assert "__TAB_ALL_ACTIVE__" not in html
    assert "__TAB_CONTENT__" not in html
    assert "__IMAGE_URL__" not in html


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
