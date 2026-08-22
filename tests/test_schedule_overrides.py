"""
test_schedule_overrides.py — тесты для schedule_overrides.py.

Запуск: python -m pytest tests/test_schedule_overrides.py -v
"""

import datetime
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schedule_overrides as so


# ── Тесты: day_of_week_rules ────────────────────────────────────────────────

def test_set_day_rule_uses_string_keys():
    """set_day_rule должен сохранять ключи как строки (для JSON round-trip)."""
    state = so.default_state()
    state = so.set_day_rule(state, 1, 0.5)
    rules = state["day_of_week_rules"]
    assert "1" in rules
    assert 1 not in rules
    assert rules["1"] == 0.5


def test_get_day_rule_uses_string_keys():
    """get_day_rule должен находить правило по строковому ключу."""
    state = so.default_state()
    state = so.set_day_rule(state, 3, 0.0)
    assert so.get_day_rule(state, 3) == 0.0
    assert so.get_day_rule(state, 1) is None


def test_remove_day_rule_uses_string_keys():
    """remove_day_rule должен удалять по строковому ключу."""
    state = so.default_state()
    state = so.set_day_rule(state, 5, 0.3)
    assert so.get_day_rule(state, 5) == 0.3
    state = so.remove_day_rule(state, 5)
    assert so.get_day_rule(state, 5) is None


def test_day_rule_survives_json_roundtrip():
    """Правила по дням недели должны переживать JSON serialization/deserialization."""
    state = so.default_state()
    state = so.set_day_rule(state, 1, 0.0)
    state = so.set_day_rule(state, 4, 0.5)

    # Эмулируем сохранение/загрузку как в __init__.py
    serialized = json.dumps(state)
    restored = json.loads(serialized)

    # После JSON round-trip ключи стали строками — get_day_rule должен работать
    assert so.get_day_rule(restored, 1) == 0.0
    assert so.get_day_rule(restored, 4) == 0.5
    assert so.get_day_rule(restored, 2) is None


def test_set_day_rule_overwrite():
    """Повторный вызов set_day_rule должен перезаписывать правило."""
    state = so.default_state()
    state = so.set_day_rule(state, 2, 0.3)
    state = so.set_day_rule(state, 2, 0.8)
    assert so.get_day_rule(state, 2) == 0.8


# ── Тесты: light_mode ──────────────────────────────────────────────────────

def test_light_mode_default_inactive():
    state = so.default_state()
    today = datetime.date(2026, 8, 22)
    assert not so.is_light_mode_active(state, today)


def test_set_and_check_light_mode():
    state = so.default_state()
    today = datetime.date(2026, 8, 22)
    state = so.set_light_mode(state, today, 3, 0.45, 20)
    assert so.is_light_mode_active(state, today)
    assert so.is_light_mode_active(state, today + datetime.timedelta(days=1))
    assert so.is_light_mode_active(state, today + datetime.timedelta(days=2))
    # На 3-й день (end_day) уже не активно (исключительно)
    assert not so.is_light_mode_active(state, today + datetime.timedelta(days=3))


def test_expire_light_mode():
    state = so.default_state()
    today = datetime.date(2026, 8, 22)
    state = so.set_light_mode(state, today, 3, 0.45, 20)
    # Проверяем через 4 дня — должно истечь
    future = today + datetime.timedelta(days=4)
    new_state, expired = so.expire_light_mode_if_needed(state, future)
    assert expired
    assert not so.is_light_mode_active(new_state, future)


def test_clear_light_mode():
    state = so.default_state()
    today = datetime.date(2026, 8, 22)
    state = so.set_light_mode(state, today, 5, 0.5, 20)
    state = so.clear_light_mode(state)
    assert not so.is_light_mode_active(state, today)


# ── Тесты: compute_effective_limit ─────────────────────────────────────────

def test_compute_effective_limit_no_overrides():
    state = so.default_state()
    today = datetime.date(2026, 8, 21)  # пятница (weekday=5)
    assert so.compute_effective_limit(state, 20, today) == 20


def test_compute_effective_limit_day_of_week():
    state = so.default_state()
    today = datetime.date(2026, 8, 23)  # воскресенье (weekday=7)
    state = so.set_day_rule(state, 7, 0.0)  # в вс — 0 карточек
    assert so.compute_effective_limit(state, 20, today) == 0


def test_compute_effective_limit_day_of_week_half():
    state = so.default_state()
    today = datetime.date(2026, 8, 23)  # воскресенье (weekday=7)
    state = so.set_day_rule(state, 7, 0.5)
    assert so.compute_effective_limit(state, 20, today) == 10


def test_compute_effective_limit_light_mode():
    state = so.default_state()
    today = datetime.date(2026, 8, 22)
    state = so.set_light_mode(state, today, 3, 0.45, 20)
    # 20 * 0.45 = 9
    assert so.compute_effective_limit(state, 20, today) == 9


def test_compute_effective_limit_both_overrides():
    """day_of_week + light_mode применяются последовательно."""
    state = so.default_state()
    today = datetime.date(2026, 8, 23)  # воскресенье (weekday=7)
    state = so.set_day_rule(state, 7, 0.5)  # половина в вс
    state = so.set_light_mode(state, today, 3, 0.4, 20)  # 40% лёгкий режим
    # 20 * 0.5 * 0.4 = 4
    assert so.compute_effective_limit(state, 20, today) == 4


def test_compute_effective_limit_floor_zero():
    """Лимит не должен уходить ниже 0."""
    state = so.default_state()
    today = datetime.date(2026, 8, 21)  # пятница (weekday=5)
    state = so.set_day_rule(state, 5, 0.0)
    state = so.set_light_mode(state, today, 3, 0.1, 20)
    assert so.compute_effective_limit(state, 1, today) == 0