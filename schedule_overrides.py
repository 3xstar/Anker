"""
schedule_overrides.py — правила по дням недели и временный лёгкий режим
(раздел 5.1 ТЗ, ветки «Лень» и «Занят(а) сегодня»).

Модуль хранит состояние override-правил и вычисляет эффективный лимит
new.perDay на конкретную дату. Состояние сериализуется в словарь, который
вызывающий код сохраняет (например, в addon config). Логика чистая и
тестируемая — не зависит от Anki API.

Два типа override:
  1. day_of_week_rules — повторяющееся правило для конкретного дня недели
     (ISO: 1=Пн .. 7=Вс). Множитель: 0.0 = пропуск новых карточек,
     1.0 = без изменений, 0.5 = половина лимита.
  2. light_mode — временный лёгкий режим на N дней (3/5/7), снижает лимит
     до заданного процента с автоматическим возвратом после окончания срока.

Приоритет: light_mode применяется поверх day_of_week_rules (если активны оба,
применяются оба множителя последовательно).
"""

import datetime
from typing import Any, Dict, Optional


def default_state() -> Dict[str, Any]:
    """Возвращает пустое состояние override-правил."""
    return {
        "day_of_week_rules": {},
        "light_mode": {
            "active": False,
            "start_day": None,     # ISO-строка даты или None
            "end_day": None,       # ISO-строка даты (исключительно) или None
            "percent": 0.45,
            "original_limit": None,
        },
    }


# ── day-of-week правила ────────────────────────────────────────────────────

def set_day_rule(
    state: Dict[str, Any],
    weekday: int,
    multiplier: float,
) -> Dict[str, Any]:
    """
    Устанавливает (или обновляет) правило для дня недели.

    Args:
        weekday: ISO день недели (1=Пн .. 7=Вс).
        multiplier: множитель для new.perDay (0.0 = пропуск).

    Returns:
        Обновлённое состояние.
    """
    state = dict(state)
    rules = dict(state.get("day_of_week_rules", {}))
    rules[str(int(weekday))] = float(multiplier)
    state["day_of_week_rules"] = rules
    return state


def remove_day_rule(state: Dict[str, Any], weekday: int) -> Dict[str, Any]:
    """Удаляет правило для дня недели."""
    state = dict(state)
    rules = dict(state.get("day_of_week_rules", {}))
    rules.pop(str(int(weekday)), None)
    state["day_of_week_rules"] = rules
    return state


def get_day_rule(state: Dict[str, Any], weekday: int) -> Optional[float]:
    """Возвращает множитель правила для дня недели или None, если правила нет."""
    rules = state.get("day_of_week_rules", {})
    return rules.get(str(int(weekday)))


# ── временный лёгкий режим ─────────────────────────────────────────────────

def set_light_mode(
    state: Dict[str, Any],
    start_day: datetime.date,
    duration_days: int,
    percent: float,
    original_limit: int,
) -> Dict[str, Any]:
    """
    Включает временный лёгкий режим.

    Args:
        start_day: дата начала.
        duration_days: длительность в днях (3/5/7).
        percent: процент от текущего лимита (0.45 = 45%).
        original_limit: лимит, к которому вернёмся после окончания.

    Returns:
        Обновлённое состояние.
    """
    state = dict(state)
    end_day = start_day + datetime.timedelta(days=duration_days)
    state["light_mode"] = {
        "active": True,
        "start_day": start_day.isoformat(),
        "end_day": end_day.isoformat(),
        "percent": float(percent),
        "original_limit": int(original_limit),
    }
    return state


def clear_light_mode(state: Dict[str, Any]) -> Dict[str, Any]:
    """Выключает лёгкий режим."""
    state = dict(state)
    state["light_mode"] = default_state()["light_mode"]
    return state


def is_light_mode_active(state: Dict[str, Any], today: datetime.date) -> bool:
    """Проверяет, активен ли лёгкий режим на дату today."""
    lm = state.get("light_mode", {})
    if not lm.get("active"):
        return False
    try:
        start = datetime.date.fromisoformat(lm["start_day"])
        end = datetime.date.fromisoformat(lm["end_day"])
    except (TypeError, ValueError):
        return False
    return start <= today < end


def expire_light_mode_if_needed(
    state: Dict[str, Any], today: datetime.date
) -> Dict[str, Any]:
    """
    Автоматически выключает лёгкий режим, если срок истёк.
    Возвращает (обновлённое_состояние, был_ли_выключен).
    """
    lm = state.get("light_mode", {})
    if not lm.get("active"):
        return state, False
    try:
        end = datetime.date.fromisoformat(lm["end_day"])
    except (TypeError, ValueError):
        return clear_light_mode(state), True
    if today >= end:
        return clear_light_mode(state), True
    return state, False


# ── вычисление эффективного лимита ─────────────────────────────────────────

def compute_effective_limit(
    state: Dict[str, Any],
    base_limit: int,
    today: datetime.date,
) -> int:
    """
    Вычисляет эффективный new.perDay на дату today с учётом override-правил.

    Args:
        state: состояние override-правил.
        base_limit: базовый лимит (из decision engine / конфига колоды).
        today: дата, для которой считаем лимит.

    Returns:
        Эффективный лимит (целое, >= 0).
    """
    limit = float(base_limit)

    # 1. day-of-week правило
    weekday = today.isoweekday()  # 1=Пн .. 7=Вс
    rule = get_day_rule(state, weekday)
    if rule is not None:
        limit *= rule

    # 2. light_mode поверх
    if is_light_mode_active(state, today):
        lm = state.get("light_mode", {})
        limit *= float(lm.get("percent", 0.45))

    return max(0, int(round(limit)))