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
