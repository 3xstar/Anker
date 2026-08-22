"""
decision_engine.py — Load Score и логика принятия решений (раздел 2 ТЗ).

Модуль полностью отделён от Anki API: принимает словарь метрик (из metrics.py),
конфигурацию и текущее состояние, возвращает решение. Это позволяет тестировать
логику без запуска Anki.

Архитектура:
  1. Из сырых метрик извлекаются скалярные сигналы (extract_signals).
  2. Каждый сигнал нормализуется в диапазон [-1, +1] (normalize_signal).
  3. Применяется EMA-сглаживание (apply_ema).
  4. Вычисляется взвешенный Load Score (compute_load_score).
  5. На основе Load Score и защитных механизмов принимается решение (decide).

Обоснование весов (см. config.py):
  - True Retention (7d + 14d) — самый прямой индикатор качества обучения,
    суммарный вес 0.30. Если пользователь забывает карточки — это главный
    сигнал к снижению нагрузки.
  - Retention по новым карточкам (0.20) — показывает, насколько хорошо
    усваивается новый материал; если новые карточки идут тяжело, лимит
    надо снижать даже при хорошем общем ретеншене.
  - Again-rate (young + mature, по 0.05) — отражает «настроение» при
    повторении: резкий рост Again = когнитивная перегрузка или усталость.
  - Сложность и стабильность FSRS (по 0.05) — объективные характеристики
    карточек, не зависящие от сиюминутного состояния пользователя.
  - Тренд due-пула (0.05) — опережающий индикатор: если due-пул растёт,
    скоро пользователь столкнётся с перегрузкой, даже если сейчас всё хорошо.
  - actual_vs_predicted (0.05) — корректирующий сигнал: если реальная
    нагрузка систематически выше прогноза, лимит завышен.
  - avg_time_growth (0.05) — рост времени ответа = растущая когнитивная
    нагрузка, даже если retention формально в порядке.
  - consistency (0.03) — нестабильный график занятий сам по себе стресс-фактор.
  - relearning_stuck (0.02) — застрявшие карточки — точечная проблема,
    слабый но полезный сигнал.
"""

import dataclasses
import datetime
from typing import Any, Dict, List, Optional, Tuple


# ── Структуры данных ────────────────────────────────────────────────────────

@dataclasses.dataclass
class Decision:
    """Результат работы decision engine за один цикл."""
    action: str  # "increase", "decrease", "hold"
    load_score: float  # итоговый Load Score ∈ [-1, +1]
    new_limit: int  # рекомендуемый новый лимит new.perDay
    step: int  # величина изменения (положительная для increase)
    reasons: List[str]  # человекочитаемые причины решения
    is_stable_streak: bool  # флаг стабильной серии (для prouded.png)
    is_too_easy: bool  # флаг сценария «слишком легко» (для enthusiastic.png)


# ── Нормализация сигналов ──────────────────────────────────────────────────

def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def normalize_signal(key: str, value: Optional[float]) -> float:
    """
    Преобразует сырое значение сигнала в нормализованный вклад ∈ [-1, +1].
    +1 = «всё отлично, можно повышать нагрузку».
    -1 = «всё плохо, надо снижать нагрузку».
    0  = нейтрально.

    Если value is None (метрика недоступна), возвращает 0 — нейтральный вклад.
    """
    if value is None:
        return 0.0

    # ── Метрики «чем выше, тем лучше» ──
    if key in ("true_retention_7d", "true_retention_14d", "new_card_retention"):
        # reference = 0.85 (85% retention — нейтрально)
        # scale = 0.15 (100% → +1, 70% → -1)
        return _clip((value - 0.85) / 0.15)

    if key == "avg_stability":
        # Стабильность в днях. 5 дней — нейтрально, 15+ → +1, 0 → -0.5.
        return _clip((value - 5.0) / 10.0)

    if key == "consistency":
        # consistency ∈ [0, 1], 0.5 — нейтрально.
        return _clip((value - 0.5) / 0.5)

    # ── Метрики «чем ниже, тем лучше» ──
    if key in ("again_rate_young", "again_rate_mature"):
        # Again-rate: 0.10 (10%) — нейтрально, 0% → +1, 30% → -1.
        return _clip((0.10 - value) / 0.20)

    if key in ("avg_difficulty", "median_difficulty"):
        # FSRS difficulty ∈ [1, 10]. 5.0 — нейтрально, 1 → +1, 9 → -1.
        return _clip((5.0 - value) / 4.0)

    if key == "low_stability_ratio":
        # Доля карточек со стабильностью < 1 дня. 0.2 — нейтрально.
        return _clip((0.2 - value) / 0.2)

    if key == "due_trend":
        # Наклон due-прогноза (карточек/день). 0 — нейтрально.
        return _clip(-value / 10.0)

    if key == "actual_vs_predicted":
        # Отношение факт/прогноз. 1.0 — нейтрально.
        return _clip((1.0 - value) / 0.5)

    if key == "avg_time_growth":
        # Рост времени на карточку (отношение). 1.0 — нейтрально.
        return _clip((1.0 - value) / 0.5)

    if key == "relearning_stuck":
        # Количество застрявших карточек. 5 — нейтрально.
        return _clip((5.0 - value) / 5.0)

    return 0.0


