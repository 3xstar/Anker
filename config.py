"""
config.py — конфигурация и значения по умолчанию для аддона Anker.

Все настраиваемые параметры собраны здесь. Пользователь может изменить их
через стандартный диалог конфигурации Anki (Tools → Add-ons → Config).
"""

from typing import Dict, List, Any

try:
    from . import log
except ImportError:  # вне Anki (тесты) модуль импортируется как top-level
    import log

# ── Значения по умолчанию ───────────────────────────────────────────────────

DEFAULT_CONFIG: Dict[str, Any] = {
    # ── Колоды (opt-in) ──
    # Список ID колод (deck_id), за которыми следит плагин.
    # Пустой список = плагин неактивен.
    "tracked_deck_ids": [],

    # ── Веса метрик для Load Score ──
    # Каждый вес ∈ [0, 1]; сумма не обязана быть = 1 (нормируется внутри).
    # Обоснование весов:
    #   - True Retention — самый прямой индикатор качества обучения,
    #     поэтому ему дан наибольший вес (0.30).
    #   - Retention по новым карточкам — второй по важности: показывает,
    #     насколько хорошо усваивается новый материал (0.20).
    #   - Соотношение кнопок ответа — отражает «настроение» пользователя
    #     при повторении, вес 0.10.
    #   - Сложность и стабильность FSRS — объективные метрики карточек,
    #     по 0.10 каждая.
    #   - Тренд прогноза повторений — опережающий индикатор (0.05).
    #   - Факт. нагрузка vs прогноз — корректирующий (0.05).
    #   - Время на карточку — индикатор когнитивной нагрузки (0.05).
    #   - Consistency — стабильность привычки (0.03).
    #   - Застрявшие в переучивании — сигнал проблемных карточек (0.02).
    "metric_weights": {
        "true_retention": 0.30,
        "new_card_retention": 0.20,
        "again_rate_young": 0.05,
        "again_rate_mature": 0.05,
        "avg_difficulty": 0.05,
        "avg_stability": 0.05,
        "low_stability_ratio": 0.05,
        "actual_vs_predicted": 0.05,
        "avg_time_growth": 0.05,
        "consistency": 0.03,
        "relearning_stuck": 0.02,
    },

    # ── Пороги Load Score ──
    # Load Score ∈ [-1, +1].
    # < load_lower_threshold → рекомендация снизить new.perDay
    # > load_upper_threshold → рекомендация повысить new.perDay
    # между ними → держать текущий лимит
    "load_lower_threshold": -0.3,
    "load_upper_threshold": 0.3,

    # ── Адаптивный шаг изменения ──
    # Минимальное изменение new.perDay (в карточках).
    "min_step": 1,
    # Максимальный процент изменения от текущего лимита за один шаг.
    "max_step_percent": 0.30,
    # Коэффициент агрессивности: умножается на |Load Score| для расчёта шага.
    "step_aggressiveness": 1.0,

    # ── Защитные механизмы ──
    # Абсолютный минимум новых карточек в день.
    "hard_floor": 1,
    # Максимум новых карточек в день (0 = без ограничения сверху).
    # Пользователь может задать конкретный потолок, если хочет ограничить рост.
    "hard_ceiling": 0,
    # Окно EMA-сглаживания в днях (5-7).
    "ema_window_days": 7,
    # Минимальный интервал между изменениями лимита (в днях).
    "cooldown_days": 2,
    # Минимум дней истории повторений до начала изменения лимита.
    # Для быстрой проверки всех сценариев вручную (через меню
    # "Запустить анализ сейчас (тест)") можно временно занизить до 1.
    "min_history_days": 7,

    # ── Сценарий «слишком легко» ──
    # Порог True Retention, выше которого считается «слишком легко».
    "too_easy_retention_threshold": 0.90,
    # Сколько недель подряд retention должен быть выше порога.
    "too_easy_streak_weeks": 2,

    # ── Streak-детекция (для prouded.png) ──
    # Сколько недель подряд без anomaly-срабатываний нужно для stable streak.
    "stable_streak_weeks": 2,

    # ── Anomaly check-in ──
    # Во сколько раз today_rate должен отличаться от среднего за 7 дней.
    "anomaly_rate_multiplier": 2.0,
    # Минимум карточек, пройденных сегодня, для срабатывания anomaly.
    "anomaly_min_cards_today": 10,
    # Cooldown между anomaly-диалогами (в днях).
    "anomaly_cooldown_days": 3,

    # ── Временный лёгкий режим ──
    # Процент от текущего new.perDay при включении лёгкого режима.
    "light_mode_percent": 0.45,

    # ── Периодичность ──
    # Единый период анализа в днях (1-30). Определяет одновременно:
    # (1) как часто Anker проверяет статистику (частота визитов),
    # (2) за какой промежуток эта статистика считается.
    "analysis_period_days": 7,

    # ── Повторяющиеся правила по дням недели ──
    # Ключ — ISO день недели (1=Пн, ..., 7=Вс).
    # Значение — множитель для new.perDay (0.0 = пропуск, 1.0 = без изменений).
    "day_of_week_rules": {},

    # ── UI ──
    # Показывать ли логи решений в окне Anki.
    "show_decision_log": False,

    # ── Язык интерфейса ──
    # "ru" — русский, "en" — английский.
    # Переключается через меню: Инструменты → Anker → Язык / Language.
    "language": "ru",
}


def get_config(addon_manager=None, module_name: str = "") -> Dict[str, Any]:
    """
    Возвращает конфигурацию аддона, объединяя пользовательские настройки
    с дефолтными значениями.

    ВАЖНО: module_name должно быть именем самого аддона (пакета верхнего
    уровня), т.е. тем __name__, который доступен в __init__.py аддона.
    Именно под этим ключом Anki хранит настройки. Нельзя полагаться на
    __name__ внутри этого модуля — он равен "anker.config", а не "anker".

    Args:
        addon_manager: Экземпляр AddonManager (из mw.addonManager).
        module_name: Имя аддона для getConfig (обычно __name__ из __init__.py).

    Returns:
        Словарь с полной конфигурацией.
    """
    config = dict(DEFAULT_CONFIG)
    if addon_manager is not None and module_name:
        try:
            user_config = addon_manager.getConfig(module_name)
            if user_config:
                # Рекурсивно обновляем только известные ключи
                _deep_update(config, user_config)
        except Exception as e:
            log.log_error("config.get_config", e)
    # Защита от старых сохранённых конфигов: период анализа не может быть
    # меньше 2 дней (меньше — не хватает точек для графиков динамики).
    config["analysis_period_days"] = max(2, int(config.get("analysis_period_days", 7)))
    return config


def _deep_update(base: dict, override: dict) -> None:
    """Рекурсивно обновляет словарь base значениями из override."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_update(base[key], value)
        else:
            base[key] = value