"""
language_dialog.py — диалог выбора языка.
"""

try:
    from aqt import mw
    from aqt.qt import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, Qt, QPalette
    from aqt.utils import tooltip
except ImportError:
    pass

from .i18n import t, get_lang, set_lang


class LanguageDialog(QDialog):
    def __init__(self, config, addon_module_name, parent=None):
        super().__init__(parent or mw)
        self._config = config
        self._addon_module_name = addon_module_name
        self._selected = config.get("language", "ru")

        # Получаем цвета из темы Anki
        try:
            palette = mw.app.palette()
            bg_color = palette.color(QPalette.ColorRole.Window).name()
            text_color = palette.color(QPalette.ColorRole.WindowText).name()
            base_color = palette.color(QPalette.ColorRole.Base).name()
        except Exception:
            bg_color = "#f5f5f7"
            text_color = "#1f1f23"
            base_color = "#ffffff"

        self.setWindowTitle("Anker — Language / Язык")
        self.setMinimumWidth(350)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg_color};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Choose language / Выберите язык")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {text_color};")
        layout.addWidget(title)

        self.ru_btn = self._create_button("Русский")
        self.ru_btn.clicked.connect(lambda: self._select("ru"))
        layout.addWidget(self.ru_btn)

        self.en_btn = self._create_button("English")
        self.en_btn.clicked.connect(lambda: self._select("en"))
        layout.addWidget(self.en_btn)

        btn_row = QHBoxLayout()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {base_color};
                color: {text_color};
                border: 1px solid #c8c8ce;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: #c8c8ce;
            }}
        """)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(36)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
        """)
        save_btn.clicked.connect(self._save)

        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        self._update_buttons()

    def _create_button(self, text):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setFixedHeight(44)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #e5e5ea;
                color: #1c1c1e;
                border: 2px solid #c6c6c8;
                border-radius: 8px;
                font-size: 15px;
                font-weight: 600;
            }
            QPushButton:checked {
                background-color: #0078d4;
                color: white;
                border-color: #0078d4;
            }
            QPushButton:hover {
                background-color: #d1d1d6;
            }
            QPushButton:checked:hover {
                background-color: #106ebe;
            }
        """)
        return btn

    def _select(self, lang):
        self._selected = lang
        self._update_buttons()

    def _update_buttons(self):
        self.ru_btn.setChecked(self._selected == "ru")
        self.en_btn.setChecked(self._selected == "en")

    # language_dialog.py, метод _save
    def _save(self):
        self._config["language"] = self._selected
        try:
            mw.addonManager.writeConfig(self._addon_module_name, self._config)
            from .i18n import set_lang, refresh_cache
            set_lang(self._selected)
            refresh_cache()  # ← добавить это
            tooltip(f"Anker language set to: {self._selected}")
            self.accept()
        except Exception as e:
            tooltip(f"Failed to save language: {e}")
            self.reject()