# ── Извлечение сигналов из сырых метрик ────────────────────────────────────

def extract_signals(metrics: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """
    Извлекает из словаря сырых метрик (metrics.py) плоский словарь
    скалярных сигналов, готовых к нормализации.

    Ключи сигналов соответствуют ключам metric_weights в config.py.
    """
    signals: Dict[str, Optional[float]] = {}

    # Прямые скалярные метрики
    for key in (
        "true_retention_7d",
        "true_retention_14d",
        "new_card_retention",
        "avg_difficulty",
        "median_difficulty",
        "avg_stability",
        "low_stability_ratio",
        "due_trend",
        "actual_vs_predicted",
        "avg_time_growth",
        "consistency",
    ):
        signals[key] = metrics.get(key)

    # Извлекаем again-rate из словарей button_ratio
    for maturity, signal_key in [("young", "again_rate_young"), ("mature", "again_rate_mature")]:
        ratio_dict = metrics.get(f"button_ratio_{maturity}")
        if ratio_dict and isinstance(ratio_dict, dict):
            signals[signal_key] = ratio_dict.get("again")
        else:
            signals[signal_key] = None

    # relearning_stuck — целое число, приводим к float
    stuck = metrics.get("relearning_stuck", 0)
    signals["relearning_stuck"] = float(stuck) if stuck is not None else None

    return signals


# ── EMA-сглаживание ────────────────────────────────────────────────────────

def ema_update(prev: Optional[float], current: Optional[float], window: int) -> Optional[float]:
    """
    Одношаговое EMA-обновление.
    alpha = 2 / (window + 1). Если prev is None — возвращаем current как есть.
    Если current is None — возвращаем prev (не обновляем).
    """
    if current is None:
        return prev
    if prev is None:
        return current
    alpha = 2.0 / (window + 1)
    return alpha * current + (1.0 - alpha) * prev


def apply_ema(
    signals: Dict[str, Optional[float]],
    prev_ema: Dict[str, Optional[float]],
    window: int,
) -> Tuple[Dict[str, Optional[float]], Dict[str, Optional[float]]]:
    """
    Применяет EMA-сглаживание к сигналам.

    Args:
        signals: текущие (сырые) значения сигналов.
        prev_ema: предыдущие EMA-значения (пустой словарь при первом запуске).
        window: окно EMA в днях.

    Returns:
        (smoothed_signals, new_ema_state) — сглаженные сигналы и обновлённое
        состояние EMA для сохранения до следующего цикла.
    """
    smoothed: Dict[str, Optional[float]] = {}
    new_ema: Dict[str, Optional[float]] = {}
    for key, value in signals.items():
        prev = prev_ema.get(key)
        new_val = ema_update(prev, value, window)
        smoothed[key] = new_val
        new_ema[key] = new_val
    return smoothed, new_ema


# ── Вычисление Load Score ──────────────────────────────────────────────────

def compute_load_score(
    signals: Dict[str, Optional[float]],
    weights: Dict[str, float],
) -> float:
    """
    Вычисляет взвешенный Load Score ∈ [-1, +1].

    Каждый сигнал нормализуется через normalize_signal(), затем умножается на
    вес из конфига. Сигналы с None-значением дают вклад 0 и исключаются из
    суммы весов (чтобы не размывать результат).

    Args:
        signals: словарь сигналов (сырых или EMA-сглаженных).
        weights: словарь весов из config.metric_weights.

    Returns:
        Load Score ∈ [-1, +1]. 0 если нет ни одного доступного сигнала.
    """
    total_weight = 0.0
    weighted_sum = 0.0
    for key, weight in weights.items():
        if key not in signals:
            continue
        value = signals[key]
        if value is None:
            continue
        contribution = normalize_signal(key, value)
        weighted_sum += weight * contribution
        total_weight += weight
    if total_weight == 0:
        return 0.0
    return _clip(weighted_sum / total_weight)


# ── Адаптивный шаг изменения ───────────────────────────────────────────────

def compute_step(
    load_score: float,
    current_limit: int,
    config: Dict[str, Any],
    metrics: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Вычисляет величину изменения new.perDay (в карточках).

    Шаг пропорционален:
      - |Load Score| (чем дальше от нейтральной зоны, тем больше шаг),
      - текущему лимиту (процентное изменение),
      - скорости падения метрик (резкое падение retention → агрессивнее).

    Args:
        load_score: текущий Load Score.
        current_limit: текущий new.perDay.
        config: конфигурация.
        metrics: сырые метрики (опционально, для учёта скорости изменений).

    Returns:
        Положительное целое число — величина шага.
    """
    min_step = int(config.get("min_step", 1))
    max_percent = float(config.get("max_step_percent", 0.30))
    aggressiveness = float(config.get("step_aggressiveness", 1.0))

    # Базовый шаг: процент от текущего лимита, масштабированный |Load Score|
    base_step = current_limit * max_percent * abs(load_score) * aggressiveness

    # Учёт скорости падения метрик: если 7d retention заметно ниже 14d,
    # увеличиваем агрессивность (резкое падение → быстрее реагируем).
    momentum_mult = 1.0
    if metrics:
        ret_7d = metrics.get("true_retention_7d")
        ret_14d = metrics.get("true_retention_14d")
        if ret_7d is not None and ret_14d is not None and ret_14d > 0:
            drop = (ret_14d - ret_7d) / ret_14d
            if drop > 0.05:  # падение больше 5% относительных
                momentum_mult = 1.0 + min(drop * 10, 1.0)  # до 2x агрессивнее

    step = max(min_step, round(base_step * momentum_mult))
    # Не больше 50% текущего лимита за раз (дополнительная защита)
    step = min(step, max(current_limit // 2, min_step))
    return step


# ── Главная функция принятия решения ───────────────────────────────────────

def decide(
    metrics: Dict[str, Any],
    config: Dict[str, Any],
    current_limit: int,
    last_change_day: Optional[datetime.date],
    today: datetime.date,
    prev_ema: Optional[Dict[str, Optional[float]]] = None,
    anomaly_triggered_today: bool = False,
    stable_streak_weeks: int = 0,
    too_easy_streak_weeks: int = 0,
) -> Tuple[Decision, Dict[str, Optional[float]]]:
    """
    Принимает решение об изменении new.perDay на основе метрик и контекста.

    Args:
        metrics: словарь сырых метрик из metrics.collect_metrics().
        config: полная конфигурация.
        current_limit: текущее значение new.perDay для колоды.
        last_change_day: дата последнего изменения лимита (None = никогда).
        today: сегодняшняя дата.
        prev_ema: предыдущее состояние EMA (None при первом запуске).
        anomaly_triggered_today: был ли сегодня anomaly check-in.
        stable_streak_weeks: сколько недель подряд без anomaly.
        too_easy_streak_weeks: сколько недель подряд retention > 90%.

    Returns:
        (Decision, new_ema_state) — решение и обновлённое состояние EMA.
    """
    if prev_ema is None:
        prev_ema = {}

    reasons: List[str] = []

    # 1. Проверка минимальной истории
    if not metrics.get("has_enough_history", False):
        return (
            Decision(
                action="hold",
                load_score=0.0,
                new_limit=current_limit,
                step=0,
                reasons=["Недостаточно истории повторений (нужно минимум 7 дней)."],
                is_stable_streak=False,
                is_too_easy=False,
            ),
            prev_ema,
        )

    # 2. Извлечение и EMA-сглаживание сигналов
    signals = extract_signals(metrics)
    ema_window = int(config.get("ema_window_days", 7))
    smoothed_signals, new_ema = apply_ema(signals, prev_ema, ema_window)

    # 3. Вычисление Load Score
    weights = config.get("metric_weights", {})
    load_score = compute_load_score(smoothed_signals, weights)

    # 4. Проверка cooldown
    cooldown_days = int(config.get("cooldown_days", 2))
    if last_change_day is not None:
        days_since = (today - last_change_day).days
        if days_since < cooldown_days:
            reasons.append(
                f"Cooldown: с последнего изменения прошло {days_since} дн. "
                f"(нужно {cooldown_days})."
            )
            return (
                Decision(
                    action="hold",
                    load_score=load_score,
                    new_limit=current_limit,
                    step=0,
                    reasons=reasons,
                    is_stable_streak=_check_stable_streak(stable_streak_weeks, config),
                    is_too_easy=_check_too_easy(too_easy_streak_weeks, config),
                ),
                new_ema,
            )

    # 5. Определение действия
    lower = float(config.get("load_lower_threshold", -0.3))
    upper = float(config.get("load_upper_threshold", 0.3))

    if load_score < lower:
        action = "decrease"
        reasons.append(f"Load Score = {load_score:.2f} < {lower} — перегрузка.")
    elif load_score > upper:
        action = "increase"
        reasons.append(f"Load Score = {load_score:.2f} > {upper} — недогрузка.")
    else:
        action = "hold"
        reasons.append(
            f"Load Score = {load_score:.2f} в нейтральной зоне [{lower}, {upper}]."
        )

    # 6. Вычисление шага и нового лимита
    if action == "hold":
        step = 0
        new_limit = current_limit
    else:
        step = compute_step(load_score, current_limit, config, metrics)
        if action == "decrease":
            new_limit = current_limit - step
        else:
            new_limit = current_limit + step

    # 7. Защитные механизмы: floor и ceiling
    hard_floor = int(config.get("hard_floor", 1))
    hard_ceiling = int(config.get("hard_ceiling", 0))
    # 0 означает «без ограничения сверху» (пользователь может задать
    # конкретный потолок в настройках, если хочет).
    if hard_ceiling > 0:
        new_limit = min(hard_ceiling, new_limit)
    new_limit = max(hard_floor, new_limit)

    if new_limit == current_limit and action != "hold":
        action = "hold"
        step = 0
        reasons.append("Новый лимит совпадает с текущим (ограничение floor/ceiling).")

    reasons.append(f"Текущий лимит: {current_limit}, новый: {new_limit}, шаг: {step}.")

    # 8. Флаги для UI
    is_stable = _check_stable_streak(stable_streak_weeks, config)
    is_too_easy = _check_too_easy(too_easy_streak_weeks, config)

    # Сценарий «слишком легко»: если Load Score > upper И retention стабильно
    # высокий — это не просто недогрузка, а именно «слишком легко».
    if is_too_easy and load_score > upper:
        reasons.append("Сценарий «слишком легко»: retention стабильно выше 90%.")

    return (
        Decision(
            action=action,
            load_score=load_score,
            new_limit=new_limit,
            step=step,
            reasons=reasons,
            is_stable_streak=is_stable,
            is_too_easy=is_too_easy,
        ),
        new_ema,
    )


def _check_stable_streak(streak_weeks: int, config: Dict[str, Any]) -> bool:
    """Проверяет, достигнут ли порог стабильной серии (для prouded.png)."""
    required = int(config.get("stable_streak_weeks", 2))
    return streak_weeks >= required


def _check_too_easy(streak_weeks: int, config: Dict[str, Any]) -> bool:
    """Проверяет, достигнут ли порог «слишком легко»."""
    required = int(config.get("too_easy_streak_weeks", 2))
    return streak_weeks >= required