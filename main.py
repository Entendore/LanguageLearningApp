import sys
import random
import unicodedata
import sqlite3
import csv
import os
import string
import re
import urllib.request
import json
from datetime import date, timedelta
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QPushButton, QFrame, QCheckBox, 
                               QProgressBar, QComboBox, QMessageBox, QDialog, 
                               QFormLayout, QDialogButtonBox, QGridLayout, QRadioButton, 
                               QButtonGroup, QTextEdit, QTableWidget, QTableWidgetItem, 
                               QHeaderView, QFileDialog, QAbstractItemView, QSpinBox, QMenu)
from PySide6.QtCore import Qt, QCoreApplication, QTimer, QLocale
from PySide6.QtGui import QFont, QShortcut, QKeySequence, QAction
from PySide6.QtTextToSpeech import QTextToSpeech

DB_FILE = "lingua_master.db"

DEFAULT_VOCAB = {
    "Spanish": {
        "Basics": [
            {"meaning": "Hello", "word": "Hola", "pos": "phrase", "example": "Hola, ¿cómo estás?"},
            {"meaning": "Goodbye", "word": "Adiós", "pos": "phrase", "example": "Adiós, hasta mañana."},
            {"meaning": "Thank you", "word": "Gracias", "pos": "phrase", "example": "Muchas gracias por tu ayuda."}
        ],
        "Animals": [
            {"meaning": "Cat", "word": "Gato", "pos": "noun", "example": "El gato duerme en el sofá."},
            {"meaning": "Dog", "word": "Perro", "pos": "noun", "example": "Mi perro come rápidamente."}
        ],
        "Verbs": [
            {"meaning": "Eat", "word": "Comer", "pos": "verb", "example": "Quiero comer una manzana."},
            {"meaning": "Run", "word": "Correr", "pos": "verb", "example": "Me gusta correr en el parque."}
        ]
    },
    "French": {
        "Basics": [
            {"meaning": "Hello", "word": "Bonjour", "pos": "phrase", "example": "Bonjour, comment ça va?"},
            {"meaning": "Goodbye", "word": "Au revoir", "pos": "phrase", "example": "Au revoir, mon ami."}
        ]
    },
    "German": {
        "Basics": [
            {"meaning": "Hello", "word": "Hallo", "pos": "phrase", "example": "Hallo, wie geht's?"},
            {"meaning": "Please", "word": "Bitte", "pos": "phrase", "example": "Bitte schön."}
        ]
    },
    "Japanese": {
        "Basics": [
            {"meaning": "Hello", "word": "Konnichiwa", "pos": "phrase", "example": "Konnichiwa, ogenki desu ka?"},
            {"meaning": "Thank you", "word": "Arigatou", "pos": "phrase", "example": "Arigatou gozaimasu."}
        ]
    }
}

DEFAULT_MADLIBS = {
    "Spanish": ["El {noun} quiere {verb} en la casa.", "Me gusta comer {noun} con un {adjective} perro."],
    "French": ["Le {noun} aime {verb}.", "Je veux {verb} avec un {adjective} {noun}."],
    "German": ["Der {noun} ist {adjective}.", "Ich will {verb}."],
    "Japanese": ["{noun} ga {verb}.", "{adjective} {noun} ga suki desu."]
}

# --- Stylesheets ---
LIGHT_THEME = """
    QWidget { background-color: #f0f2f5; color: #1c1e21; font-family: 'Segoe UI', Arial, sans-serif; }
    QFrame#cardFrame { background-color: #ffffff; border-radius: 20px; border: 1px solid #e4e6eb; }
    QLabel#instructionLabel { color: #65676b; font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; }
    QLabel#promptLabel { color: #050505; font-size: 28px; font-weight: bold; }
    QLabel#statsLabel { color: #65676b; font-size: 13px; font-weight: bold; }
    QLabel#exampleLabel { color: #65676b; font-size: 14px; font-style: italic; }
    QLineEdit { padding: 15px; border: 2px solid #e4e6eb; border-radius: 12px; background-color: #ffffff; font-size: 16px; }
    QLineEdit:focus { border: 2px solid #1877f2; }
    QComboBox { padding: 8px 12px; border: 1px solid #e4e6eb; border-radius: 8px; background-color: #ffffff; }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox QAbstractItemView { background-color: #ffffff; border: 1px solid #e4e6eb; selection-background-color: #e7f3ff; selection-color: #1877f2; }
    QPushButton { background-color: #e4e6eb; color: #1c1e21; border: none; border-radius: 8px; padding: 10px 16px; font-weight: bold; }
    QPushButton:hover { background-color: #d8dadf; }
    QPushButton#primaryBtn { background-color: #1877f2; color: white; }
    QPushButton#primaryBtn:hover { background-color: #166fe5; }
    QPushButton#primaryBtn:disabled { background-color: #e4e6eb; color: #bcc0c4; }
    QPushButton#successBtn { background-color: #42b72a; color: white; }
    QPushButton#successBtn:hover { background-color: #36a420; }
    QPushButton#successBtn:disabled { background-color: #e4e6eb; color: #bcc0c4; }
    QPushButton#dangerBtn { background-color: transparent; color: #f02849; border: 1px solid #f02849; }
    QPushButton#dangerBtn:hover { background-color: #f02849; color: white; }
    QPushButton#ghostBtn { background-color: transparent; color: #1877f2; }
    QPushButton#ghostBtn:hover { background-color: #e7f3ff; }
    QCheckBox { spacing: 8px; }
    QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 2px solid #bcc0c4; background: white; }
    QCheckBox::indicator:checked { background: #1877f2; border-color: #1877f2; }
    QRadioButton { padding: 8px 16px; border-radius: 12px; background-color: #ffffff; border: 1px solid #e4e6eb; }
    QRadioButton:checked { background-color: #1877f2; color: white; }
    QRadioButton::indicator { width: 0px; height: 0px; }
    QProgressBar { border: none; border-radius: 8px; background-color: #e4e6eb; text-align: center; height: 12px; font-size: 10px; color: #65676b; }
    QProgressBar::chunk { background-color: #1877f2; border-radius: 8px; }
    QProgressBar#masteryBar::chunk { background-color: #673ab7; }
    QProgressBar#dailyBar::chunk { background-color: #42b72a; }
    QTableWidget { background-color: #ffffff; border: 1px solid #e4e6eb; border-radius: 12px; gridline-color: #f0f2f5; }
    QHeaderView::section { background-color: #f0f2f5; padding: 12px; border: none; font-weight: bold; }
    QTableWidget::item { padding: 12px; }
    QTextEdit { border: 2px solid #e4e6eb; border-radius: 12px; padding: 10px; }
"""

