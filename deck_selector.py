"""
deck_selector.py — UI списка колод с чекбоксами (opt-in, раздел 6 ТЗ).

Окно с поиском/фильтром и списком всех колод пользователя. Пользователь
отмечает галочками те колоды, за которыми аддон будет следить. По умолчанию
ни одна колода не выбрана (opt-in, а не opt-out).

Используется нативный PyQt-диалог (QDialog), так как это настройка, а не
общение с маскотом — маскот (AnkiWebView) используется только для диалогов.
"""

from typing import List, Optional, Set

from . import log

from .i18n import t

try:
    from aqt import mw
    from aqt.qt import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QVBoxLayout,
        Qt,
    )
    from aqt.utils import tooltip
    _ANKI_AVAILABLE = True
except ImportError:
    _ANKI_AVAILABLE = False
    QDialog = object
    QHBoxLayout = object
    QLabel = object
    QLineEdit = object
    QListWidget = object
    QListWidgetItem = object
    QPushButton = object
    QVBoxLayout = object
    Qt = object
    mw = None
    tooltip = None


class DeckSelectorDialog(QDialog):
    """Диалог выбора отслеживаемых колод с поиском."""

    def __init__(self, addon_module_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("ds_title"))
        self.setMinimumSize(420, 480)

        self._addon_module_name = addon_module_name
        self._all_decks: List[tuple] = []  # [(deck_id, name), ...]
        self._selected: Set[int] = set()

        self._build_ui()
        self._load_decks()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Предупреждение о двойном учёте (скрыто по умолчанию)
        self.warning_label = QLabel(
            "⚠ Некоторые колоды вложены друг в друга — "
            "это приведёт к двойному учёту карточек. "
            "Оставьте только родительскую колоду."
        )
        self.warning_label.setStyleSheet(
            "color: #c75b00; font-size: 12px; padding: 4px 8px;"
        )
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        layout.addWidget(self.warning_label)

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
        self.close_btn.clicked.connect(self._validate_and_accept)
        button_row.addWidget(self.select_all_btn)
        button_row.addWidget(self.select_none_btn)
        button_row.addStretch()
        button_row.addWidget(self.close_btn)
        layout.addLayout(button_row)

    def _load_decks(self) -> None:
        """Загружает все колоды и текущий выбор из конфига."""
        try:
            decks = mw.col.decks.all_names_and_ids()
        except Exception as e:
            log.log_error("deck_selector._load_decks", e)
            decks = []

        # Фильтруем: только колоды, у которых есть карточки (включая подколоды)
        non_empty = []
        for d in decks:
            if d.name == "Default":
                continue
            try:
                count = mw.col.decks.card_count(d.id, include_subdecks=True)
                if count > 0:
                    non_empty.append((d.id, d.name))
            except Exception:
                # Если не можем проверить — показываем (лучше лишнее, чем потеря)
                non_empty.append((d.id, d.name))

        self._all_decks = non_empty

        # Текущий выбор из конфига аддона
        current = self._current_selected()
        self._selected = set(current)

        self._apply_filter()

    def _current_selected(self) -> List[int]:
        """Читает список отслеживаемых колод из конфига аддона."""
        try:
            config = mw.addonManager.getConfig(self._addon_module_name)
            return list(config.get("tracked_deck_ids", [])) if config else []
        except Exception as e:
            log.log_error("deck_selector._current_selected", e)
            return []

    def _apply_filter(self) -> None:
        """Перерисовывает список с учётом строки поиска."""
        query = self.search_edit.text().strip().lower()

        self.deck_list.blockSignals(True)
        self.deck_list.clear()
        for did, name in self._all_decks:
            if query and query not in name.lower():
                continue
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.ItemDataRole.UserRole, did)
            item.setCheckState(
                Qt.CheckState.Checked if did in self._selected else Qt.CheckState.Unchecked
            )
            self.deck_list.addItem(item)
        self.deck_list.blockSignals(False)

        # Проверяем на конфликт родитель-потомок
        self._check_ancestor_conflict()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """Обновляет множество выбранных при клике по чекбоксу."""
        did = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self._selected.add(did)
        else:
            self._selected.discard(did)
        self._check_ancestor_conflict()

    def _check_ancestor_conflict(self) -> None:
        """
        Проверяет, нет ли в выбранных колодах ситуации «родитель + потомок».
        Если есть — показывает предупреждение.
        """
        selected = list(self._selected)
        for i, did_a in enumerate(selected):
            try:
                children_a = set(mw.col.decks.deck_and_child_ids(did_a))
            except Exception:
                continue
            for did_b in selected[i + 1:]:
                if did_b in children_a:
                    self.warning_label.show()
                    return
                try:
                    children_b = set(mw.col.decks.deck_and_child_ids(did_b))
                    if did_a in children_b:
                        self.warning_label.show()
                        return
                except Exception:
                    pass
        self.warning_label.hide()

    def _validate_and_accept(self) -> None:
        """Проверяет на конфликты перед сохранением."""
        selected = list(self._selected)
        for i, did_a in enumerate(selected):
            try:
                children_a = set(mw.col.decks.deck_and_child_ids(did_a))
            except Exception:
                continue
            for did_b in selected[i + 1:]:
                if did_b in children_a:
                    tooltip(
                        "Нельзя выбрать родительскую и дочернюю колоду одновременно. "
                        "Оставьте только родительскую."
                    )
                    return
                try:
                    children_b = set(mw.col.decks.deck_and_child_ids(did_b))
                    if did_a in children_b:
                        tooltip(
                            "Нельзя выбрать родительскую и дочернюю колоду одновременно. "
                            "Оставьте только родительскую."
                        )
                        return
                except Exception:
                    pass
        self.accept()

    def _select_all(self) -> None:
        self._selected = {did for did, _ in self._all_decks}
        self._apply_filter()

    def _select_none(self) -> None:
        self._selected = set()
        self._apply_filter()

    def selected_deck_ids(self) -> List[int]:
        """Возвращает итоговый список выбранных ID колод."""
        return sorted(self._selected)


def show_deck_selector(addon_module_name: str, parent=None) -> Optional[List[int]]:
    """
    Показывает диалог выбора колод. Возвращает список выбранных ID колод
    (None, если пользователь отменил).

    Args:
        addon_module_name: имя аддона (__name__ из __init__.py).
    """
    dialog = DeckSelectorDialog(addon_module_name, parent or mw)
    if dialog.exec():
        return dialog.selected_deck_ids()
    return None