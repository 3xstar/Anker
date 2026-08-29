"""
test_metrics.py — тесты для чистых функций metrics.py.

Запуск: python -m pytest tests/test_metrics.py -v
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics import _recent_card_ids


def _row(cid: int, day: str):
    return {"cid": cid, "day": datetime.date.fromisoformat(day)}


def test_recent_card_ids_includes_cards_with_reviews_in_period():
    since = datetime.date(2026, 8, 20)
    revlog = [
        _row(1, "2026-08-18"),  # до периода — не входит
        _row(2, "2026-08-20"),  # граница — входит
        _row(3, "2026-08-22"),  # внутри периода — входит
        _row(1, "2026-08-21"),  # та же карточка, свежая запись — входит один раз
    ]
    assert _recent_card_ids(revlog, since) == [1, 2, 3]


def test_recent_card_ids_excludes_cards_without_recent_reviews():
    since = datetime.date(2026, 8, 20)
    revlog = [
        _row(1, "2026-08-19"),
        _row(2, "2026-08-18"),
    ]
    assert _recent_card_ids(revlog, since) == []


def test_recent_card_ids_empty_revlog():
    assert _recent_card_ids([], datetime.date(2026, 8, 20)) == []
