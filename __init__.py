"""
__init__.py — точка входа аддона Anker.

Регистрирует хуки, пункт меню, управляет ежедневным циклом:
  1. Фоновый расчёт метрик (ежедневно, без UI).
  2. Плановый визит маскота (по настраиваемому расписанию).
  3. Anomaly check-in (событийный, при резком скачке Again-rate).

Правило приоритета (раздел 4 ТЗ): если в один день сработали anomaly-триггер
и плановый визит — показывается только anomaly-диалог, плановый визит
откладывается до следующего цикла.
"""

import datetime
import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from aqt import gui_hooks, mw
from aqt.qt import QAction, QMenu, QTimer
from aqt.utils import showInfo, tooltip

from . import config as cfg
from . import metrics
from . import decision_engine
from . import anomaly
from . import schedule_overrides
from . import mascot_ui
from . import deck_selector

# ── Константы ──────────────────────────────────────────────────────────────

STATE_KEY = "anker_adaptive_load_state"
FREQUENCY_DAYS = {
    "every_3_days": 3,
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
}


# ── Управление состоянием ──────────────────────────────────────────────────

def _load_state() -> Dict[str, Any]:
    """Загружает сохранённое состояние аддона из коллекции."""
    try:
        raw = mw.col.get_config(STATE_KEY, "{}")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    """Сохраняет состояние аддона в коллекцию."""
    try:
        mw.col.set_config(STATE_KEY, json.dumps(state, ensure_ascii=False, default=str))
    except Exception:
        pass


def _default_state() -> Dict[str, Any]:
    """Возвращает состояние по умолчанию."""
    return {
        "last_check_day": None,
        "last_change_day": None,
        "last_anomaly_day": None,
        "last_visit_day": None,
        "ema_state": {},
        "overrides": schedule_overrides.default_state(),
        "streaks": {
            "anomaly_free_days": 0,
            "too_easy_days": 0,
        },
    }


# ── Работа с лимитами колод ────────────────────────────────────────────────

def _get_deck_limit(did: int) -> int:
    """Возвращает текущий new.perDay для колоды."""
    try:
        conf = mw.col.decks.config_dict_for_deck_id(did)
        return int(conf.get("new", {}).get("perDay", 20))
    except Exception:
        return 20


def _set_deck_limit(did: int, limit: int) -> None:
    """Устанавливает new.perDay для колоды."""
    try:
        conf = mw.col.decks.config_dict_for_deck_id(did)
        conf.setdefault("new", {})["perDay"] = max(1, int(limit))
        mw.col.decks.update_config(conf)
    except Exception as e:
        tooltip(f"Anker: не удалось изменить лимит колоды: {e}")


# ── Ежедневная рутина ──────────────────────────────────────────────────────

def _daily_routine() -> None:
    """
    Выполняет ежедневный фоновый расчёт метрик и, при необходимости,
    показывает диалог маскота (anomaly или плановый визит).
    """
    today = datetime.date.today()
    state = _load_state()
    if not state:
        state = _default_state()

    config = cfg.get_config(mw.addonManager)
    tracked_ids = list(config.get("tracked_deck_ids", []))

    # Если нет отслеживаемых колод — плагин неактивен
    if not tracked_ids:
        return

    # Проверяем, не запускали ли уже сегодня
    last_check = state.get("last_check_day")
    if last_check == today.isoformat():
        return  # уже проверяли сегодня

    # Обновляем дату последней проверки
    state["last_check_day"] = today.isoformat()

    # Срок действия лёгкого режима
    state["overrides"], light_expired = schedule_overrides.expire_light_mode_if_needed(
        state["overrides"], today
    )

    # ── Сбор метрик (агрегированно по всем отслеживаемым колодам) ──
    all_metrics = metrics.collect_metrics(mw.col, tracked_ids, config, today)

    # ── Обновление streak-счётчиков ──
    streaks = state.setdefault("streaks", {"anomaly_free_days": 0, "too_easy_days": 0})

    # Проверка «слишком легко»: retention > порога
    too_easy_threshold = float(config.get("too_easy_retention_threshold", 0.90))
    ret_14d = all_metrics.get("true_retention_14d")
    if ret_14d is not None and ret_14d > too_easy_threshold:
        streaks["too_easy_days"] = streaks.get("too_easy_days", 0) + 1
    else:
        streaks["too_easy_days"] = 0

    # ── Anomaly check-in ──
    revlog_rows = metrics.fetch_revlog_rows(mw.col, tracked_ids, today - datetime.timedelta(days=14))
    anomaly_today = anomaly.detect_anomaly(
        revlog_rows,
        config,
        today,
        _parse_date(state.get("last_anomaly_day")),
    )

    if anomaly_today:
        streaks["anomaly_free_days"] = 0
        state["last_anomaly_day"] = today.isoformat()
        _save_state(state)
        # Показываем anomaly-диалог (правило приоритета: anomaly > плановый визит)
        _show_anomaly_flow(config, state, tracked_ids, today)
        return
    else:
        streaks["anomaly_free_days"] = streaks.get("anomaly_free_days", 0) + 1

    # ── Decision engine: рекомендация ──
    # Вычисляем средний текущий лимит по отслеживаемым колодам
    current_limits = [_get_deck_limit(did) for did in tracked_ids]
    avg_limit = sum(current_limits) // max(len(current_limits), 1)

    decision, new_ema = decision_engine.decide(
        metrics=all_metrics,
        config=config,
        current_limit=avg_limit,
        last_change_day=_parse_date(state.get("last_change_day")),
        today=today,
        prev_ema=state.get("ema_state", {}),
        anomaly_triggered_today=False,
        stable_streak_weeks=streaks.get("anomaly_free_days", 0) // 7,
        too_easy_streak_weeks=streaks.get("too_easy_days", 0) // 7,
    )
    state["ema_state"] = new_ema

    # ── Плановый визит ──
    should_visit = _should_show_planned_visit(state, config, today)
    if should_visit:
        state["last_visit_day"] = today.isoformat()
        _save_state(state)
        _show_planned_visit_flow(decision, config, state, tracked_ids, today)
    else:
        _save_state(state)


