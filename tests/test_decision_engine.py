"""
test_decision_engine.py — тесты для decision_engine.py.

Запуск: python -m pytest tests/test_decision_engine.py -v
(из папки аддона, с активированным venv Anki или с установленным pytest)
"""

import datetime
import sys
import os

import pytest

# Добавляем родительскую папку в путь для импорта модулей аддона
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import decision_engine as de
import config as cfg


# ── Вспомогательные ────────────────────────────────────────────────────────

def make_metrics(**overrides):
    """Создаёт словарь метрик с разумными значениями по умолчанию."""
    base = {
        "true_retention_7d": 0.88,
        "true_retention_14d": 0.87,
        "new_card_retention": 0.85,
        "button_ratio_young": {"again": 0.10, "hard": 0.30, "good": 0.50, "easy": 0.10},
        "button_ratio_mature": {"again": 0.08, "hard": 0.25, "good": 0.55, "easy": 0.12},
        "avg_difficulty": 5.0,
        "median_difficulty": 4.8,
        "avg_stability": 8.0,
        "low_stability_ratio": 0.15,
        "due_trend": 0.5,
        "actual_vs_predicted": 1.05,
        "avg_time_growth": 1.02,
        "consistency": 0.65,
        "relearning_stuck": 3,
        "history_days": 14,
        "has_enough_history": True,
    }
    base.update(overrides)
    return base


def make_config(**overrides):
    """Создаёт конфиг с дефолтами."""
    c = dict(cfg.DEFAULT_CONFIG)
    c.update(overrides)
    return c


# ── Тесты: extract_signals ─────────────────────────────────────────────────

def test_extract_signals_basic():
    metrics = make_metrics()
    signals = de.extract_signals(metrics)
    assert signals["true_retention_7d"] == 0.88
    assert signals["again_rate_young"] == 0.10
    assert signals["again_rate_mature"] == 0.08
    assert signals["relearning_stuck"] == 3.0


def test_extract_signals_missing_button_ratio():
    metrics = make_metrics(button_ratio_young=None, button_ratio_mature=None)
    signals = de.extract_signals(metrics)
    assert signals["again_rate_young"] is None
    assert signals["again_rate_mature"] is None


# ── Тесты: normalize_signal ────────────────────────────────────────────────

def test_normalize_retention_good():
    assert de.normalize_signal("true_retention_7d", 1.0) == 1.0
    assert de.normalize_signal("true_retention_7d", 0.85) == 0.0
    assert de.normalize_signal("true_retention_7d", 0.70) == -1.0


def test_normalize_retention_none():
    assert de.normalize_signal("true_retention_7d", None) == 0.0


def test_normalize_again_rate():
    assert de.normalize_signal("again_rate_young", 0.0) == pytest.approx(0.5)
    assert de.normalize_signal("again_rate_young", 0.10) == pytest.approx(0.0)
    assert de.normalize_signal("again_rate_young", 0.30) == pytest.approx(-1.0)


def test_normalize_difficulty():
    assert de.normalize_signal("avg_difficulty", 5.0) == 0.0
    assert de.normalize_signal("avg_difficulty", 1.0) == 1.0
    assert de.normalize_signal("avg_difficulty", 9.0) == -1.0


def test_normalize_due_trend():
    assert de.normalize_signal("due_trend", 0.0) == 0.0
    assert de.normalize_signal("due_trend", 10.0) == -1.0
    assert de.normalize_signal("due_trend", -10.0) == 1.0


def test_normalize_actual_vs_predicted():
    assert de.normalize_signal("actual_vs_predicted", 1.0) == 0.0
    assert de.normalize_signal("actual_vs_predicted", 1.5) == -1.0
    assert de.normalize_signal("actual_vs_predicted", 0.5) == 1.0


def test_normalize_consistency():
    assert de.normalize_signal("consistency", 0.5) == 0.0
    assert de.normalize_signal("consistency", 1.0) == 1.0
    assert de.normalize_signal("consistency", 0.0) == -1.0


