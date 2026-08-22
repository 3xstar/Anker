"""
deck_selector.py — UI списка колод с чекбоксами (opt-in, раздел 6 ТЗ).

Окно с поиском/фильтром и списком всех колод пользователя. Пользователь
отмечает галочками те колоды, за которыми аддон будет следить. По умолчанию
ни одна колода не выбрана (opt-in, а не opt-out).

Используется нативный PyQt-диалог (QDialog), так как это настройка, а не
общение с маскотом — маскот (AnkiWebView) используется только для диалогов.
"""

from typing import List, Optional, Set

from aqt import mw
from aqt.qt import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    Qt,
)


class DeckSelectorDialog(QDialog):
    """Диалог выбора отслеживаемых колод с поиском."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Anker — выбор колод")
        self.setMinimumSize(420, 480)

        self._all_decks: List[tuple] = []  # [(deck_id, name), ...]
        self._selected: Set[int] = set()

        self._build_ui()
        self._load_decks()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Поле поиска
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск колоды…")
        self.search_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_edit)

        # Список колод с чекбоксами
        self.deck_list = QListWidget()
        self.deck_list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.deck_list)

        # Кнопки
        button_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Выбрать все")
        self.select_none_btn = QPushButton("Снять все")
        self.close_btn = QPushButton("Готово")
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_none_btn.clicked.connect(self._select_none)
        self.close_btn.clicked.connect(self.accept)
        button_row.addWidget(self.select_all_btn)
        button_row.addWidget(self.select_none_btn)
        button_row.addStretch()
        button_row.addWidget(self.close_btn)
        layout.addLayout(button_row)

    def _load_decks(self) -> None:
        """Загружает все колоды и текущий выбор из конфига."""
        # Получаем все колоды: mw.col.decks.all_names_and_ids()
        try:
            decks = mw.col.decks.all_names_and_ids()
        except Exception:
            decks = []

        self._all_decks = [(did, name) for name, did in decks if name != "Default"]

        # Текущий выбор из конфига аддона
        current = self._current_selected()
        self._selected = set(current)

        self._apply_filter()

    def _current_selected(self) -> List[int]:
        """Читает список отслеживаемых колод из конфига аддона."""
        try:
            config = mw.addonManager.getConfig(__name__)
            return list(config.get("tracked_deck_ids", [])) if config else []
        except Exception:
            return []

    def _apply_filter(self) -> None:
        """Перерисовывает список с учётом строки поиска."""
        query = self.search_edit.text().strip().lower()

        # Блокируем сигнал itemChanged, чтобы не срабатывал при перерисовке
        self.deck_list.blockSignals(True)
        self.deck_list.clear()
        for did, name in self._all_decks:
            if query and query not in name.lower():
                continue
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setData(Qt.UserRole, did)
            item.setCheckState(
                Qt.Checked if did in self._selected else Qt.Unchecked
            )
            self.deck_list.addItem(item)
        self.deck_list.blockSignals(False)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """Обновляет множество выбранных при клике по чекбоксу."""
        did = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self._selected.add(did)
        else:
            self._selected.discard(did)

    def _select_all(self) -> None:
        self._selected = {did for did, _ in self._all_decks}
        self._apply_filter()

    def _select_none(self) -> None:
        self._selected = set()
        self._apply_filter()

    def selected_deck_ids(self) -> List[int]:
        """Возвращает итоговый список выбранных ID колод."""
        return sorted(self._selected)


def show_deck_selector(parent=None) -> Optional[List[int]]:
    """
    Показывает диалог выбора колод. Возвращает список выбранных ID колод
    (None, если пользователь отменил).
    """
    dialog = DeckSelectorDialog(parent or mw)
    if dialog.exec():
        return dialog.selected_deck_ids()
    return None