def _should_show_planned_visit(
    state: Dict[str, Any], config: Dict[str, Any], today: datetime.date
) -> bool:
    """Проверяет, пора ли показать плановый визит."""
    frequency = config.get("visit_frequency", "weekly")
    interval_days = FREQUENCY_DAYS.get(frequency, 7)
    last_visit = _parse_date(state.get("last_visit_day"))
    if last_visit is None:
        return True  # первый запуск
    return (today - last_visit).days >= interval_days


# ── Диалоговые потоки ──────────────────────────────────────────────────────

def _show_anomaly_flow(
    config: Dict[str, Any],
    state: Dict[str, Any],
    tracked_ids: List[int],
    today: datetime.date,
) -> None:
    """Запускает цепочку anomaly-диалогов."""

    def on_action(action: str) -> None:
        if action == "anomaly_lazy":
            QTimer.singleShot(0, lambda: _show_lazy_flow(config, state, tracked_ids, today))
        elif action == "anomaly_busy":
            QTimer.singleShot(0, lambda: _show_busy_flow(config, state))
        elif action == "anomaly_dismiss":
            pass  # просто закрыть

    mascot_ui.show_anomaly_checkin(on_action)


def _show_lazy_flow(
    config: Dict[str, Any],
    state: Dict[str, Any],
    tracked_ids: List[int],
    today: datetime.date,
) -> None:
    """Диалог «Лень» → выбор длительности лёгкого режима."""

    def on_action(action: str) -> None:
        if action.startswith("light_"):
            days_str = action.replace("light_", "").replace("d", "")
            try:
                duration = int(days_str)
            except ValueError:
                return
            percent = float(config.get("light_mode_percent", 0.45))
            # Сохраняем original_limit как средний по колодам
            limits = [_get_deck_limit(did) for did in tracked_ids]
            avg_limit = sum(limits) // max(len(limits), 1) if limits else 20
            state["overrides"] = schedule_overrides.set_light_mode(
                state["overrides"], today, duration, percent, avg_limit
            )
            _save_state(state)
            # Применяем лёгкий режим к каждой колоде
            for did in tracked_ids:
                current = _get_deck_limit(did)
                new_limit = max(1, int(current * percent))
                _set_deck_limit(did, new_limit)
            tooltip(f"Anker: лёгкий режим на {duration} дн. включён.")
        elif action == "light_decline":
            pass

    mascot_ui.show_anomaly_lazy(on_action)


def _show_busy_flow(
    config: Dict[str, Any],
    state: Dict[str, Any],
) -> None:
    """Диалог «Занят(а)» → выбор дней недели."""

    def on_action(action: str) -> None:
        if action == "busy_setup_days":
            QTimer.singleShot(
                0,
                lambda: _show_day_picker(state),
            )
        elif action == "busy_dismiss":
            pass

    mascot_ui.show_anomaly_busy(on_action)


def _show_day_picker(state: Dict[str, Any]) -> None:
    """Диалог выбора дней недели для снижения нагрузки."""
    current_rules = state.get("overrides", {}).get("day_of_week_rules", {})

    def on_action(action: str) -> None:
        if action.startswith("day_rule_set:"):
            day = int(action.split(":")[1])
            state["overrides"] = schedule_overrides.set_day_rule(
                state["overrides"], day, 0.0
            )
        elif action.startswith("day_rule_remove:"):
            day = int(action.split(":")[1])
            state["overrides"] = schedule_overrides.remove_day_rule(
                state["overrides"], day
            )
        _save_state(state)

    mascot_ui.show_day_of_week_picker(current_rules, on_action)