def test_normalize_relearning_stuck():
    assert de.normalize_signal("relearning_stuck", 5.0) == 0.0
    assert de.normalize_signal("relearning_stuck", 0.0) == 1.0
    assert de.normalize_signal("relearning_stuck", 10.0) == -1.0


# ── Тесты: EMA ─────────────────────────────────────────────────────────────

def test_ema_update_first():
    assert de.ema_update(None, 0.5, 7) == 0.5


def test_ema_update_none_current():
    assert de.ema_update(0.5, None, 7) == 0.5


def test_ema_update_smooth():
    # alpha = 2/(7+1) = 0.25
    result = de.ema_update(0.8, 0.9, 7)
    expected = 0.25 * 0.9 + 0.75 * 0.8  # = 0.225 + 0.6 = 0.825
    assert abs(result - expected) < 0.001


def test_apply_ema():
    signals = {"true_retention_7d": 0.9, "again_rate_young": 0.15}
    prev = {"true_retention_7d": 0.85, "again_rate_young": 0.12}
    smoothed, new_ema = de.apply_ema(signals, prev, 7)
    assert "true_retention_7d" in smoothed
    assert "again_rate_young" in smoothed
    # Проверяем, что значения изменились в сторону новых
    assert smoothed["true_retention_7d"] > 0.85
    assert smoothed["true_retention_7d"] < 0.9


# ── Тесты: compute_load_score ──────────────────────────────────────────────

def test_load_score_neutral():
    """При нейтральных метриках Load Score должен быть около 0."""
    metrics = make_metrics()
    signals = de.extract_signals(metrics)
    weights = cfg.DEFAULT_CONFIG["metric_weights"]
    score = de.compute_load_score(signals, weights)
    assert -0.3 < score < 0.3, f"Expected neutral, got {score}"


def test_load_score_overloaded():
    """При плохих метриках Load Score должен быть отрицательным."""
    metrics = make_metrics(
        true_retention_7d=0.60,
        true_retention_14d=0.65,
        new_card_retention=0.55,
        button_ratio_young={"again": 0.35, "hard": 0.30, "good": 0.30, "easy": 0.05},
        button_ratio_mature={"again": 0.30, "hard": 0.30, "good": 0.35, "easy": 0.05},
        avg_difficulty=7.5,
        low_stability_ratio=0.45,
        due_trend=8.0,
        actual_vs_predicted=1.6,
        avg_time_growth=1.5,
        consistency=0.2,
        relearning_stuck=12,
    )
    signals = de.extract_signals(metrics)
    weights = cfg.DEFAULT_CONFIG["metric_weights"]
    score = de.compute_load_score(signals, weights)
    assert score < -0.3, f"Expected overloaded (negative), got {score}"


def test_load_score_underloaded():
    """При отличных метриках Load Score должен быть положительным."""
    metrics = make_metrics(
        true_retention_7d=0.95,
        true_retention_14d=0.94,
        new_card_retention=0.93,
        button_ratio_young={"again": 0.03, "hard": 0.20, "good": 0.60, "easy": 0.17},
        button_ratio_mature={"again": 0.02, "hard": 0.18, "good": 0.60, "easy": 0.20},
        avg_difficulty=3.0,
        low_stability_ratio=0.05,
        due_trend=-3.0,
        actual_vs_predicted=0.7,
        avg_time_growth=0.9,
        consistency=0.85,
        relearning_stuck=1,
    )
    signals = de.extract_signals(metrics)
    weights = cfg.DEFAULT_CONFIG["metric_weights"]
    score = de.compute_load_score(signals, weights)
    assert score > 0.3, f"Expected underloaded (positive), got {score}"


