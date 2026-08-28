"""
metrics.py — сбор и расчёт метрик из раздела 1 ТЗ.

Модуль отделён от остальной логики аддона: функции, которые читают данные из
базы Anki, принимают объект коллекции `col` и список ID отслеживаемых колод.
Чистые расчётные функции (ретеншен, линейная регрессия и т.п.) принимают
обычные данные и могут быть протестированы без Anki.

Важно: FSRS `memory_state` (difficulty/stability) доступен только при
включённом FSRS-планировщике в Anki 23.10+. На SM-2 или старых версиях эти
метрики возвращают None — decision_engine корректно пропускает их.
"""

import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ── Константы Anki ──────────────────────────────────────────────────────────

# Значения поля `ease` в таблице revlog (Anki 23.10+):
# 1 = Again, 2 = Hard, 3 = Good, 4 = Easy.
EASE_AGAIN = 1
EASE_HARD = 2
EASE_GOOD = 3
EASE_EASY = 4

# Значения поля `type` в таблице revlog:
REVLOG_TYPE_LEARN = 0      # изучение (learning steps)
REVLOG_TYPE_REVIEW = 1     # повторение (review)
REVLOG_TYPE_RELEARN = 2    # переучивание (relearning)
REVLOG_TYPE_CRAM = 3       # зубрёжка (filtered deck)
REVLOG_TYPE_MANUAL = 4     # ручное перенесение

# Порог "young"/"mature": интервал 21 день (стандарт Anki).
YOUNG_MATURE_THRESHOLD_DAYS = 21

# Порог "низкой стабильности" — карточки со стабильностью < 1 дня.
LOW_STABILITY_DAYS = 1.0

# Анки считает новый день с 4:00 утра (настраивается, но берём стандарт).
DEFAULT_DAY_CUTOFF_HOUR = 4


# ── Вспомогательные чистые функции ─────────────────────────────────────────

def timestamp_ms_to_day(ts_ms: int, cutoff_hour: int = DEFAULT_DAY_CUTOFF_HOUR) -> datetime.date:
    """
    Переводит unix-время в миллисекундах (как хранится в revlog.id) в
    локальную «Anki-дату», учитывая сдвиг начала дня на cutoff_hour.
    """
    dt = datetime.datetime.fromtimestamp(ts_ms / 1000.0)
    day_start = dt.replace(hour=cutoff_hour, minute=0, second=0, microsecond=0)
    if dt < day_start:
        day_start -= datetime.timedelta(days=1)
    return day_start.date()


def days_between(d1: datetime.date, d2: datetime.date) -> int:
    """Число дней между двумя датами (положительное, если d2 позже d1)."""
    return (d2 - d1).days