DARK_THEME = """
    QWidget { background-color: #1c1e21; color: #e4e6eb; font-family: 'Segoe UI', Arial, sans-serif; }
    QFrame#cardFrame { background-color: #242526; border-radius: 20px; border: 1px solid #393a3b; }
    QLabel#instructionLabel { color: #b0b3b8; font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; }
    QLabel#promptLabel { color: #ffffff; font-size: 28px; font-weight: bold; }
    QLabel#statsLabel { color: #b0b3b8; font-size: 13px; font-weight: bold; }
    QLabel#exampleLabel { color: #b0b3b8; font-size: 14px; font-style: italic; }
    QLineEdit { padding: 15px; border: 2px solid #393a3b; border-radius: 12px; background-color: #242526; color: #e4e6eb; font-size: 16px; }
    QLineEdit:focus { border: 2px solid #2d88ff; }
    QComboBox { padding: 8px 12px; border: 1px solid #393a3b; border-radius: 8px; background-color: #242526; color: #e4e6eb; }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox QAbstractItemView { background-color: #242526; border: 1px solid #393a3b; selection-background-color: #2d88ff; color: #e4e6eb; }
    QPushButton { background-color: #393a3b; color: #e4e6eb; border: none; border-radius: 8px; padding: 10px 16px; font-weight: bold; }
    QPushButton:hover { background-color: #4e4f50; }
    QPushButton#primaryBtn { background-color: #2d88ff; color: white; }
    QPushButton#primaryBtn:hover { background-color: #1877f2; }
    QPushButton#primaryBtn:disabled { background-color: #393a3b; color: #777; }
    QPushButton#successBtn { background-color: #45bd62; color: white; }
    QPushButton#successBtn:hover { background-color: #36a420; }
    QPushButton#successBtn:disabled { background-color: #393a3b; color: #777; }
    QPushButton#dangerBtn { background-color: transparent; color: #f02849; border: 1px solid #f02849; }
    QPushButton#dangerBtn:hover { background-color: #f02849; color: white; }
    QPushButton#ghostBtn { background-color: transparent; color: #2d88ff; }
    QPushButton#ghostBtn:hover { background-color: #3a3b3c; }
    QCheckBox { spacing: 8px; color: #e4e6eb; }
    QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 2px solid #606162; background: #242526; }
    QCheckBox::indicator:checked { background: #2d88ff; border-color: #2d88ff; }
    QRadioButton { padding: 8px 16px; border-radius: 12px; background-color: #242526; border: 1px solid #393a3b; color: #e4e6eb; }
    QRadioButton:checked { background-color: #2d88ff; color: white; border-color: #2d88ff; }
    QRadioButton::indicator { width: 0px; height: 0px; }
    QProgressBar { border: none; border-radius: 8px; background-color: #393a3b; text-align: center; height: 12px; font-size: 10px; color: #ffffff; }
    QProgressBar::chunk { background-color: #2d88ff; border-radius: 8px; }
    QProgressBar#masteryBar::chunk { background-color: #9b59b6; }
    QProgressBar#dailyBar::chunk { background-color: #45bd62; }
    QTableWidget { background-color: #242526; border: 1px solid #393a3b; border-radius: 12px; gridline-color: #393a3b; color: #e4e6eb; }
    QHeaderView::section { background-color: #1c1e21; padding: 12px; border: none; font-weight: bold; color: #b0b3b8; }
    QTableWidget::item { padding: 12px; }
    QTextEdit { border: 2px solid #393a3b; border-radius: 12px; padding: 10px; background-color: #242526; color: #e4e6eb; }
"""

# --- Dialogs ---
class AddWordDialog(QDialog):
    def __init__(self, languages, categories, parent=None, word_data=None):
        super().__init__(parent)
        self.setWindowTitle("Edit/Add Word"); self.setModal(True)
        layout = QFormLayout(self); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(15)
        self.lang_input = QComboBox(); self.lang_input.addItems(languages); self.lang_input.setEditable(True)
        self.cat_input = QComboBox(); self.cat_input.addItems(categories); self.cat_input.setEditable(True)
        self.meaning_input = QLineEdit(); self.word_input = QLineEdit()
        self.pos_input = QComboBox(); self.pos_input.addItems(["noun", "verb", "adjective", "phrase", "other"])
        self.example_input = QTextEdit(); self.example_input.setMaximumHeight(60)
        layout.addRow("Language:", self.lang_input); layout.addRow("Category:", self.cat_input)
        layout.addRow("Meaning:", self.meaning_input); layout.addRow("Word/Sentence:", self.word_input)
        layout.addRow("Part of Speech:", self.pos_input); layout.addRow("Example Sentence:", self.example_input)
        if word_data:
            self.lang_input.setCurrentText(word_data['language']); self.cat_input.setCurrentText(word_data['category'])
            self.meaning_input.setText(word_data['meaning']); self.word_input.setText(word_data['word'])
            self.pos_input.setCurrentText(word_data['pos']); self.example_input.setText(word_data.get('example', ''))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setObjectName("primaryBtn")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

class AddMadLibDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Custom Mad Lib"); self.setModal(True)
        layout = QFormLayout(self); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(15)
        self.lang_input = QComboBox(); self.lang_input.setEditable(True)
        self.template_input = QTextEdit()
        self.template_input.setPlaceholderText("Type story here. Use {noun}, {verb}, {adjective} for blanks.")
        layout.addRow("Language:", self.lang_input); layout.addRow("Template:", self.template_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setObjectName("primaryBtn")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

class DownloadDatasetDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("🌐 Download & Convert Dataset"); self.setModal(True)
        self.setFixedSize(500, 450)
        layout = QVBoxLayout(self); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(15)
        form = QFormLayout()
        self.url_input = QLineEdit(); self.url_input.setPlaceholderText("https://example.com/spanish_words.csv")
        self.lang_input = QLineEdit(); self.lang_input.setPlaceholderText("e.g., Spanish")
        self.cat_input = QLineEdit(); self.cat_input.setPlaceholderText("e.g., Animals")
        self.format_combo = QComboBox(); self.format_combo.addItems(["CSV", "TSV", "JSON"])
        self.format_combo.currentTextChanged.connect(self.update_ui_visibility)
        self.csv_widget = QWidget(); csv_layout = QFormLayout(self.csv_widget); csv_layout.setContentsMargins(0,0,0,0)
        self.col_meaning = QSpinBox(); self.col_meaning.setMinimum(1); self.col_meaning.setMaximum(99)
        self.col_word = QSpinBox(); self.col_word.setMinimum(1); self.col_word.setMaximum(99)
        self.col_pos = QSpinBox(); self.col_pos.setMinimum(0); self.col_pos.setMaximum(99)
        csv_layout.addRow("Meaning Column #:", self.col_meaning); csv_layout.addRow("Word Column #:", self.col_word)
        csv_layout.addRow("POS Column # (0=Skip):", self.col_pos)
        self.json_widget = QWidget(); json_layout = QFormLayout(self.json_widget); json_layout.setContentsMargins(0,0,0,0)
        self.key_meaning = QLineEdit("english"); self.key_word = QLineEdit("foreign"); self.key_pos = QLineEdit("pos")
        json_layout.addRow("Meaning Key:", self.key_meaning); json_layout.addRow("Word Key:", self.key_word); json_layout.addRow("POS Key:", self.key_pos)
        self.json_widget.hide()
        form.addRow("URL:", self.url_input); form.addRow("Language:", self.lang_input); form.addRow("Category:", self.cat_input)
        form.addRow("Format:", self.format_combo)
        layout.addLayout(form); layout.addWidget(self.csv_widget); layout.addWidget(self.json_widget)
        self.status_label = QLabel(""); self.status_label.setWordWrap(True); layout.addWidget(self.status_label)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setObjectName("primaryBtn"); buttons.button(QDialogButtonBox.Ok).setText("Download & Import")
        buttons.accepted.connect(self.start_download); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def update_ui_visibility(self, fmt):
        self.csv_widget.setVisible(fmt in ["CSV", "TSV"]); self.json_widget.setVisible(fmt == "JSON")

    def start_download(self):
        url = self.url_input.text().strip(); lang = self.lang_input.text().strip(); cat = self.cat_input.text().strip()
        fmt = self.format_combo.currentText()
        if not url or not lang or not cat:
            self.status_label.setText("Error: URL, Language, and Category are required!"); return
        try:
            self.status_label.setText("⏳ Downloading data..."); QApplication.processEvents()
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response: data = response.read().decode('utf-8')
            self.status_label.setText("⏳ Parsing and inserting..."); QApplication.processEvents()
            c = self.conn.cursor(); count = 0
            if fmt in ["CSV", "TSV"]:
                delimiter = ',' if fmt == "CSV" else '\t'
                reader = csv.reader(data.splitlines(), delimiter=delimiter); next(reader, None)
                for row in reader:
                    meaning = row[self.col_meaning.value() - 1]; word = row[self.col_word.value() - 1]
                    pos_idx = self.col_pos.value(); pos = row[pos_idx - 1] if pos_idx > 0 and pos_idx <= len(row) else "other"
                    c.execute("INSERT INTO words (language, category, meaning, word, pos) VALUES (?, ?, ?, ?, ?)", (lang, cat, meaning, word, pos))
                    count += 1
            elif fmt == "JSON":
                items = json.loads(data)
                for item in items:
                    meaning = item.get(self.key_meaning.text(), ""); word = item.get(self.key_word.text(), "")
                    pos = item.get(self.key_pos.text(), "other")
                    if meaning and word:
                        c.execute("INSERT INTO words (language, category, meaning, word, pos) VALUES (?, ?, ?, ?, ?)", (lang, cat, meaning, word, pos))
                        count += 1
            self.conn.commit()
            self.status_label.setText(f"✅ Success! Imported {count} words.")
            QMessageBox.information(self, "Success", f"Successfully imported {count} words!"); self.accept()
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)}")