def _show_planned_visit_flow(
    decision: Any,
    config: Dict[str, Any],
    state: Dict[str, Any],
    tracked_ids: List[int],
    today: datetime.date,
) -> None:
    """Показывает плановый визит и применяет решение при согласии."""

    def on_action(action: str) -> None:
        if action == "increase_accept":
            _apply_decision(decision, tracked_ids, state, today)
        elif action == "decrease_accept":
            _apply_decision(decision, tracked_ids, state, today)
        # increase_decline, decrease_decline, prouded_ack, neutral_ack — ничего не делаем

    mascot_ui.show_planned_visit(decision, on_action)


def _apply_decision(
    decision: Any,
    tracked_ids: List[int],
    state: Dict[str, Any],
    today: datetime.date,
) -> None:
    """Применяет решение к каждой отслеживаемой колоде."""
    new_limit = decision.new_limit
    step = decision.step
    action = decision.action

    for did in tracked_ids:
        current = _get_deck_limit(did)
        if action == "increase":
            target = current + step
        elif action == "decrease":
            target = current - step
        else:
            continue
        target = max(1, target)
        _set_deck_limit(did, target)

    state["last_change_day"] = today.isoformat()
    _save_state(state)
    tooltip(f"Anker: лимит изменён ({action}), новый ≈ {new_limit}")


# ── Применение override-правил при старте ───────────────────────────────────

def _apply_overrides_on_startup() -> None:
    """
    При старте Anki применяет активные override-правила (лёгкий режим,
    day-of-week) к отслеживаемым колодам. Это нужно, потому что между сессиями
    Anki лимиты могли быть изменены вручную или сброшены.
    """
    today = datetime.date.today()
    state = _load_state()
    if not state:
        return
    config = cfg.get_config(mw.addonManager)
    tracked_ids = list(config.get("tracked_deck_ids", []))
    if not tracked_ids:
        return

    overrides = state.get("overrides", {})
    # Срок действия лёгкого режима
    overrides, _ = schedule_overrides.expire_light_mode_if_needed(overrides, today)
    state["overrides"] = overrides
    _save_state(state)

    for did in tracked_ids:
        base_limit = _get_deck_limit(did)
        effective = schedule_overrides.compute_effective_limit(overrides, base_limit, today)
        if effective != base_limit:
            _set_deck_limit(did, effective)


# ── Меню ───────────────────────────────────────────────────────────────────

def _add_menu_item() -> None:
    """Добавляет пункт меню Anker в Tools."""
    menu: Optional[QMenu] = None
    try:
        menu = mw.form.menuTools
    except Exception:
        return
    if menu is None:
        return

    anker_menu = menu.addMenu("Anker")

    # Выбор колод
    select_action = QAction("Выбрать колоды…", mw)
    select_action.triggered.connect(_on_select_decks)
    anker_menu.addAction(select_action)

    # Показать маскота (тест)
    test_action = QAction("Показать маскота (тест)", mw)
    test_action.triggered.connect(_on_test_mascot)
    anker_menu.addAction(test_action)

    # Сбросить состояние
    reset_action = QAction("Сбросить состояние", mw)
    reset_action.triggered.connect(_on_reset_state)
    anker_menu.addAction(reset_action)


def _on_select_decks() -> None:
    """Обработчик выбора колод."""
    selected = deck_selector.show_deck_selector()
    if selected is not None:
        try:
            config = mw.addonManager.getConfig(__name__) or {}
            config["tracked_deck_ids"] = selected
            mw.addonManager.writeConfig(__name__, config)
            tooltip(f"Anker: выбрано колод — {len(selected)}")
        except Exception as e:
            showInfo(f"Не удалось сохранить настройки: {e}")


def _on_test_mascot() -> None:
    """Тестовый показ маскота (нейтральный визит)."""
    from .decision_engine import Decision

    test_decision = Decision(
        action="hold",
        load_score=0.0,
        new_limit=20,
        step=0,
        reasons=["Тестовый запуск."],
        is_stable_streak=False,
        is_too_easy=False,
    )

    def on_action(action: str) -> None:
        tooltip(f"Anker test action: {action}")

    mascot_ui.show_planned_visit(test_decision, on_action)


def _on_reset_state() -> None:
    """Сбрасывает состояние аддона."""
    _save_state(_default_state())
    tooltip("Anker: состояние сброшено.")


# ── Вспомогательные ────────────────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[datetime.date]:
    """Парсит ISO-дату из строки или возвращает None."""
    if not date_str:
        return None
    try:
        return datetime.date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


# ── Регистрация хуков ──────────────────────────────────────────────────────

def _on_main_window_init() -> None:
    """Вызывается при инициализации главного окна Anki."""
    _add_menu_item()
    _apply_overrides_on_startup()
    # Запускаем ежедневную рутину с небольшой задержкой, чтобы коллекция
    # точно была готова.
    QTimer.singleShot(2000, _daily_routine)


gui_hooks.main_window_did_init.append(_on_main_window_init)