def linear_regression_slope(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """
    Вычисляет наклон линии линейной регрессии y = a*x + b методом наименьших
    квадратов. Возвращает None, если данных недостаточно (меньше 2 точек) или
    дисперсия x нулевая.
    """
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return None
    numer = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return numer / denom


def true_retention_from_eases(eases: Sequence[int]) -> Optional[float]:
    """
    True Retention = доля ответов, не являющихся "Again", т.е. ease > EASE_AGAIN.
    Возвращает долю 0..1 или None, если данных нет.
    """
    if not eases:
        return None
    remembered = sum(1 for e in eases if e > EASE_AGAIN)
    return remembered / len(eases)


def median(values: Sequence[float]) -> Optional[float]:
    """Медиана списка чисел (None при пустом списке)."""
    if not values:
        return None
    sorted_values = sorted(values)
    n = len(sorted_values)
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


def button_ratios(eases: Sequence[int]) -> Optional[Dict[str, float]]:
    """
    Соотношение кнопок ответа: доля Again/Hard/Good/Easy среди переданных ease.
    Возвращает словарь с ключами 'again','hard','good','easy' (сумма = 1),
    либо None при отсутствии данных.
    """
    if not eases:
        return None
    total = len(eases)
    return {
        "again": sum(1 for e in eases if e == EASE_AGAIN) / total,
        "hard": sum(1 for e in eases if e == EASE_HARD) / total,
        "good": sum(1 for e in eases if e == EASE_GOOD) / total,
        "easy": sum(1 for e in eases if e == EASE_EASY) / total,
    }


# ── Чтение данных из базы Anki ─────────────────────────────────────────────

def _expand_deck_ids(col, deck_ids: Sequence[int]) -> List[int]:
    """
    Разворачивает список ID колод, добавляя ID всех дочерних подколод.
    Это нужно, потому что карточки в Anki привязаны к самой нижней подколоде,
    и без агрегации метрики для родительской колоды будут пустыми.
    """
    result = set()
    for did in deck_ids:
        try:
            children = col.decks.deck_and_child_ids(did)
            result.update(children)
        except Exception:
            result.add(did)
    return sorted(result)


def fetch_revlog_rows(
    col,
    deck_ids: Sequence[int],
    since_day: datetime.date,
    cutoff_hour: int = DEFAULT_DAY_CUTOFF_HOUR,
) -> List[Dict[str, Any]]:
    """
    Возвращает строки revlog для карточек из заданных колод (включая подколоды),
    начиная с since_day (включительно). Строка содержит поля:
    cid, ease, ivl, lastIvl, time (мс), type, day (datetime.date).
    """
    if not deck_ids:
        return []
    expanded = _expand_deck_ids(col, deck_ids)
    placeholders = ",".join("?" for _ in expanded)
    # revlog.id — unix-время в мс. Считаем границу дня в мс на основе cutoff.
    start_dt = datetime.datetime.combine(
        since_day, datetime.time(hour=cutoff_hour, minute=0, second=0)
    )
    start_ms = int(start_dt.timestamp() * 1000)

    sql = f"""
        SELECT r.id, r.cid, r.ease, r.ivl, r.lastIvl, r.time, r.type
        FROM revlog AS r
        JOIN cards AS c ON c.id = r.cid
        WHERE c.did IN ({placeholders})
          AND r.id >= ?
    """
    rows = col.db.all(sql, *expanded, start_ms)
    result = []
    for row in rows:
        rev_id, cid, ease, ivl, last_ivl, time_ms, rtype = row
        result.append(
            {
                "cid": cid,
                "ease": ease,
                "ivl": ivl,
                "lastIvl": last_ivl,
                "time": time_ms,
                "type": rtype,
                "day": timestamp_ms_to_day(rev_id, cutoff_hour),
            }
        )
    return result


def fetch_card_rows(
    col, deck_ids: Sequence[int]
) -> List[Dict[str, Any]]:
    """
    Возвращает карточки из заданных колод (включая подколоды):
    id, did, ivl (интервал), reps, lapses.
    """
    if not deck_ids:
        return []
    expanded = _expand_deck_ids(col, deck_ids)
    placeholders = ",".join("?" for _ in expanded)
    sql = f"""
        SELECT id, did, ivl, reps, lapses
        FROM cards
        WHERE did IN ({placeholders})
    """
    rows = col.db.all(sql, *expanded)
    return [
        {"id": r[0], "did": r[1], "ivl": r[2], "reps": r[3], "lapses": r[4]}
        for r in rows
    ]


def fetch_fsrs_memory_state(
    col, card_ids: Sequence[int]
) -> Dict[int, Tuple[float, Optional[float]]]:
    """
    Получает FSRS-состояние (difficulty, stability) через card.memory_state.

    card.memory_state — стандартное поле объекта Card в Anki с FSRS.
    Если карточка не изучалась через FSRS (SM-2) — memory_state будет None,
    это ожидаемо и обрабатывается graceful.

    Возвращает словарь {card_id: (difficulty, stability)}.
    Если FSRS недоступен или данных нет — возвращает пустой словарь.
    """
    result: Dict[int, Tuple[float, Optional[float]]] = {}
    if not card_ids:
        return result
    for cid in card_ids:
        try:
            card = col.get_card(cid)
        except Exception:
            continue
        state = getattr(card, "memory_state", None)
        if state is None:
            continue
        try:
            difficulty = float(state.difficulty)
            stability = float(state.stability) if state.stability is not None else None
            result[cid] = (difficulty, stability)
        except Exception:
            continue
    return result


# ── Оркестратор сбора всех метрик ──────────────────────────────────────────

def collect_metrics(
    col,
    deck_ids: Sequence[int],
    config: Dict[str, Any],
    today: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    Собирает все метрики раздела 1 для переданных колод.

    Args:
        col: объект коллекции Anki (mw.col).
        deck_ids: список ID отслеживаемых колод.
        config: полная конфигурация аддона (см. config.py).
        today: «сегодня» в терминах Anki (по умолчанию — реальная дата).

    Returns:
        Словарь с сырыми значениями метрик (см. ключи ниже).
    """
    if today is None:
        today = datetime.date.today()

    cutoff_hour = int(config.get("day_cutoff_hour", DEFAULT_DAY_CUTOFF_HOUR))
    # Период анализа не может быть меньше 2 дней — иначе графикам не хватает
    # точек для построения динамики.
    period = max(2, int(config.get("analysis_period_days", 7)))
    # Берём запас истории: 2× период + 7 дней на всякий случай
    history_window_days = max(period * 2 + 7, 30)

    since_day = today - datetime.timedelta(days=history_window_days)

    revlog = fetch_revlog_rows(col, deck_ids, since_day, cutoff_hour)
    cards = fetch_card_rows(col, deck_ids)

    metrics: Dict[str, Any] = {
        "history_days": _count_history_days(revlog, today),
        "has_enough_history": False,
        "true_retention": None,
        "new_card_retention": None,
        "button_ratio_young": None,
        "button_ratio_mature": None,
        "avg_difficulty": None,
        "avg_stability": None,
        "low_stability_ratio": None,
        "actual_vs_predicted": None,
        "actual_vs_predicted_counts": None,  # {"actual": N, "predicted": M}
        "avg_time_per_card": None,
        "avg_time_growth": None,
        "consistency": None,
        "relearning_stuck": 0,
        "daily_retention": [],  # [(day_label, retention), ...] для sparkline
        "daily_again_rate": [],  # [(day_label, again_rate), ...]
        "daily_new_card_retention": [],
        "daily_review_count": [],
        "daily_relearning_count": [],
        "daily_stability": [],  # [(day_label, avg_ivl), ...] — прокси стабильности
        "daily_time": [],  # [(day_label, avg_seconds), ...]
    }

    # 1. True Retention (единый период)
    metrics["true_retention"] = _retention_window(revlog, today, period)

    # 2. Retention по новым карточкам (окно 30 дней — шире периода анализа,
    # чтобы не зависеть от темпа добавления карточек)
    metrics["new_card_retention"] = _new_card_retention(revlog, today, 30)

    # 3. Соотношение кнопок (young/mature)
    metrics["button_ratio_young"] = _button_ratio_by_maturity(
        revlog, today, period, mature=False
    )
    metrics["button_ratio_mature"] = _button_ratio_by_maturity(
        revlog, today, period, mature=True
    )

    # 4. Сложность и стабильность FSRS (graceful fallback на SM-2)
    card_ids = [c["id"] for c in cards]
    fsrs = fetch_fsrs_memory_state(col, card_ids)
    if fsrs:
        difficulties = [d for d, _ in fsrs.values() if d is not None]
        stabilities = [s for _, s in fsrs.values() if s is not None]
        if difficulties:
            metrics["avg_difficulty"] = sum(difficulties) / len(difficulties)
        if stabilities:
            metrics["avg_stability"] = sum(stabilities) / len(stabilities)
            low_count = sum(1 for s in stabilities if s < LOW_STABILITY_DAYS)
            metrics["low_stability_ratio"] = low_count / len(stabilities)

    # 5. Фактическая нагрузка vs теоретическая (period vs предыдущий period)
    recent_reviews, prev_reviews = _actual_vs_predicted_counts(revlog, today, period)
    metrics["actual_vs_predicted"] = (
        (recent_reviews / prev_reviews) if prev_reviews else None
    )
    metrics["actual_vs_predicted_counts"] = {
        "actual": recent_reviews,
        "predicted": prev_reviews,
    }

    # 6. Время на карточку (period vs предыдущий period)
    metrics["avg_time_per_card"], metrics["avg_time_growth"] = _time_per_card(
        revlog, today, period
    )

    # 7. Consistency нагрузки по дням
    metrics["consistency"] = _consistency(revlog, today, period)

    # 8. Застрявшие в переучивании
    metrics["relearning_stuck"] = _relearning_stuck(revlog, today, period)

    # 9. Дневные ряды для sparkline-графиков
    metrics["daily_retention"] = _daily_retention_series(revlog, today, period)
    metrics["daily_again_rate"] = _daily_again_rate_series(revlog, today, period)
    metrics["daily_new_card_retention"] = _daily_new_card_retention_series(revlog, today, 30)
    metrics["daily_review_count"] = _daily_review_count_series(revlog, today, period)
    metrics["daily_relearning_count"] = _daily_relearning_count_series(revlog, today, period)
    metrics["daily_stability"] = _daily_stability_series(revlog, today, period)
    metrics["daily_time"] = _daily_time_series(revlog, today, period)

    metrics["has_enough_history"] = (
        metrics["history_days"] >= int(config.get("min_history_days", 7))
    )

    return metrics


# ── Реализация отдельных метрик ────────────────────────────────────────────

def _count_history_days(revlog: Sequence[Dict[str, Any]], today: datetime.date) -> int:
    """Число дней с хоть одной записью в revlog (в пределах окна)."""
    if not revlog:
        return 0
    days = {r["day"] for r in revlog}
    if not days:
        return 0
    return days_between(min(days), max(days)) + 1


def _retention_window(
    revlog: Sequence[Dict[str, Any]],
    today: datetime.date,
    window_days: int,
) -> Optional[float]:
    """
    True Retention по повторениям (type=review) с интервалом > 1 дня в окне.
    """
    start = today - datetime.timedelta(days=window_days)
    eases = [
        r["ease"]
        for r in revlog
        if r["type"] == REVLOG_TYPE_REVIEW
        and r["lastIvl"] > 1
        and start <= r["day"] <= today
    ]
    return true_retention_from_eases(eases)


def _new_card_retention(
    revlog: Sequence[Dict[str, Any]],
    today: datetime.date,
    window_days: int,
) -> Optional[float]:
    """
    Retention по новым карточкам: только для карточек, впервые вышедших из
    learning steps за последние window_days дней. «Выход из learning» = первая
    запись типа review (type=1) у карточки.
    """
    start = today - datetime.timedelta(days=window_days)
    # Для каждой карточки — день её первого review.
    first_review_day: Dict[int, datetime.date] = {}
    for r in revlog:
        if r["type"] != REVLOG_TYPE_REVIEW:
            continue
        cid = r["cid"]
        if cid not in first_review_day or r["day"] < first_review_day[cid]:
            first_review_day[cid] = r["day"]

    # Оставляем карточки, вышедшие в окно.
    recently_graduated = {
        cid for cid, day in first_review_day.items() if start <= day <= today
    }
    if not recently_graduated:
        return None

    eases = [
        r["ease"]
        for r in revlog
        if r["type"] == REVLOG_TYPE_REVIEW
        and r["cid"] in recently_graduated
        and r["lastIvl"] > 1
        and r["day"] <= today
    ]
    return true_retention_from_eases(eases)


def _button_ratio_by_maturity(
    revlog: Sequence[Dict[str, Any]],
    today: datetime.date,
    window_days: int,
    mature: bool,
) -> Optional[Dict[str, float]]:
    """
    Соотношение кнопок ответа для young (interval < 21) или mature
    (interval >= 21) карточек за window_days дней.
    """
    start = today - datetime.timedelta(days=window_days)
    eases = []
    for r in revlog:
        if r["type"] != REVLOG_TYPE_REVIEW:
            continue
        if not (start <= r["day"] <= today):
            continue
        is_mature = r["lastIvl"] >= YOUNG_MATURE_THRESHOLD_DAYS
        if is_mature == mature:
            eases.append(r["ease"])
    return button_ratios(eases)


def _actual_vs_predicted_counts(
    revlog: Sequence[Dict[str, Any]], today: datetime.date, period: int
) -> Tuple[int, int]:
    """
    Возвращает (recent, prev) — число повторений (review + relearn) за
    последние period дней и за предыдущие period дней. Используется и для
    отношения «факт vs прогноз», и для парной столбчатой диаграммы.
    """
    recent_start = today - datetime.timedelta(days=period)
    prev_start = today - datetime.timedelta(days=period * 2)

    recent = sum(
        1
        for r in revlog
        if r["type"] in (REVLOG_TYPE_REVIEW, REVLOG_TYPE_RELEARN)
        and recent_start <= r["day"] <= today
    )
    prev = sum(
        1
        for r in revlog
        if r["type"] in (REVLOG_TYPE_REVIEW, REVLOG_TYPE_RELEARN)
        and prev_start <= r["day"] < recent_start
    )
    return recent, prev


def _time_per_card(
    revlog: Sequence[Dict[str, Any]], today: datetime.date, period: int
) -> Tuple[Optional[float], Optional[float]]:
    """
    Среднее время на карточку (в секундах) за последние period дней и рост
    относительно предыдущих period дней (отношение).
    """
    recent_start = today - datetime.timedelta(days=period)
    prev_start = today - datetime.timedelta(days=period * 2)

    recent_times = [
        r["time"] / 1000.0
        for r in revlog
        if recent_start <= r["day"] <= today and r["time"] > 0
    ]
    prev_times = [
        r["time"] / 1000.0
        for r in revlog
        if prev_start <= r["day"] < recent_start and r["time"] > 0
    ]

    if recent_times:
        avg_recent = sum(recent_times) / len(recent_times)
    else:
        avg_recent = None
    if prev_times and recent_times:
        avg_prev = sum(prev_times) / len(prev_times)
        growth = avg_recent / avg_prev if avg_prev > 0 else None
    else:
        growth = None
    return avg_recent, growth


def _consistency(
    revlog: Sequence[Dict[str, Any]], today: datetime.date, window_days: int
) -> Optional[float]:
    """
    Consistency нагрузки по дням: коэффициент вариации количества review по
    дням за окно. Меньше = стабильнее. Возвращаем 1 - CV (нормализовано),
    чтобы большее значение означало большую стабильность (0..1).
    """
    start = today - datetime.timedelta(days=window_days)
    counts: Dict[datetime.date, int] = {}
    for r in revlog:
        if r["type"] not in (REVLOG_TYPE_REVIEW, REVLOG_TYPE_RELEARN):
            continue
        if start <= r["day"] <= today:
            counts[r["day"]] = counts.get(r["day"], 0) + 1
    if not counts:
        return None
    values = list(counts.values())
    mean = sum(values) / len(values)
    if mean == 0:
        return None
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    cv = (variance ** 0.5) / mean
    return max(0.0, min(1.0, 1.0 - cv))


def _relearning_stuck(
    revlog: Sequence[Dict[str, Any]], today: datetime.date, window_days: int
) -> int:
    """
    Количество карточек, «застрявших» в переучивании: у которых за window_days
    дней больше 2 записей типа relearning (type=2).
    """
    start = today - datetime.timedelta(days=window_days)
    relearn_count: Dict[int, int] = {}
    for r in revlog:
        if r["type"] != REVLOG_TYPE_RELEARN:
            continue
        if start <= r["day"] <= today:
            relearn_count[r["cid"]] = relearn_count.get(r["cid"], 0) + 1
    return sum(1 for count in relearn_count.values() if count > 2)


def _daily_retention_series(
    revlog: Sequence[Dict[str, Any]], today: datetime.date, window_days: int
) -> List[tuple]:
    """
    Вычисляет дневной True Retention за последние window_days дней.
    Возвращает список [(day_label, retention), ...] для sparkline-графика.
    """
    result = []
    for offset in range(window_days - 1, -1, -1):
        day = today - datetime.timedelta(days=offset)
        eases = [
            r["ease"]
            for r in revlog
            if r["type"] == REVLOG_TYPE_REVIEW
            and r["lastIvl"] > 1
            and r["day"] == day
        ]
        ret = true_retention_from_eases(eases)
        label = day.strftime("%d.%m")
        result.append((label, ret))
    return result


def _daily_again_rate_series(
    revlog: Sequence[Dict[str, Any]], today: datetime.date, window_days: int
) -> List[tuple]:
    """
    Вычисляет дневной Again-rate за последние window_days дней.
    Возвращает список [(day_label, again_rate), ...] для sparkline-графика.
    """
    result = []
    for offset in range(window_days - 1, -1, -1):
        day = today - datetime.timedelta(days=offset)
        eases = [
            r["ease"]
            for r in revlog
            if r["type"] == REVLOG_TYPE_REVIEW
            and r["day"] == day
        ]
        if not eases:
            result.append((day.strftime("%d.%m"), None))
            continue
        again_count = sum(1 for e in eases if e == EASE_AGAIN)
        result.append((day.strftime("%d.%m"), again_count / len(eases)))
    return result


def _daily_new_card_retention_series(
    revlog: Sequence[Dict[str, Any]], today: datetime.date, window_days: int
) -> List[tuple]:
    """Дневной retention по новым карточкам за window_days дней."""
    # Для каждого дня: карточки, впервые вышедшие из learning в этот день
    first_review_day: Dict[int, datetime.date] = {}
    for r in revlog:
        if r["type"] != REVLOG_TYPE_REVIEW:
            continue
        cid = r["cid"]
        if cid not in first_review_day or r["day"] < first_review_day[cid]:
            first_review_day[cid] = r["day"]

    result = []
    for offset in range(window_days - 1, -1, -1):
        day = today - datetime.timedelta(days=offset)
        graduated_today = {cid for cid, d in first_review_day.items() if d == day}
        if not graduated_today:
            result.append((day.strftime("%d.%m"), None))
            continue
        eases = [
            r["ease"]
            for r in revlog
            if r["type"] == REVLOG_TYPE_REVIEW
            and r["cid"] in graduated_today
            and r["lastIvl"] > 1
            and r["day"] <= today
        ]
        ret = true_retention_from_eases(eases)
        result.append((day.strftime("%d.%m"), ret))
    return result


def _daily_review_count_series(
    revlog: Sequence[Dict[str, Any]], today: datetime.date, window_days: int
) -> List[tuple]:
    """Дневное количество повторений за window_days дней (для визуализации регулярности)."""
    result = []
    for offset in range(window_days - 1, -1, -1):
        day = today - datetime.timedelta(days=offset)
        count = sum(
            1 for r in revlog
            if r["type"] in (REVLOG_TYPE_REVIEW, REVLOG_TYPE_RELEARN)
            and r["day"] == day
        )
        result.append((day.strftime("%d.%m"), float(count) if count > 0 else None))
    return result


def _daily_relearning_count_series(
    revlog: Sequence[Dict[str, Any]], today: datetime.date, window_days: int
) -> List[tuple]:
    """Дневное количество переучиваний за window_days дней."""
    result = []
    for offset in range(window_days - 1, -1, -1):
        day = today - datetime.timedelta(days=offset)
        count = sum(
            1 for r in revlog
            if r["type"] == REVLOG_TYPE_RELEARN
            and r["day"] == day
        )
        result.append((day.strftime("%d.%m"), float(count) if count > 0 else None))
    return result


def _daily_stability_series(
    revlog: Sequence[Dict[str, Any]], today: datetime.date, window_days: int
) -> List[tuple]:
    """
    Дневная динамика средней стабильности. FSRS-стабильность — это снимок
    текущего состояния карточки (без истории), поэтому в качестве дневного
    прокси берём средний выданный интервал (ivl) по повторениям за день:
    он растёт вместе с закреплением карточек.
    """
    result = []
    for offset in range(window_days - 1, -1, -1):
        day = today - datetime.timedelta(days=offset)
        ivls = [
            r["ivl"]
            for r in revlog
            if r["type"] == REVLOG_TYPE_REVIEW and r["ivl"] > 0 and r["day"] == day
        ]
        if ivls:
            result.append((day.strftime("%d.%m"), sum(ivls) / len(ivls)))
        else:
            result.append((day.strftime("%d.%m"), None))
    return result


def _daily_time_series(
    revlog: Sequence[Dict[str, Any]], today: datetime.date, window_days: int
) -> List[tuple]:
    """Дневная динамика среднего времени на карточку (в секундах)."""
    result = []
    for offset in range(window_days - 1, -1, -1):
        day = today - datetime.timedelta(days=offset)
        times = [
            r["time"] / 1000.0
            for r in revlog
            if r["day"] == day and r["time"] > 0
        ]
        if times:
            result.append((day.strftime("%d.%m"), sum(times) / len(times)))
        else:
            result.append((day.strftime("%d.%m"), None))
    return result