class DatabaseManagerDialog(QDialog):
    def __init__(self, db_conn, parent=None):
        super().__init__(parent)
        self.conn = db_conn
        self.setWindowTitle("🗄️ Database Manager")
        self.setFixedSize(900, 600); self.setModal(True)
        layout = QVBoxLayout(self); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(15)
        toolbar = QHBoxLayout()
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("🔍 Search words, meanings, categories...")
        self.search_input.textChanged.connect(self.load_table)
        export_btn = QPushButton("📤 Export CSV"); export_btn.clicked.connect(self.export_csv)
        anki_btn = QPushButton("🎴 Export Anki"); anki_btn.clicked.connect(self.export_anki)
        import_btn = QPushButton("📥 Import CSV"); import_btn.clicked.connect(self.import_csv)
        dl_btn = QPushButton("🌐 Download"); dl_btn.setObjectName("primaryBtn"); dl_btn.clicked.connect(self.open_download_dialog)
        add_btn = QPushButton("➕ Add Word"); add_btn.clicked.connect(self.add_word)
        add_madlib_btn = QPushButton("✏️ Mad Lib"); add_madlib_btn.clicked.connect(self.add_madlib)
        reset_btn = QPushButton("🔄 Reset"); reset_btn.setObjectName("dangerBtn"); reset_btn.clicked.connect(self.reset_progress)
        del_btn = QPushButton("🗑️ Delete"); del_btn.setObjectName("dangerBtn"); del_btn.clicked.connect(self.delete_word)
        toolbar.addWidget(self.search_input, 2); toolbar.addWidget(export_btn); toolbar.addWidget(anki_btn); toolbar.addWidget(import_btn)
        toolbar.addWidget(dl_btn); toolbar.addWidget(add_madlib_btn); toolbar.addWidget(add_btn); toolbar.addWidget(reset_btn); toolbar.addWidget(del_btn)
        layout.addLayout(toolbar)
        self.table = QTableWidget(); self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["ID", "Language", "Category", "Meaning", "Word", "POS", "Star", "Example"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.hideColumn(0); self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_word)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.table); self.load_table()

    def show_context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid(): return
        menu = QMenu(self)
        action_star = QAction("⭐ Toggle Star", self); action_star.triggered.connect(self.bulk_toggle_star)
        action_edit = QAction("✏️ Edit", self); action_edit.triggered.connect(lambda: self.edit_word(self.table.currentIndex()))
        action_del = QAction("🗑️ Delete", self); action_del.triggered.connect(self.delete_word)
        menu.addAction(action_star); menu.addAction(action_edit); menu.addAction(action_del)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def bulk_toggle_star(self):
        selected = self.table.selectionModel().selectedRows()
        c = self.conn.cursor()
        for index in selected:
            word_id = self.table.item(index.row(), 0).text()
            current_star = self.table.item(index.row(), 6).text()
            new_status = 0 if current_star == "⭐" else 1
            c.execute("UPDATE words SET is_starred=? WHERE id=?", (new_status, word_id))
        self.conn.commit(); self.load_table()

    def load_table(self):
        search = f"%{self.search_input.text()}%"
        c = self.conn.cursor()
        c.execute("""SELECT id, language, category, meaning, word, pos, is_starred, example FROM words 
                     WHERE language LIKE ? OR category LIKE ? OR meaning LIKE ? OR word LIKE ?""",
                  (search, search, search, search))
        rows = c.fetchall()
        self.table.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            for c_idx, data in enumerate(row):
                if c_idx == 6: item = QTableWidgetItem("⭐" if data == 1 else "☆"); item.setTextAlignment(Qt.AlignCenter)
                else: item = QTableWidgetItem(str(data) if data else "")
                self.table.setItem(r_idx, c_idx, item)

    def reset_progress(self):
        reply = QMessageBox.warning(self, "Reset Progress", "Wipe all stats, mastery, and missed words?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            c = self.conn.cursor()
            c.execute("DELETE FROM mastery"); c.execute("DELETE FROM missed"); c.execute("DELETE FROM daily_stats")
            c.execute("UPDATE stats SET value=0")
            self.conn.commit(); QMessageBox.information(self, "Reset", "All progress has been reset.")

    def open_download_dialog(self):
        dlg = DownloadDatasetDialog(self.conn, self)
        if dlg.exec(): self.load_table()

    def add_word(self):
        c = self.conn.cursor()
        c.execute("SELECT DISTINCT language FROM words"); langs = [r[0] for r in c.fetchall()]
        c.execute("SELECT DISTINCT category FROM words"); cats = [r[0] for r in c.fetchall()]
        dlg = AddWordDialog(langs, cats, self)
        if dlg.exec():
            c.execute("INSERT INTO words (language, category, meaning, word, pos, example) VALUES (?, ?, ?, ?, ?, ?)",
                      (dlg.lang_input.currentText(), dlg.cat_input.currentText(), dlg.meaning_input.text(), dlg.word_input.text(), dlg.pos_input.currentText(), dlg.example_input.toPlainText()))
            self.conn.commit(); self.load_table()

    def add_madlib(self):
        c = self.conn.cursor()
        c.execute("SELECT DISTINCT language FROM words"); langs = [r[0] for r in c.fetchall()]
        dlg = AddMadLibDialog(self); dlg.lang_input.addItems(langs)
        if dlg.exec():
            c.execute("INSERT INTO madlibs (language, template) VALUES (?, ?)", (dlg.lang_input.currentText(), dlg.template_input.toPlainText()))
            self.conn.commit(); QMessageBox.information(self, "Success", "Mad Lib template added!")

    def edit_word(self, index):
        row = index.row(); word_id = self.table.item(row, 0).text()
        c = self.conn.cursor()
        c.execute("SELECT language, category, meaning, word, pos, example FROM words WHERE id=?", (word_id,))
        w_data = c.fetchone()
        if not w_data: return
        data_dict = {'language': w_data[0], 'category': w_data[1], 'meaning': w_data[2], 'word': w_data[3], 'pos': w_data[4], 'example': w_data[5]}
        c.execute("SELECT DISTINCT language FROM words"); langs = [r[0] for r in c.fetchall()]
        c.execute("SELECT DISTINCT category FROM words"); cats = [r[0] for r in c.fetchall()]
        dlg = AddWordDialog(langs, cats, self, word_data=data_dict)
        if dlg.exec():
            c.execute("UPDATE words SET language=?, category=?, meaning=?, word=?, pos=?, example=? WHERE id=?",
                      (dlg.lang_input.currentText(), dlg.cat_input.currentText(), dlg.meaning_input.text(), dlg.word_input.text(), dlg.pos_input.currentText(), dlg.example_input.toPlainText(), word_id))
            self.conn.commit(); self.load_table()

    def delete_word(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected: return
        c = self.conn.cursor()
        for index in selected:
            word_id = self.table.item(index.row(), 0).text()
            c.execute("DELETE FROM words WHERE id=?", (word_id,))
            c.execute("DELETE FROM mastery WHERE word_id=?", (word_id,))
            c.execute("DELETE FROM missed WHERE word_id=?", (word_id,))
        self.conn.commit(); self.load_table()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "vocabulary.csv", "CSV Files (*.csv)")
        if not path: return
        c = self.conn.cursor(); c.execute("SELECT language, category, meaning, word, pos, example FROM words")
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f); writer.writerow(['Language', 'Category', 'Meaning', 'Word', 'POS', 'Example']); writer.writerows(c.fetchall())
        QMessageBox.information(self, "Success", "Vocabulary exported successfully!")

    def export_anki(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Anki Deck", "anki_deck.txt", "Text Files (*.txt)")
        if not path: return
        c = self.conn.cursor(); c.execute("SELECT word, meaning, example FROM words")
        with open(path, 'w', encoding='utf-8') as f:
            for row in c.fetchall():
                front = row[0]
                back = f"{row[1]}\n<br><br><i>{row[2]}</i>" if row[2] else row[1]
                f.write(f"{front}\t{back}\n")
        QMessageBox.information(self, "Success", "Anki TSV exported successfully!")

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import CSV", "", "CSV Files (*.csv)")
        if not path: return
        c = self.conn.cursor()
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f); next(reader, None)
            for row in reader:
                if len(row) >= 5: 
                    example = row[5] if len(row) > 5 else ""
                    c.execute("INSERT INTO words (language, category, meaning, word, pos, example) VALUES (?, ?, ?, ?, ?, ?)", (row[0], row[1], row[2], row[3], row[4], example))
        self.conn.commit(); self.load_table(); QMessageBox.information(self, "Success", "Vocabulary imported successfully!")


