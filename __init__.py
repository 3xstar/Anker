"""
__init__.py — точка входа аддона Anker.

Регистрирует хуки, пункт меню, управляет ежедневным циклом:
  1. Фоновый расчёт метрик (ежедневно, без UI) — отдельно по каждой колоде.
  2. Плановый визит маскота (по настраиваемому расписанию).
  3. Anomaly check-in (событийный, при резком скачке Again-rate).

Правило приоритета (раздел 4 ТЗ): если в один день сработали anomaly-триггер
и плановый визит — показывается только anomaly-диалог, плановый визит
откладывается до следующего цикла.

Архитектура (v0.2): весь пайплайн (метрики → anomaly → decision) выполняется
отдельно для каждой отслеживаемой колоды. Состояние (ema, streaks, overrides)
хранится per-deck. Если несколько колод требуют диалога в один день — они
показываются последовательно.
"""

import datetime
import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

# Импорты Anki — доступны только внутри запущенного Anki.
# При импорте вне Anki (например, pytest) модуль не падает.
try:
    from aqt import gui_hooks, mw
    from aqt.qt import QAction, QMenu, QTimer
    from aqt.utils import showInfo, tooltip
    _ANKI_AVAILABLE = True
except ImportError:
    _ANKI_AVAILABLE = False

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
    """Возвращает состояние по умолчанию (v0.2: per-deck)."""
    return {
        "last_check_day": None,
        "decks": {},  # {str(deck_id): {ema_state, streaks, ...}}
    }


