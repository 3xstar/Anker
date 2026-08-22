"""
test_anomaly.py — тесты для anomaly.py.

Запуск: python -m pytest tests/test_anomaly.py -v
"""

import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anomaly
import config as cfg


# ── Вспомогательные ────────────────────────────────────────────────────────

# ease: 1=Again, 2=Hard, 3=Good, 4=Easy; type: 1=review
def make_revlog(again_today, total_today, avg_again_prev_7d, prev_days=7):
    """
    Создаёт список revlog-строк:
      - сегодня: total_today повторений, из них again_today — "Again"
      - предыдущие prev_days дней: повторения с долей Again = avg_again_prev_7d
    """
    rows = []
    today = datetime.date(2026, 8, 22)
    # Сегодняшние повторения
    for i in range(total_today):
        ease = anomaly.EASE_AGAIN if i < again_today else 3  # 3 = Good
        rows.append(
            {
                "cid": i,
                "ease": ease,
                "ivl": 5,
                "lastIvl": 5,
                "time": 5000,
                "type": anomaly.REVLOG_TYPE_REVIEW,
                "day": today,
            }
        )
    # Предыдущие дни (по 10 повторений в день)
    for d in range(1, prev_days + 1):
        day = today - datetime.timedelta(days=d)
        again_count = round(10 * avg_again_prev_7d)
        for i in range(10):
            ease = anomaly.EASE_AGAIN if i < again_count else 3
            rows.append(
                {
                    "cid": 100 + d * 100 + i,
                    "ease": ease,
                    "ivl": 5,
                    "lastIvl": 5,
                    "time": 5000,
                    "type": anomaly.REVLOG_TYPE_REVIEW,
                    "day": day,
                }
            )
    return rows


def make_config(**overrides):
    c = dict(cfg.DEFAULT_CONFIG)
    c.update(overrides)
    return c


# ── Тесты: compute_again_rate ──────────────────────────────────────────────

def test_compute_again_rate():
    today = datetime.date(2026, 8, 22)
    rows = make_revlog(again_today=3, total_today=10, avg_again_prev_7d=0.1)
    rate = anomaly.compute_again_rate(rows, today)
    assert abs(rate - 0.3) < 0.01


def test_compute_again_rate_no_reviews():
    today = datetime.date(2026, 8, 22)
    far_past = datetime.date(2026, 8, 1)  # далеко за пределами окна
    rows = make_revlog(again_today=3, total_today=10, avg_again_prev_7d=0.1)
    assert anomaly.compute_again_rate(rows, far_past) is None


# ── Тесты: compute_avg_again_rate ──────────────────────────────────────────

def test_compute_avg_again_rate():
    today = datetime.date(2026, 8, 22)
    rows = make_revlog(again_today=0, total_today=0, avg_again_prev_7d=0.1)
    avg = anomaly.compute_avg_again_rate(rows, today, 7)
    assert avg is not None
    assert 0.05 < avg < 0.15


# ── Тесты: count_reviews_today ─────────────────────────────────────────────

def test_count_reviews_today():
    today = datetime.date(2026, 8, 22)
    rows = make_revlog(again_today=4, total_today=20, avg_again_prev_7d=0.1)
    assert anomaly.count_reviews_today(rows, today) == 20


# ── Тесты: detect_anomaly ──────────────────────────────────────────────────

def test_detect_anomaly_true():
    """Резкий скачок Again-rate должен детектироваться."""
    today = datetime.date(2026, 8, 22)
    config = make_config()
    # Сегодня 40% Again (8 из 20), в среднем за 7 дней 10% → ratio = 4x
    rows = make_revlog(again_today=8, total_today=20, avg_again_prev_7d=0.10)
    assert anomaly.detect_anomaly(rows, config, today, None) is True


def test_detect_anomaly_false_normal():
    """Нормальный Again-rate не должен детектироваться."""
    today = datetime.date(2026, 8, 22)
    config = make_config()
    rows = make_revlog(again_today=2, total_today=20, avg_again_prev_7d=0.10)
    assert anomaly.detect_anomaly(rows, config, today, None) is False


def test_detect_anomaly_false_too_few_cards():
    """Меньше anomaly_min_cards_today карточек — не детектируем."""
    today = datetime.date(2026, 8, 22)
    config = make_config(anomaly_min_cards_today=10)
    rows = make_revlog(again_today=3, total_today=5, avg_again_prev_7d=0.10)
    assert anomaly.detect_anomaly(rows, config, today, None) is False


def test_detect_anomaly_false_cooldown():
    """Cooldown блокирует повторное срабатывание."""
    today = datetime.date(2026, 8, 22)
    config = make_config(anomaly_cooldown_days=3)
    rows = make_revlog(again_today=8, total_today=20, avg_again_prev_7d=0.10)
    last_anomaly = datetime.date(2026, 8, 21)  # вчера
    assert anomaly.detect_anomaly(rows, config, today, last_anomaly) is False


def test_detect_anomaly_false_no_history():
    """Без исторических данных сравнения — не детектируем."""
    today = datetime.date(2026, 8, 22)
    config = make_config()
    # Только сегодняшние данные, без предыдущих дней
    rows = []
    for i in range(20):
        ease = anomaly.EASE_AGAIN if i < 8 else 3
        rows.append(
            {
                "cid": i,
                "ease": ease,
                "ivl": 5,
                "lastIvl": 5,
                "time": 5000,
                "type": anomaly.REVLOG_TYPE_REVIEW,
                "day": today,
            }
        )
    assert anomaly.detect_anomaly(rows, config, today, None) is False


def test_detect_anomaly_zero_today_again():
    """0% Again сегодня — не аномалия (нет отклонения)."""
    today = datetime.date(2026, 8, 22)
    config = make_config()
    rows = make_revlog(again_today=0, total_today=20, avg_again_prev_7d=0.10)
    assert anomaly.detect_anomaly(rows, config, today, None) is False