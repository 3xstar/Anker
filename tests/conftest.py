# conftest.py — настройка pytest для тестов аддона Anker.
# Исключаем файлы аддона из сбора тестов (они требуют aqt/Anki).

collect_ignore = [
    "__init__.py",
    "config.py",
    "metrics.py",
    "decision_engine.py",
    "anomaly.py",
    "schedule_overrides.py",
    "deck_selector.py",
    "mascot_ui.py",
]