def test_load_score_missing_metrics():
    """При отсутствии FSRS-метрик (SM-2) Load Score всё равно вычисляется."""
    metrics = make_metrics(
        avg_difficulty=None,
        median_difficulty=None,
        avg_stability=None,
        low_stability_ratio=None,
    )
    signals = de.extract_signals(metrics)
    weights = cfg.DEFAULT_CONFIG["metric_weights"]
    score = de.compute_load_score(signals, weights)
    assert -1.0 <= score <= 1.0


# ── Тесты: compute_step ────────────────────────────────────────────────────

def test_compute_step_basic():
    config = make_config()
    step = de.compute_step(0.5, 20, config)
    assert step >= 1
    assert step <= 10  # не больше 50% от 20


def test_compute_step_zero_load():
    config = make_config()
    step = de.compute_step(0.0, 20, config)
    assert step == 1  # min_step


def test_compute_step_max():
    config = make_config()
    step = de.compute_step(1.0, 100, config)
    assert step >= 1
    assert step <= 50  # max 50%


# ── Тесты: decide ──────────────────────────────────────────────────────────

def test_decide_hold_neutral():
    metrics = make_metrics()
    config = make_config()
    today = datetime.date(2026, 8, 22)
    decision, _ = de.decide(metrics, config, 20, None, today)
    assert decision.action == "hold"


def test_decide_increase():
    metrics = make_metrics(
        true_retention_7d=0.96,
        true_retention_14d=0.95,
        new_card_retention=0.94,
        button_ratio_young={"again": 0.02, "hard": 0.18, "good": 0.60, "easy": 0.20},
        button_ratio_mature={"again": 0.01, "hard": 0.15, "good": 0.60, "easy": 0.24},
        avg_difficulty=2.5,
        low_stability_ratio=0.03,
        due_trend=-5.0,
        actual_vs_predicted=0.6,
        avg_time_growth=0.85,
        consistency=0.9,
        relearning_stuck=0,
    )
    config = make_config()
    today = datetime.date(2026, 8, 22)
    decision, _ = de.decide(metrics, config, 20, None, today)
    assert decision.action == "increase"
    assert decision.new_limit > 20


def test_decide_decrease():
    metrics = make_metrics(
        true_retention_7d=0.55,
        true_retention_14d=0.60,
        new_card_retention=0.50,
        button_ratio_young={"again": 0.40, "hard": 0.30, "good": 0.25, "easy": 0.05},
        button_ratio_mature={"again": 0.35, "hard": 0.30, "good": 0.30, "easy": 0.05},
        avg_difficulty=8.0,
        low_stability_ratio=0.50,
        due_trend=10.0,
        actual_vs_predicted=1.8,
        avg_time_growth=1.6,
        consistency=0.15,
        relearning_stuck=15,
    )
    config = make_config()
    today = datetime.date(2026, 8, 22)
    decision, _ = de.decide(metrics, config, 20, None, today)
    assert decision.action == "decrease"
    assert decision.new_limit < 20


def test_decide_cooldown():
    """При активном cooldown решение должно быть hold."""
    metrics = make_metrics(
        true_retention_7d=0.96,
        true_retention_14d=0.95,
        new_card_retention=0.94,
        button_ratio_young={"again": 0.02, "hard": 0.18, "good": 0.60, "easy": 0.20},
        button_ratio_mature={"again": 0.01, "hard": 0.15, "good": 0.60, "easy": 0.24},
        avg_difficulty=2.5,
        low_stability_ratio=0.03,
        due_trend=-5.0,
        actual_vs_predicted=0.6,
        avg_time_growth=0.85,
        consistency=0.9,
        relearning_stuck=0,
    )
    config = make_config(cooldown_days=3)
    today = datetime.date(2026, 8, 22)
    last_change = datetime.date(2026, 8, 21)  # вчера меняли
    decision, _ = de.decide(metrics, config, 20, last_change, today)
    assert decision.action == "hold"