# --- Main App ---
class LanguageLearningApp(QWidget):
    def __init__(self):
        super().__init__()
        self.conn = sqlite3.connect(DB_FILE); self.conn.row_factory = sqlite3.Row
        self.init_db()
        self.check_day_streak() # Check streak on startup
        
        self.current_word = None
        self.tts = QTextToSpeech(); self.current_tts_language = None
        self.mode = "typing"; self.is_review_mode = False
        self.madlib_template = None; self.madlib_blanks = []; self.madlib_filled = []
        
        self.init_ui(); self.populate_languages(); self.next_word()

    def init_db(self):
        c = self.conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT, language TEXT, category TEXT, meaning TEXT, word TEXT, pos TEXT, is_starred INTEGER DEFAULT 0, example TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS madlibs (id INTEGER PRIMARY KEY AUTOINCREMENT, language TEXT, template TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS mastery (word_id INTEGER PRIMARY KEY, level INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS missed (word_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS daily_stats (date TEXT PRIMARY KEY, count INTEGER DEFAULT 0)""")
        try: c.execute("ALTER TABLE words ADD COLUMN is_starred INTEGER DEFAULT 0")
        except: pass
        try: c.execute("ALTER TABLE words ADD COLUMN example TEXT")
        except: pass
        c.execute("SELECT COUNT(*) FROM words")
        if c.fetchone()[0] == 0:
            for lang, cats in DEFAULT_VOCAB.items():
                for cat, words in cats.items():
                    for w in words:
                        c.execute("INSERT INTO words (language, category, meaning, word, pos, example) VALUES (?, ?, ?, ?, ?, ?)", (lang, cat, w['meaning'], w['word'], w['pos'], w.get('example', '')))
        c.execute("SELECT COUNT(*) FROM madlibs")
        if c.fetchone()[0] == 0:
            for lang, templates in DEFAULT_MADLIBS.items():
                for t in templates: c.execute("INSERT INTO madlibs (language, template) VALUES (?, ?)", (lang, t))
        for key in ["score", "streak", "total_questions", "day_streak", "last_study_date"]:
            c.execute("INSERT OR IGNORE INTO stats (key, value) VALUES (?, ?)", (key, 0))
        self.conn.commit()

    def check_day_streak(self):
        today = date.today().isoformat()
        last_date = self.get_stat("last_study_date")
        day_streak = self.get_stat("day_streak")
        
        if last_date != today:
            # If last study wasn't yesterday, streak is broken
            if last_date != (date.today() - timedelta(days=1)).isoformat():
                self.set_stat("day_streak", 0)

    def init_ui(self):
        self.setWindowTitle("Lingua Master")
        self.setMinimumSize(750, 850)
        layout = QVBoxLayout(); layout.setContentsMargins(30, 30, 30, 30); layout.setSpacing(20)
        
        header_layout = QHBoxLayout()
        title_label = QLabel("🦜 Lingua Master"); title_label.setStyleSheet("font-size: 24px; font-weight: 900; color: #1877f2;")
        
        # Quick Dictionary Lookup
        self.lookup_input = QLineEdit(); self.lookup_input.setPlaceholderText("🔍 Quick lookup...")
        self.lookup_input.setFixedWidth(150)
        self.lookup_input.textChanged.connect(self.quick_lookup)
        
        self.db_manager_btn = QPushButton("🗄️ Database"); self.db_manager_btn.setObjectName("ghostBtn"); self.db_manager_btn.clicked.connect(self.open_db_manager)
        self.review_btn = QPushButton("📖 Smart Review: OFF"); self.review_btn.setCheckable(True); self.review_btn.toggled.connect(self.toggle_review_mode)
        self.dark_cb = QCheckBox("🌙 Dark Mode"); self.dark_cb.toggled.connect(self.toggle_dark_mode)
        header_layout.addWidget(title_label); header_layout.addStretch()
        header_layout.addWidget(self.lookup_input); header_layout.addWidget(self.review_btn); header_layout.addWidget(self.db_manager_btn); header_layout.addWidget(self.dark_cb)
        layout.addLayout(header_layout)

        stats_layout = QHBoxLayout()
        self.stats_label = QLabel("Score: 0 | Streak: 0 🔥"); self.stats_label.setObjectName("statsLabel")
        stats_layout.addWidget(self.stats_label); stats_layout.addStretch()
        layout.addLayout(stats_layout)

        prog_layout = QVBoxLayout(); prog_layout.setSpacing(8)
        self.progress_bar = QProgressBar(); self.progress_bar.setValue(0); self.progress_bar.setFormat("Overall Accuracy: %p%")
        self.mastery_bar = QProgressBar(); self.mastery_bar.setValue(0); self.mastery_bar.setFormat("Mastered: %v / %m"); self.mastery_bar.setObjectName("masteryBar")
        self.daily_bar = QProgressBar(); self.daily_bar.setValue(0); self.daily_bar.setFormat("Daily Goal: %v / %m"); self.daily_bar.setObjectName("dailyBar"); self.daily_bar.setMaximum(20)
        prog_layout.addWidget(self.progress_bar); prog_layout.addWidget(self.mastery_bar); prog_layout.addWidget(self.daily_bar)
        layout.addLayout(prog_layout)

        settings_bar = QHBoxLayout()
        self.lang_combo = QComboBox(); self.lang_combo.currentTextChanged.connect(self.on_language_changed)
        self.category_combo = QComboBox(); self.category_combo.currentTextChanged.connect(self.next_word)
        
        # TTS Voice Selector
        self.voice_combo = QComboBox()
        self.voice_combo.currentIndexChanged.connect(self.on_voice_changed)
        
        self.reverse_cb = QCheckBox("Reverse Mode"); self.reverse_cb.toggled.connect(self.next_word)
        self.fav_cb = QCheckBox("⭐ Favorites Only"); self.fav_cb.toggled.connect(self.next_word)
        self.autoplay_cb = QCheckBox("🔊 Autoplay Audio"); self.autoplay_cb.toggled.connect(self.next_word)
        
        settings_bar.addWidget(QLabel("Language:")); settings_bar.addWidget(self.lang_combo); settings_bar.addSpacing(10)
        settings_bar.addWidget(QLabel("Category:")); settings_bar.addWidget(self.category_combo); settings_bar.addSpacing(10)
        settings_bar.addWidget(QLabel("Voice:")); settings_bar.addWidget(self.voice_combo)
        settings_bar.addStretch()
        settings_bar.addWidget(self.fav_cb); settings_bar.addWidget(self.autoplay_cb); settings_bar.addWidget(self.reverse_cb)
        layout.addLayout(settings_bar)

        mode_layout = QHBoxLayout(); mode_layout.setSpacing(8)
        self.mode_group = QButtonGroup(self)
        self.rb_typing = QRadioButton("✍️ Type"); self.rb_mc = QRadioButton("🔘 Choice")
        self.rb_builder = QRadioButton("🧱 Build"); self.rb_madlib = QRadioButton("📝 Mad Lib")
        self.rb_dictation = QRadioButton("👂 Dictation"); self.rb_cloze = QRadioButton("🧩 Cloze") # New Mode
        self.rb_typing.setChecked(True)
        self.mode_group.addButton(self.rb_typing, 0); self.mode_group.addButton(self.rb_mc, 1)
        self.mode_group.addButton(self.rb_builder, 2); self.mode_group.addButton(self.rb_madlib, 3)
        self.mode_group.addButton(self.rb_dictation, 4); self.mode_group.addButton(self.rb_cloze, 5)
        self.mode_group.idClicked.connect(self.change_mode)
        mode_layout.addWidget(self.rb_typing); mode_layout.addWidget(self.rb_mc)
        mode_layout.addWidget(self.rb_builder); mode_layout.addWidget(self.rb_madlib)
        mode_layout.addWidget(self.rb_dictation); mode_layout.addWidget(self.rb_cloze); mode_layout.addStretch()
        layout.addLayout(mode_layout)

        self.card_frame = QFrame(); self.card_frame.setObjectName("cardFrame")
        card_layout = QVBoxLayout(self.card_frame); card_layout.setContentsMargins(30, 40, 30, 30); card_layout.setSpacing(15)
        top_card_layout = QHBoxLayout()
        self.instruction_label = QLabel("..."); self.instruction_label.setObjectName("instructionLabel")
        self.star_btn = QPushButton("☆"); self.star_btn.setObjectName("ghostBtn")
        self.star_btn.setStyleSheet("font-size: 24px; padding: 0px; background: transparent; border: none;")
        self.star_btn.clicked.connect(self.toggle_star)
        top_card_layout.addStretch(); top_card_layout.addWidget(self.instruction_label); top_card_layout.addStretch()
        top_card_layout.addWidget(self.star_btn, alignment=Qt.AlignTop)
        card_layout.addLayout(top_card_layout)
        
        self.prompt_label = QLabel("..."); self.prompt_label.setAlignment(Qt.AlignCenter)
        self.prompt_label.setObjectName("promptLabel"); self.prompt_label.setWordWrap(True)
        card_layout.addWidget(self.prompt_label)
        
        self.example_label = QLabel(""); self.example_label.setObjectName("exampleLabel")
        self.example_label.setAlignment(Qt.AlignCenter); self.example_label.setWordWrap(True)
        card_layout.addWidget(self.example_label)
        
        tts_layout = QHBoxLayout()
        self.tts_button = QPushButton("🔊 Hear"); self.tts_button.setObjectName("ghostBtn"); self.tts_button.clicked.connect(lambda: self.speak_word(0.0))
        self.tts_slow_button = QPushButton("🐢 Slow"); self.tts_slow_button.setObjectName("ghostBtn"); self.tts_slow_button.clicked.connect(lambda: self.speak_word(-0.4))
        tts_layout.addStretch(); tts_layout.addWidget(self.tts_button); tts_layout.addWidget(self.tts_slow_button)
        card_layout.addLayout(tts_layout); 
        layout.addWidget(self.card_frame, 1)

        self.answer_stack = QVBoxLayout()
        self.typing_widget = QWidget(); typing_layout = QVBoxLayout(self.typing_widget); typing_layout.setContentsMargins(0,0,0,0)
        self.hint_label = QLabel(""); self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setStyleSheet("color: #f39c12; font-weight: bold; font-family: monospace;")
        typing_layout.addWidget(self.hint_label)
        self.input_field = QLineEdit(); self.input_field.setFont(QFont("Arial", 14))
        self.input_field.returnPressed.connect(lambda: self.check_answer(self.input_field.text()))
        typing_layout.addWidget(self.input_field)
        
        self.mc_widget = QWidget(); mc_layout = QGridLayout(self.mc_widget); mc_layout.setSpacing(10)
        self.mc_buttons = []
        for i in range(4):
            btn = QPushButton(); mc_layout.addWidget(btn, i//2, i%2); self.mc_buttons.append(btn)

        self.builder_widget = QWidget(); builder_layout = QVBoxLayout(self.builder_widget); builder_layout.setSpacing(10)
        self.builder_answer_label = QLabel("Click words below to build the sentence...")
        self.builder_answer_label.setWordWrap(True); self.builder_answer_label.setAlignment(Qt.AlignCenter); self.builder_answer_label.setMinimumHeight(60)
        self.builder_answer_label.setStyleSheet("background-color: transparent; border: 2px dashed #e4e6eb; border-radius: 12px; padding: 10px; font-size: 16px; font-weight: bold;")
        builder_layout.addWidget(self.builder_answer_label)
        self.bank_layout = QGridLayout(); builder_layout.addLayout(self.bank_layout)
        
        self.answer_stack.addWidget(self.typing_widget); self.answer_stack.addWidget(self.mc_widget); self.answer_stack.addWidget(self.builder_widget)
        self.mc_widget.hide(); self.builder_widget.hide(); layout.addLayout(self.answer_stack)

        self.feedback_label = QLabel(""); self.feedback_label.setAlignment(Qt.AlignCenter)
        self.feedback_label.setStyleSheet("font-size: 14px; font-weight: bold;"); layout.addWidget(self.feedback_label)
        
        button_layout = QHBoxLayout()
        self.hint_button = QPushButton("💡 Hint"); self.hint_button.clicked.connect(self.show_hint)
        self.check_button = QPushButton("Check Answer"); self.check_button.setObjectName("successBtn"); self.check_button.setMinimumHeight(50)
        self.check_button.clicked.connect(lambda: self.check_answer(self.input_field.text()))
        button_layout.addWidget(self.hint_button); button_layout.addWidget(self.check_button, 1)
        layout.addLayout(button_layout)

        self.setLayout(layout); self.update_stats_ui()
        QApplication.instance().setStyleSheet(LIGHT_THEME)
        
        QShortcut(QKeySequence("1"), self).activated.connect(lambda: self.mc_buttons[0].click() if self.mode in ["mc", "madlib"] else None)
        QShortcut(QKeySequence("2"), self).activated.connect(lambda: self.mc_buttons[1].click() if self.mode in ["mc", "madlib"] else None)
        QShortcut(QKeySequence("3"), self).activated.connect(lambda: self.mc_buttons[2].click() if self.mode in ["mc", "madlib"] else None)
        QShortcut(QKeySequence("4"), self).activated.connect(lambda: self.mc_buttons[3].click() if self.mode in ["mc", "madlib"] else None)
        QShortcut(QKeySequence("h"), self).activated.connect(self.show_hint)
        
        self.populate_voices()

    def populate_voices(self):
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        voices = self.tts.availableVoices()
        for v in voices:
            self.voice_combo.addItem(f"{v.name()} ({v.locale().name()})")
        self.voice_combo.blockSignals(False)

    def on_voice_changed(self, index):
        voices = self.tts.availableVoices()
        if 0 <= index < len(voices):
            self.tts.setVoice(voices[index])
            self.current_tts_language = "manual"

    def quick_lookup(self, text):
        if len(text) < 2: return
        c = self.conn.cursor()
        c.execute("SELECT word, meaning FROM words WHERE word LIKE ? OR meaning LIKE ? LIMIT 1", (f"%{text}%", f"%{text}%"))
        r = c.fetchone()
        if r:
            self.lookup_input.setToolTip(f"{r['word']} = {r['meaning']}")

    def toggle_star(self):
        if not self.current_word: return
        c = self.conn.cursor()
        new_status = 0 if self.current_word['is_starred'] == 1 else 1
        c.execute("UPDATE words SET is_starred=? WHERE id=?", (new_status, self.current_word['id']))
        self.conn.commit()
        self.current_word['is_starred'] = new_status
        self.update_star_btn()

    def update_star_btn(self):
        self.star_btn.setText("⭐" if self.current_word and self.current_word['is_starred'] == 1 else "☆")

    def get_stat(self, key):
        c = self.conn.cursor(); c.execute("SELECT value FROM stats WHERE key=?", (key,)); r = c.fetchone()
        return r['value'] if r else 0

    def set_stat(self, key, value):
        c = self.conn.cursor(); c.execute("INSERT OR REPLACE INTO stats (key, value) VALUES (?, ?)", (key, value)); self.conn.commit()

    def get_word_mastery(self, word_id):
        c = self.conn.cursor(); c.execute("SELECT level FROM mastery WHERE word_id=?", (word_id,)); r = c.fetchone()
        return r['level'] if r else 0

    def update_mastery(self, word_id, correct):
        cur = self.get_word_mastery(word_id)
        new_level = min(3, cur + 1) if correct else max(0, cur - 1)
        c = self.conn.cursor(); c.execute("INSERT OR REPLACE INTO mastery (word_id, level) VALUES (?, ?)", (word_id, new_level)); self.conn.commit()

    def get_missed_words(self):
        c = self.conn.cursor(); c.execute("SELECT word_id FROM missed")
        return [row['word_id'] for row in c.fetchall()]

    def add_missed(self, word_id):
        c = self.conn.cursor(); c.execute("INSERT OR IGNORE INTO missed (word_id) VALUES (?)", (word_id,)); self.conn.commit()

    def remove_missed(self, word_id):
        c = self.conn.cursor(); c.execute("DELETE FROM missed WHERE word_id=?", (word_id,)); self.conn.commit()
        
    def increment_daily_goal(self):
        today = date.today().isoformat()
        c = self.conn.cursor()
        c.execute("INSERT OR IGNORE INTO daily_stats (date, count) VALUES (?, 0)", (today,))
        c.execute("UPDATE daily_stats SET count = count + 1 WHERE date=?", (today,))
        self.conn.commit()
        
        # Update Day Streak if daily goal is met
        if self.get_stat("last_study_date") != today:
            count = c.execute("SELECT count FROM daily_stats WHERE date=?", (today,)).fetchone()['count']
            if count >= 20: # Daily goal is 20
                last_date = self.get_stat("last_study_date")
                day_streak = self.get_stat("day_streak")
                if last_date == (date.today() - timedelta(days=1)).isoformat():
                    self.set_stat("day_streak", day_streak + 1)
                else:
                    self.set_stat("day_streak", 1)
                self.set_stat("last_study_date", today)

    def open_db_manager(self):
        dlg = DatabaseManagerDialog(self.conn, self)
        dlg.exec(); self.populate_languages()

    def toggle_review_mode(self, checked):
        self.is_review_mode = checked
        self.review_btn.setText(f"📖 Smart Review: {'ON' if checked else 'OFF'}")
        self.review_btn.setObjectName("primaryBtn" if checked else "")
        self.review_btn.style().unpolish(self.review_btn); self.review_btn.style().polish(self.review_btn)
        if checked:
            c = self.conn.cursor()
            c.execute("SELECT COUNT(*) FROM words w LEFT JOIN mastery m ON w.id = m.word_id WHERE m.level IS NULL OR m.level < 3")
            if c.fetchone()[0] == 0:
                QMessageBox.information(self, "Review Mode", "You have mastered all available words!")
                self.review_btn.setChecked(False); return
        self.next_word()

    def change_mode(self, id):
        if id == 0: self.mode = "typing"
        elif id == 1: self.mode = "mc"
        elif id == 2: self.mode = "builder"
        elif id == 3: self.mode = "madlib"
        elif id == 4: self.mode = "dictation"
        elif id == 5: self.mode = "cloze"
        self.typing_widget.setVisible(self.mode in ["typing", "dictation", "cloze"])
        self.mc_widget.setVisible(self.mode in ["mc", "madlib"])
        self.builder_widget.setVisible(self.mode == "builder")
        self.hint_button.setEnabled(self.mode in ["typing", "dictation", "cloze"])
        self.next_word()

    def populate_languages(self):
        self.lang_combo.blockSignals(True); self.lang_combo.clear()
        c = self.conn.cursor(); c.execute("SELECT DISTINCT language FROM words")
        self.lang_combo.addItems([row['language'] for row in c.fetchall()]); self.lang_combo.blockSignals(False)
        self.on_language_changed(self.lang_combo.currentText())

    def on_language_changed(self, language):
        if not language: return
        self.category_combo.blockSignals(True); self.category_combo.clear()
        self.category_combo.addItem("All Categories")
        c = self.conn.cursor(); c.execute("SELECT DISTINCT category FROM words WHERE language=?", (language,))
        self.category_combo.addItems([row['category'] for row in c.fetchall()])
        self.category_combo.blockSignals(False)
        self.configure_tts(language); self.next_word()

    def configure_tts(self, language_name):
        # If user manually selected a voice, don't auto-change
        if self.current_tts_language == "manual": return
        
        locale_map = {"Spanish": QLocale.Spanish, "French": QLocale.French, "German": QLocale.German, "Japanese": QLocale.Japanese, "Italian": QLocale.Italian, "Chinese": QLocale.Chinese}
        target = locale_map.get(language_name, QLocale.English)
        for i, v in enumerate(self.tts.availableVoices()):
            if v.locale().language() == target:
                self.tts.setVoice(v); self.current_tts_language = language_name
                self.voice_combo.blockSignals(True); self.voice_combo.setCurrentIndex(i); self.voice_combo.blockSignals(False)
                self.tts_button.setEnabled(True); self.tts_slow_button.setEnabled(True); return
        self.tts_button.setEnabled(False); self.tts_slow_button.setEnabled(False)

    def toggle_dark_mode(self, checked):
        QApplication.instance().setStyleSheet(DARK_THEME if checked else LIGHT_THEME)

    def clean_text(self, text):
        text = unicodedata.normalize('NFKD', text)
        text = "".join([c for c in text if not unicodedata.combining(c)])
        text = text.translate(str.maketrans('', '', string.punctuation))
        text = text.replace('¿', '').replace('¡', '')
        return text.lower().strip()

    def update_mastery_bar(self, available_words):
        mastered_count = sum(1 for w in available_words if self.get_word_mastery(w['id']) == 3)
        self.mastery_bar.setMaximum(len(available_words)); self.mastery_bar.setValue(mastered_count)
        today = date.today().isoformat()
        c = self.conn.cursor(); c.execute("SELECT count FROM daily_stats WHERE date=?", (today,))
        r = c.fetchone()
        count = r['count'] if r else 0
        self.daily_bar.setValue(count)

    def next_word(self):
        if self.mode == "madlib": self.start_madlib(); return

        current_lang = self.lang_combo.currentText()
        if not current_lang: return
        
        c = self.conn.cursor()
        selected_cat = self.category_combo.currentText()
        query = "SELECT * FROM words WHERE language=?"
        params = [current_lang]
        if selected_cat != "All Categories": query += " AND category=?"; params.append(selected_cat)
        if self.fav_cb.isChecked(): query += " AND is_starred=1"
        
        # Cloze mode requires an example sentence
        if self.mode == "cloze": query += " AND example IS NOT NULL AND example != ''"
            
        c.execute(query, tuple(params))
        available_words = [dict(row) for row in c.fetchall()]
            
        self.update_mastery_bar(available_words)
            
        if not available_words: 
            self.prompt_label.setText("No words found!"); self.star_btn.setText("☆"); return

        if self.is_review_mode:
            available_words = [w for w in available_words if self.get_word_mastery(w['id']) < 3]
            if not available_words:
                QMessageBox.information(self, "Review Complete", "You have mastered all words in this filter!")
                self.review_btn.setChecked(False); return

        weighted_pool = []
        for word in available_words:
            mastery = self.get_word_mastery(word['id'])
            weight = 10 if mastery == 0 else (5 if mastery == 1 else (2 if mastery == 2 else 1))
            weighted_pool.extend([word] * weight)
            
        self.current_word = random.choice(weighted_pool)
        self.update_star_btn()
        self.example_label.setText(""); self.example_label.hide()
        
        correct_answer = ""
        if self.mode == "dictation":
            self.instruction_label.setText("👂 Listen and type what you hear")
            self.prompt_label.setText("🎧")
            correct_answer = self.current_word['word']
            QTimer.singleShot(300, lambda: self.speak_word(0.0))
        elif self.mode == "cloze":
            self.instruction_label.setText("🧩 Fill in the blank")
            # Replace the word in the example with underscores
            word = self.current_word['word']
            cloze_text = re.sub(re.escape(word), "_____", self.current_word['example'], flags=re.IGNORECASE)
            self.prompt_label.setText(cloze_text)
            correct_answer = word
        elif self.reverse_cb.isChecked():
            self.instruction_label.setText("What does this mean?")
            self.prompt_label.setText(f"{self.current_word['word']}")
            correct_answer = self.current_word['meaning']
        else:
            self.instruction_label.setText(f"Translate to {current_lang}")
            self.prompt_label.setText(f"{self.current_word['meaning']}")
            correct_answer = self.current_word['word']
            
        self.feedback_label.setText(""); self.hint_label.setText(""); self.input_field.setStyleSheet("")
        
        if self.mode == "mc":
            wrong_choices = [w for w in available_words if w['word' if not self.reverse_cb.isChecked() else 'meaning'] != correct_answer]
            choices = random.sample(wrong_choices, min(3, len(wrong_choices))) + [self.current_word]
            random.shuffle(choices)
            for i, btn in enumerate(self.mc_buttons):
                if i < len(choices):
                    btn.setText(f"{i+1}. {choices[i]['word' if not self.reverse_cb.isChecked() else 'meaning']}")
                    btn.setEnabled(True); btn.setStyleSheet("")
                    btn.clicked.disconnect()
                    btn.clicked.connect(lambda checked, t=choices[i]['word' if not self.reverse_cb.isChecked() else 'meaning']: self.check_answer(t))
                else:
                    btn.setText(""); btn.setEnabled(False)
            self.check_button.setEnabled(False)
        elif self.mode == "builder":
            self.setup_builder(correct_answer); self.check_button.setEnabled(True)
        else: # Typing, Dictation, Cloze
            self.input_field.clear(); self.input_field.setEnabled(True); self.input_field.setFocus()
            self.check_button.setEnabled(True); self.hint_button.setEnabled(True)
            
        self.check_button.setText("Check Answer"); self.check_button.setObjectName("successBtn")
        self.check_button.style().unpolish(self.check_button); self.check_button.style().polish(self.check_button)
        try: self.check_button.clicked.disconnect()
        except: pass
        if self.mode == "builder": self.check_button.clicked.connect(self.check_builder_answer)
        else: self.check_button.clicked.connect(lambda: self.check_answer(self.input_field.text()))
        
        if self.autoplay_cb.isChecked() and self.mode not in ["dictation", "cloze"]: self.speak_word(0.0)

    def start_madlib(self):
        lang = self.lang_combo.currentText()
        c = self.conn.cursor(); c.execute("SELECT template FROM madlibs WHERE language=?", (lang,))
        templates = [row['template'] for row in c.fetchall()]
        if not templates:
            self.instruction_label.setText("No Mad Libs for this language."); self.prompt_label.setText("Add one in Database Manager!"); return
        self.madlib_template = random.choice(templates)
        self.madlib_blanks = re.findall(r'\{(.*?)\}', self.madlib_template)
        self.madlib_filled = []
        self.instruction_label.setText("Mad Libs! Fill in the blanks:")
        self.advance_madlib()

    def advance_madlib(self):
        if not self.madlib_blanks: self.finish_madlib(); return
        required_pos = self.madlib_blanks.pop(0)
        display_text = self.madlib_template
        for w in self.madlib_filled:
            display_text = re.sub(r'\{.*?\}', f'<b style="color:#42b72a;">{w}</b>', display_text, count=1)
        display_text = display_text.replace(f'{{{required_pos}}}', f'<b style="color:#f02849;">[{required_pos}]</b>', 1)
        self.prompt_label.setText(display_text)
        c = self.conn.cursor()
        c.execute("SELECT * FROM words WHERE language=? AND pos=?", (self.lang_combo.currentText(), required_pos))
        pos_words = [dict(row) for row in c.fetchall()]
        if len(pos_words) < 4: 
            c.execute("SELECT * FROM words WHERE language=?", (self.lang_combo.currentText(),))
            pos_words = [dict(row) for row in c.fetchall()]
        choices = random.sample(pos_words, min(4, len(pos_words)))
        for i, btn in enumerate(self.mc_buttons):
            if i < len(choices):
                btn.setText(f"{i+1}. {choices[i]['word']}"); btn.setEnabled(True)
                btn.setStyleSheet("padding: 15px; font-size: 14px; font-weight: bold; border-radius: 12px; background-color: #1877f2; color: white; border: none;")
                btn.clicked.disconnect()
                btn.clicked.connect(lambda checked, t=choices[i]['word']: self.handle_madlib_choice(t))
            else:
                btn.setText(""); btn.setEnabled(False)
        self.check_button.setEnabled(False)

    def handle_madlib_choice(self, word_text):
        self.madlib_filled.append(word_text); self.advance_madlib()

    def finish_madlib(self):
        final_sentence = self.madlib_template
        for w in self.madlib_filled:
            final_sentence = re.sub(r'\{.*?\}', f'<b style="color:#42b72a;">{w}</b>', final_sentence, count=1)
        self.prompt_label.setText(final_sentence)
        self.feedback_label.setText("🎉 Mad Lib complete!"); self.feedback_label.setStyleSheet("color: #9b59b6; font-weight: bold;")
        self.set_stat("score", self.get_stat("score") + 1)
        self.set_stat("total_questions", self.get_stat("total_questions") + 1)
        self.increment_daily_goal()
        self.update_stats_ui()
        for btn in self.mc_buttons: btn.setEnabled(False)
        plain_sentence = re.sub(r'<.*?>', '', final_sentence)
        self.speak_word(0.0, override_text=plain_sentence)
        self.check_button.setText("Next Story ➔"); self.check_button.setEnabled(True); self.check_button.setObjectName("primaryBtn")
        self.check_button.style().unpolish(self.check_button); self.check_button.style().polish(self.check_button)
        try: self.check_button.clicked.disconnect()
        except: pass
        self.check_button.clicked.connect(self.next_word)

    def smart_split_sentence(self, text):
        return re.findall(r"\w+|[^\w\s]", text)

    def setup_builder(self, correct_sentence):
        self.builder_answer_list = []
        words = self.smart_split_sentence(correct_sentence); random.shuffle(words)
        for i in reversed(range(self.bank_layout.count())): self.bank_layout.itemAt(i).widget().setParent(None)
        cols = 4
        for i, word in enumerate(words):
            btn = QPushButton(word); btn.setCheckable(True)
            btn.setStyleSheet("padding: 12px; font-size: 14px; font-weight: bold; border-radius: 12px; background-color: #1877f2; color: white;")
            btn.clicked.connect(lambda checked, b=btn: self.toggle_builder_word(b))
            self.bank_layout.addWidget(btn, i // cols, i % cols)
        self.update_builder_answer_label()

    def toggle_builder_word(self, btn):
        if btn.isChecked(): self.builder_answer_list.append(btn)
        else:
            if btn in self.builder_answer_list: self.builder_answer_list.remove(btn)
        self.update_builder_answer_label()

    def update_builder_answer_label(self):
        text = " ".join([btn.text() for btn in self.builder_answer_list])
        self.builder_answer_label.setText(text if text else "Click words below to build the sentence...")

    def check_builder_answer(self):
        user_answer = " ".join([btn.text() for btn in self.builder_answer_list])
        self.check_answer(user_answer)

    def check_answer(self, user_answer_str):
        user_answer = self.clean_text(user_answer_str)
        correct_answer = self.clean_text(self.current_word['word'] if not self.reverse_cb.isChecked() else self.current_word['meaning'])
        if not user_answer: return 

        self.set_stat("total_questions", self.get_stat("total_questions") + 1)
        is_correct = (user_answer == correct_answer)

        if is_correct:
            self.set_stat("score", self.get_stat("score") + 1)
            self.set_stat("streak", self.get_stat("streak") + 1)
            self.feedback_label.setText("✅ Correct!"); self.feedback_label.setStyleSheet("color: #42b72a; font-weight: bold;")
            self.input_field.setStyleSheet("border: 2px solid #42b72a; background-color: #eafbf1;")
            self.remove_missed(self.current_word['id'])
            self.increment_daily_goal()
        else:
            self.set_stat("streak", 0)
            self.feedback_label.setText(f"❌ Incorrect. Answer was: {correct_answer}"); self.feedback_label.setStyleSheet("color: #f02849; font-weight: bold;")
            self.input_field.setStyleSheet("border: 2px solid #f02849; background-color: #fce8e8;")
            self.add_missed(self.current_word['id'])

        if self.current_word.get('example') and self.mode != "cloze":
            self.example_label.setText(f"💡 {self.current_word['example']}")
            self.example_label.show()

        self.update_mastery(self.current_word['id'], is_correct)
        self.update_stats_ui()

        self.input_field.setEnabled(False); self.hint_button.setEnabled(False)
        for btn in self.mc_buttons: btn.setEnabled(False)
        for i in range(self.bank_layout.count()): self.bank_layout.itemAt(i).widget().setEnabled(False)

        self.check_button.setEnabled(True); self.check_button.setText("Next Word ➔"); self.check_button.setObjectName("primaryBtn")
        self.check_button.style().unpolish(self.check_button); self.check_button.style().polish(self.check_button)
        try: self.check_button.clicked.disconnect()
        except: pass
        self.check_button.clicked.connect(self.next_word); self.check_button.setFocus()

    def update_stats_ui(self):
        score = self.get_stat("score"); streak = self.get_stat("streak"); day_streak = self.get_stat("day_streak")
        streak_text = f"Streak: {streak} 🔥"
        if streak >= 20: streak_text = f"Streak: {streak} 🔥🔥🔥"
        elif streak >= 10: streak_text = f"Streak: {streak} 🔥🔥"
        elif streak >= 5: streak_text = f"Streak: {streak} 🔥"
        
        self.stats_label.setText(f"🏆 Score: {score}  |  {streak_text}  |  📅 Day Streak: {day_streak}")
        acc = int((score / self.get_stat("total_questions")) * 100) if self.get_stat("total_questions") > 0 else 0
        self.progress_bar.setValue(acc)
        
        today = date.today().isoformat()
        c = self.conn.cursor(); c.execute("SELECT count FROM daily_stats WHERE date=?", (today,))
        r = c.fetchone()
        count = r['count'] if r else 0
        self.daily_bar.setValue(count)

    def show_hint(self):
        if self.current_word and self.mode in ["typing", "dictation", "cloze"]:
            word = self.current_word['word']
            hint = word[0] + " " + " _ " * (len(word.split()[0]) - 1) + "..."
            self.hint_label.setText(f"Starts with: {hint}")
            self.hint_button.setEnabled(False)

    def speak_word(self, rate, override_text=None):
        text_to_speak = override_text if override_text else (self.current_word['word'] if self.current_word else "")
        if text_to_speak and self.current_tts_language:
            self.tts.setRate(rate); self.tts.say(text_to_speak)
            QTimer.singleShot(2000, lambda: self.tts.setRate(0.0))

if __name__ == "__main__":
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    window = LanguageLearningApp()
    window.show()
    sys.exit(app.exec())