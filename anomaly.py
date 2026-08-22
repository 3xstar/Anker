"""
anomaly.py — обнаружение резких скачков (раздел 5.1 ТЗ).

Модуль отделён от Anki API: принимает данные revlog (в виде списка словарей,
как возвращает metrics.fetch_revlog_rows) и конфигурацию, возвращает флаг
наличия аномалии. Тестируется без запуска Anki.

Условия срабатывания anomaly check-in (все обязательны):
  1. Сегодняшний Again-rate отличается от скользящего среднего за 7 дней
     минимум в `anomaly_rate_multiplier` раз (по умолчанию 2x).
  2. За сегодня пройдено не менее `anomaly_min_cards_today` карточек
     (по умолчанию 10) — защита от шума на малых выборках.
  3. С последнего показа anomaly-диалога прошло не менее
     `anomaly_cooldown_days` дней (по умолчанию 3).
"""

import datetime
from typing import Any, Dict, List, Optional, Sequence

# Значения ease в revlog (Anki 23.10+)
EASE_AGAIN = 1
REVLOG_TYPE_REVIEW = 1


def compute_again_rate(
    revlog_rows: Sequence[Dict[str, Any]],
    target_day: datetime.date,
) -> Optional[float]:
    """
    Вычисляет Again-rate (долю ответов "Again") среди повторений (type=review)
    за указанный день.

    Returns:
        Доля 0..1 или None, если за день не было повторений.
    """
    eases = [
        r["ease"]
        for r in revlog_rows
        if r["type"] == REVLOG_TYPE_REVIEW and r["day"] == target_day
    ]
    if not eases:
        return None
    again_count = sum(1 for e in eases if e == EASE_AGAIN)
    return again_count / len(eases)


def compute_avg_again_rate(
    revlog_rows: Sequence[Dict[str, Any]],
    end_day: datetime.date,
    window_days: int,
) -> Optional[float]:
    """
    Вычисляет средний Again-rate за окно window_days дней, заканчиваясь
    днём end_day (не включая сам end_day — это «предыдущие N дней»).

    Returns:
        Средняя доля 0..1 или None, если за окно не было повторений.
    """
    start = end_day - datetime.timedelta(days=window_days)
    eases = [
        r["ease"]
        for r in revlog_rows
        if r["type"] == REVLOG_TYPE_REVIEW
        and start <= r["day"] < end_day
    ]
    if not eases:
        return None
    again_count = sum(1 for e in eases if e == EASE_AGAIN)
    return again_count / len(eases)


def count_reviews_today(
    revlog_rows: Sequence[Dict[str, Any]],
    today: datetime.date,
) -> int:
    """Количество повторений (type=review) за сегодня."""
    return sum(
        1
        for r in revlog_rows
        if r["type"] == REVLOG_TYPE_REVIEW and r["day"] == today
    )


def detect_anomaly(
    revlog_rows: Sequence[Dict[str, Any]],
    config: Dict[str, Any],
    today: datetime.date,
    last_anomaly_day: Optional[datetime.date],
) -> bool:
    """
    Проверяет, нужно ли показать anomaly check-in диалог сегодня.

    Args:
        revlog_rows: строки revlog (как из metrics.fetch_revlog_rows).
        config: полная конфигурация.
        today: сегодняшняя дата.
        last_anomaly_day: дата последнего показа anomaly-диалога (None = никогда).

    Returns:
        True, если условия срабатывания выполнены.
    """
    # Условие 3: cooldown
    cooldown = int(config.get("anomaly_cooldown_days", 3))
    if last_anomaly_day is not None:
        days_since = (today - last_anomaly_day).days
        if days_since < cooldown:
            return False

    # Условие 2: минимум карточек сегодня
    min_cards = int(config.get("anomaly_min_cards_today", 10))
    today_reviews = count_reviews_today(revlog_rows, today)
    if today_reviews < min_cards:
        return False

    # Условие 1: отклонение Again-rate
    today_rate = compute_again_rate(revlog_rows, today)
    if today_rate is None or today_rate == 0:
        return False  # нет данных или 0% Again — не аномалия

    avg_rate = compute_avg_again_rate(revlog_rows, today, 7)
    if avg_rate is None or avg_rate == 0:
        return False  # нет исторических данных для сравнения

    multiplier = float(config.get("anomaly_rate_multiplier", 2.0))
    ratio = today_rate / avg_rate

    return ratio >= multiplier