def test_decide_not_enough_history():
    metrics = make_metrics(has_enough_history=False, history_days=3)
    config = make_config()
    today = datetime.date(2026, 8, 22)
    decision, _ = de.decide(metrics, config, 20, None, today)
    assert decision.action == "hold"


def test_decide_hard_floor():
    """Лимит не должен падать ниже hard_floor."""
    metrics = make_metrics(
        true_retention_7d=0.30,
        true_retention_14d=0.35,
        new_card_retention=0.25,
        button_ratio_young={"again": 0.60, "hard": 0.20, "good": 0.15, "easy": 0.05},
        button_ratio_mature={"again": 0.55, "hard": 0.20, "good": 0.20, "easy": 0.05},
        avg_difficulty=9.0,
        low_stability_ratio=0.70,
        due_trend=15.0,
        actual_vs_predicted=2.0,
        avg_time_growth=2.0,
        consistency=0.05,
        relearning_stuck=20,
    )
    config = make_config(hard_floor=1)
    today = datetime.date(2026, 8, 22)
    decision, _ = de.decide(metrics, config, 5, None, today)
    assert decision.new_limit >= 1


def test_decide_stable_streak_flag():
    metrics = make_metrics()
    config = make_config()
    today = datetime.date(2026, 8, 22)
    decision, _ = de.decide(
        metrics, config, 20, None, today,
        stable_streak_weeks=3,
    )
    assert decision.is_stable_streak is True


def test_decide_too_easy_flag():
    metrics = make_metrics()
    config = make_config()
    today = datetime.date(2026, 8, 22)
    decision, _ = de.decide(
        metrics, config, 20, None, today,
        too_easy_streak_weeks=3,
    )
    assert decision.is_too_easy is True


# ── Тесты: linear_regression_slope (из metrics.py) ─────────────────────────

def test_linear_regression_positive():
    from metrics import linear_regression_slope
    slope = linear_regression_slope([0, 1, 2, 3], [0, 2, 4, 6])
    assert abs(slope - 2.0) < 0.01


def test_linear_regression_negative():
    from metrics import linear_regression_slope
    slope = linear_regression_slope([0, 1, 2], [10, 8, 6])
    assert abs(slope + 2.0) < 0.01


def test_linear_regression_insufficient():
    from metrics import linear_regression_slope
    assert linear_regression_slope([1], [1]) is None
    assert linear_regression_slope([], []) is None


# ── Тесты: true_retention_from_eases ────────────────────────────────────────

def test_true_retention():
    from metrics import true_retention_from_eases
    # ease: 1=Again, 2=Hard, 3=Good, 4=Easy
    eases = [1, 2, 3, 3, 4, 1, 3, 2, 3, 4]  # 2 Again из 10 = 80% retention
    assert abs(true_retention_from_eases(eases) - 0.80) < 0.01


def test_true_retention_empty():
    from metrics import true_retention_from_eases
    assert true_retention_from_eases([]) is None


# ── Тесты: median ──────────────────────────────────────────────────────────

def test_median_odd():
    from metrics import median
    assert median([1.0, 3.0, 2.0]) == 2.0


def test_median_even():
    from metrics import median
    assert median([1.0, 2.0, 3.0, 4.0]) == 2.5


def test_median_empty():
    from metrics import median
    assert median([]) is None


# ── Тесты: button_ratios ───────────────────────────────────────────────────

def test_button_ratios():
    from metrics import button_ratios
    eases = [1, 1, 2, 3, 3, 3, 4]  # 2 Again, 1 Hard, 3 Good, 1 Easy
    ratios = button_ratios(eases)
    assert ratios is not None
    assert abs(ratios["again"] - 2 / 7) < 0.01
    assert abs(ratios["hard"] - 1 / 7) < 0.01
    assert abs(ratios["good"] - 3 / 7) < 0.01
    assert abs(ratios["easy"] - 1 / 7) < 0.01


def test_button_ratios_empty():
    from metrics import button_ratios
    assert button_ratios([]) is None