def _default_deck_state() -> Dict[str, Any]:
    """Возвращает состояние одной колоды по умолчанию."""
    return {
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


def _migrate_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Миграция со старого (плоского) формата состояния на per-deck.
    Если обнаружен старый формат — сбрасываем состояние (некритичные данные).
    """
    if "decks" not in state:
        return _default_state()
    return state


def _get_deck_state(state: Dict[str, Any], deck_id: int) -> Dict[str, Any]:
    """Возвращает (и при необходимости создаёт) per-deck состояние."""
    key = str(deck_id)
    if key not in state["decks"]:
        state["decks"][key] = _default_deck_state()
    return state["decks"][key]


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


# ── Ежедневная рутина (per-deck) ───────────────────────────────────────────

def _daily_routine() -> None:
    """
    Выполняет ежедневный фоновый расчёт метрик для каждой отслеживаемой
    колоды отдельно. Если несколько колод требуют диалога — показывает
    их последовательно.
    """
    today = datetime.date.today()
    state = _load_state()
    if not state:
        state = _default_state()
    state = _migrate_state(state)

    config = cfg.get_config(mw.addonManager, __name__)
    tracked_ids = list(config.get("tracked_deck_ids", []))

    if not tracked_ids:
        return

    last_check = state.get("last_check_day")
    if last_check == today.isoformat():
        return

    state["last_check_day"] = today.isoformat()

    # Собираем очередь диалогов: (type, deck_id, deck_name, decision|None, metrics|None)
    pending: List[Tuple[str, int, str, Any, Any]] = []

    for deck_id in tracked_ids:
        try:
            deck_name = mw.col.decks.name(deck_id)
        except Exception:
            deck_name = f"Колода #{deck_id}"

        ds = _get_deck_state(state, deck_id)

        # Срок действия лёгкого режима
        ds["overrides"], _ = schedule_overrides.expire_light_mode_if_needed(
            ds["overrides"], today
        )

        # Сбор метрик для этой колоды
        deck_metrics = metrics.collect_metrics(mw.col, [deck_id], config, today)

        # Streaks
        streaks = ds.setdefault("streaks", {"anomaly_free_days": 0, "too_easy_days": 0})
        too_easy_threshold = float(config.get("too_easy_retention_threshold", 0.90))
        ret_14d = deck_metrics.get("true_retention_14d")
        if ret_14d is not None and ret_14d > too_easy_threshold:
            streaks["too_easy_days"] = streaks.get("too_easy_days", 0) + 1
        else:
            streaks["too_easy_days"] = 0

        # Anomaly check-in
        revlog_rows = metrics.fetch_revlog_rows(
            mw.col, [deck_id], today - datetime.timedelta(days=14)
        )
        anomaly_today = anomaly.detect_anomaly(
            revlog_rows, config, today,
            _parse_date(ds.get("last_anomaly_day")),
        )

        if anomaly_today:
            streaks["anomaly_free_days"] = 0
            ds["last_anomaly_day"] = today.isoformat()
            pending.append(("anomaly", deck_id, deck_name, None, deck_metrics))
            continue

        streaks["anomaly_free_days"] = streaks.get("anomaly_free_days", 0) + 1

        # Decision engine
        current_limit = _get_deck_limit(deck_id)
        decision, new_ema = decision_engine.decide(
            metrics=deck_metrics,
            config=config,
            current_limit=current_limit,
            last_change_day=_parse_date(ds.get("last_change_day")),
            today=today,
            prev_ema=ds.get("ema_state", {}),
            anomaly_triggered_today=False,
            stable_streak_weeks=streaks.get("anomaly_free_days", 0) // 7,
            too_easy_streak_weeks=streaks.get("too_easy_days", 0) // 7,
        )
        ds["ema_state"] = new_ema

        # Плановый визит
        should_visit = _should_show_planned_visit(ds, config, today)
        if should_visit:
            ds["last_visit_day"] = today.isoformat()
            pending.append(("planned", deck_id, deck_name, decision, deck_metrics))

    _save_state(state)

    # Показываем диалоги последовательно
    if pending:
        _show_dialog_queue(pending, 0, state, config, today)


def _should_show_planned_visit(
    ds: Dict[str, Any], config: Dict[str, Any], today: datetime.date
) -> bool:
    """Проверяет, пора ли показать плановый визит для конкретной колоды."""
    frequency = config.get("visit_frequency", "weekly")
    interval_days = FREQUENCY_DAYS.get(frequency, 7)
    last_visit = _parse_date(ds.get("last_visit_day"))
    if last_visit is None:
        return True
    return (today - last_visit).days >= interval_days


# ── Очередь диалогов ───────────────────────────────────────────────────────

def _show_dialog_queue(
    pending: List[Tuple[str, int, str, Any, Any]],
    index: int,
    state: Dict[str, Any],
    config: Dict[str, Any],
    today: datetime.date,
) -> None:
    """Показывает следующий диалог из очереди (рекурсивно через колбэки)."""
    if index >= len(pending):
        return

    item = pending[index]
    dialog_type, deck_id, deck_name, extra, deck_metrics = item

    def on_done() -> None:
        QTimer.singleShot(0, lambda: _show_dialog_queue(
            pending, index + 1, state, config, today
        ))

    if dialog_type == "anomaly":
        ds = _get_deck_state(state, deck_id)
        _show_anomaly_flow(config, ds, deck_id, deck_name, today, deck_metrics, on_done)
    else:
        ds = _get_deck_state(state, deck_id)
        decision = extra
        _show_planned_visit_flow(decision, config, ds, deck_id, deck_name, today, deck_metrics, on_done)


# ── Диалоговые потоки (per-deck) ───────────────────────────────────────────

def _show_anomaly_flow(
    config: Dict[str, Any],
    ds: Dict[str, Any],
    deck_id: int,
    deck_name: str,
    today: datetime.date,
    deck_metrics: Dict[str, Any],
    on_done: Callable[[], None],
) -> None:
    """Запускает цепочку anomaly-диалогов для конкретной колоды."""

    stats_ctx = {
        "metrics": deck_metrics,
        "decision_action": "hold",
        "is_anomaly": True,
    }

    def on_action(action: str) -> None:
        if action == "anomaly_lazy":
            QTimer.singleShot(0, lambda: _show_lazy_flow(
                config, ds, deck_id, deck_name, today, on_done
            ))
        elif action == "anomaly_busy":
            QTimer.singleShot(0, lambda: _show_busy_flow(config, ds, deck_name, on_done))
        elif action == "anomaly_dismiss":
            on_done()

    mascot_ui.show_anomaly_checkin(deck_name, on_action, stats_context=stats_ctx)


def _show_lazy_flow(
    config: Dict[str, Any],
    ds: Dict[str, Any],
    deck_id: int,
    deck_name: str,
    today: datetime.date,
    on_done: Callable[[], None],
) -> None:
    """Диалог «Лень» → выбор длительности лёгкого режима."""

    def on_action(action: str) -> None:
        if action.startswith("light_"):
            days_str = action.replace("light_", "").replace("d", "")
            try:
                duration = int(days_str)
            except ValueError:
                on_done()
                return
            percent = float(config.get("light_mode_percent", 0.45))
            current = _get_deck_limit(deck_id)
            ds["overrides"] = schedule_overrides.set_light_mode(
                ds["overrides"], today, duration, percent, current
            )
            new_limit = max(1, int(current * percent))
            _set_deck_limit(deck_id, new_limit)
            tooltip(f"Anker: лёгкий режим для «{deck_name}» на {duration} дн.")
        elif action == "light_decline":
            pass
        on_done()

    mascot_ui.show_anomaly_lazy(deck_name, on_action)


def _show_busy_flow(
    config: Dict[str, Any],
    ds: Dict[str, Any],
    deck_name: str,
    on_done: Callable[[], None],
) -> None:
    """Диалог «Занят(а)» → выбор дней недели."""

    def on_action(action: str) -> None:
        if action == "busy_setup_days":
            QTimer.singleShot(0, lambda: _show_day_picker(ds, deck_name, on_done))
        elif action == "busy_dismiss":
            on_done()

    mascot_ui.show_anomaly_busy(deck_name, on_action)


def _show_day_picker(
    ds: Dict[str, Any],
    deck_name: str,
    on_done: Callable[[], None],
) -> None:
    """Диалог выбора дней недели для снижения нагрузки."""
    current_rules = ds.get("overrides", {}).get("day_of_week_rules", {})

    def on_action(action: str) -> None:
        if action.startswith("day_rule_set:"):
            day = int(action.split(":")[1])
            ds["overrides"] = schedule_overrides.set_day_rule(
                ds["overrides"], day, 0.0
            )
        elif action.startswith("day_rule_remove:"):
            day = int(action.split(":")[1])
            ds["overrides"] = schedule_overrides.remove_day_rule(
                ds["overrides"], day
            )
        # Не сохраняем здесь — сохранится в _daily_routine после всей цепочки

    mascot_ui.show_day_of_week_picker(current_rules, deck_name, on_action, on_done)


def _show_planned_visit_flow(
    decision: Any,
    config: Dict[str, Any],
    ds: Dict[str, Any],
    deck_id: int,
    deck_name: str,
    today: datetime.date,
    deck_metrics: Dict[str, Any],
    on_done: Callable[[], None],
) -> None:
    """Показывает плановый визит и применяет решение при согласии."""

    stats_ctx = {
        "metrics": deck_metrics,
        "decision_action": decision.action,
        "is_stable": decision.is_stable_streak,
        "is_anomaly": False,
    }

    def on_action(action: str) -> None:
        if action == "increase_accept":
            _apply_decision(decision, deck_id, ds, today)
        elif action == "decrease_accept":
            _apply_decision(decision, deck_id, ds, today)
        on_done()

    mascot_ui.show_planned_visit(decision, deck_name, on_action, stats_context=stats_ctx)


def _apply_decision(
    decision: Any,
    deck_id: int,
    ds: Dict[str, Any],
    today: datetime.date,
) -> None:
    """Применяет решение к одной конкретной колоде."""
    action = decision.action
    step = decision.step
    current = _get_deck_limit(deck_id)

    if action == "increase":
        target = current + step
    elif action == "decrease":
        target = current - step
    else:
        return

    target = max(1, target)
    _set_deck_limit(deck_id, target)
    ds["last_change_day"] = today.isoformat()
    tooltip(f"Anker: лимит изменён ({action}), новый ≈ {target}")


# ── Применение override-правил при старте (per-deck) ───────────────────────

def _apply_overrides_on_startup() -> None:
    """
    При старте Anki применяет активные override-правила (лёгкий режим,
    day-of-week) к каждой отслеживаемой колоде отдельно.
    """
    today = datetime.date.today()
    state = _load_state()
    if not state:
        return
    state = _migrate_state(state)

    config = cfg.get_config(mw.addonManager, __name__)
    tracked_ids = list(config.get("tracked_deck_ids", []))
    if not tracked_ids:
        return

    for did in tracked_ids:
        ds = _get_deck_state(state, did)
        overrides = ds.get("overrides", {})
        overrides, _ = schedule_overrides.expire_light_mode_if_needed(overrides, today)
        ds["overrides"] = overrides

        base_limit = _get_deck_limit(did)
        effective = schedule_overrides.compute_effective_limit(overrides, base_limit, today)
        if effective != base_limit:
            _set_deck_limit(did, effective)

    _save_state(state)


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

    # Запустить анализ сейчас (тест) — реальный расчётный путь
    force_action = QAction("Запустить анализ сейчас (тест)", mw)
    force_action.triggered.connect(_on_force_analysis)
    anker_menu.addAction(force_action)

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
    selected = deck_selector.show_deck_selector(__name__)
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

    mascot_ui.show_planned_visit(test_decision, "Тестовая колода", on_action)


def _on_force_analysis() -> None:
    """Принудительный запуск анализа (тест) — в обход расписания и cooldown."""
    _force_analysis()


def _force_analysis() -> None:
    """
    Выполняет полный расчётный путь для каждой колоды отдельно,
    в обход visit_frequency и cooldown, но с сохранением проверки
    min_history_days.
    """
    today = datetime.date.today()
    state = _load_state()
    if not state:
        state = _default_state()
    state = _migrate_state(state)

    config = cfg.get_config(mw.addonManager, __name__)
    tracked_ids = list(config.get("tracked_deck_ids", []))

    if not tracked_ids:
        tooltip("Anker: нет отслеживаемых колод. Сначала выберите колоды в меню Anker.")
        return

    pending: List[Tuple[str, int, str, Any, Any]] = []

    for deck_id in tracked_ids:
        try:
            deck_name = mw.col.decks.name(deck_id)
        except Exception:
            deck_name = f"Колода #{deck_id}"

        ds = _get_deck_state(state, deck_id)
        deck_metrics = metrics.collect_metrics(mw.col, [deck_id], config, today)

        if not deck_metrics.get("has_enough_history", False):
            min_days = int(config.get("min_history_days", 7))
            actual_days = deck_metrics.get("history_days", 0)
            showInfo(
                f"Колода «{deck_name}»: недостаточно истории — "
                f"нужно минимум {min_days} дн., сейчас {actual_days}.\n\n"
                f"Совет: для быстрой проверки можно временно занизить "
                f"min_history_days в конфиге аддона (например, до 1)."
            )
            continue

        streaks = ds.get("streaks", {"anomaly_free_days": 0, "too_easy_days": 0})
        too_easy_threshold = float(config.get("too_easy_retention_threshold", 0.90))
        ret_14d = deck_metrics.get("true_retention_14d")
        too_easy_days = streaks.get("too_easy_days", 0)
        if ret_14d is not None and ret_14d > too_easy_threshold:
            too_easy_days += 1
        else:
            too_easy_days = 0

        revlog_rows = metrics.fetch_revlog_rows(
            mw.col, [deck_id], today - datetime.timedelta(days=14)
        )
        anomaly_today = anomaly.detect_anomaly(
            revlog_rows, config, today, None  # без cooldown
        )

        if anomaly_today:
            pending.append(("anomaly", deck_id, deck_name, None, deck_metrics))
            continue

        current_limit = _get_deck_limit(deck_id)
        decision, _ = decision_engine.decide(
            metrics=deck_metrics,
            config=config,
            current_limit=current_limit,
            last_change_day=None,  # без cooldown
            today=today,
            prev_ema=ds.get("ema_state", {}),
            anomaly_triggered_today=False,
            stable_streak_weeks=streaks.get("anomaly_free_days", 0) // 7,
            too_easy_streak_weeks=too_easy_days // 7,
        )
        pending.append(("planned", deck_id, deck_name, decision, deck_metrics))

    if pending:
        _show_dialog_queue(pending, 0, state, config, today)


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
    QTimer.singleShot(2000, _daily_routine)


if _ANKI_AVAILABLE:
    gui_hooks.main_window_did_init.append(_on_main_window_init)