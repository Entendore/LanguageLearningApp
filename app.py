#!/usr/bin/env python3
"""
PolyGlot — Language Learning App
External SQLite database support with schema validation, error handling,
spaced-repetition progress tracking, and dynamic language pack loading.
"""

import sys
import json
import shutil
import random
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame, QProgressBar,
    QRadioButton, QButtonGroup, QComboBox, QGridLayout, QSpacerItem,
    QSizePolicy, QScrollArea, QMessageBox, QFileDialog, QInputDialog,
    QTextEdit, QHeaderView, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QDialog, QDialogButtonBox, QLineEdit, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QRect
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPen, QPalette, QIcon, QLinearGradient
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

APP_NAME = "PolyGlot"
SCHEMA_VERSION = "2.0"
APP_DATA_DIR = Path.home() / ".polyglot"
DB_PATH = APP_DATA_DIR / "polyglot.db"
PACKS_DIR = APP_DATA_DIR / "packs"
BACKUP_DIR = APP_DATA_DIR / "backups"
LOG_PATH = APP_DATA_DIR / "polyglot.log"

APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
PACKS_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("polyglot")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CUSTOM EXCEPTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PolyGlotError(Exception):
    """Base exception for PolyGlot."""
    def __init__(self, message, details=""):
        self.message = message
        self.details = details
        super().__init__(message)


class SchemaVersionError(PolyGlotError):
    """Database schema version is incompatible."""
    pass


class SchemaValidationError(PolyGlotError):
    """Database schema is missing required tables or columns."""
    pass


class LanguageNotFoundError(PolyGlotError):
    """Requested language does not exist in the database."""
    pass


class InvalidLanguagePackError(PolyGlotError):
    """Imported file is not a valid language pack."""
    pass


class DatabaseCorruptedError(PolyGlotError):
    """Database is corrupted and cannot be read."""
    pass


class DuplicateLanguageError(PolyGlotError):
    """Language already exists in the database."""
    pass


class DataIntegrityError(PolyGlotError):
    """Foreign key or data integrity violation."""
    pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DATABASE SCHEMA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SCHEMA_SQL = """
-- ── Schema version tracking ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_info (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- ── Supported languages ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS languages (
    code            TEXT PRIMARY KEY,           -- ISO 639-1 (es, fr, de, ja)
    name            TEXT NOT NULL,              -- English name
    native_name     TEXT NOT NULL,              -- Native name
    flag_emoji      TEXT DEFAULT '',
    is_rtl          INTEGER DEFAULT 0,          -- 1 = right-to-left
    description     TEXT DEFAULT '',
    author          TEXT DEFAULT 'PolyGlot',
    version         TEXT DEFAULT '1.0',
    word_count      INTEGER DEFAULT 0,          -- cached count
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ── Vocabulary categories ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lang_code       TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    sort_order      INTEGER DEFAULT 0,
    color           TEXT DEFAULT '#4A90D9',
    icon            TEXT DEFAULT '📋',
    word_count      INTEGER DEFAULT 0,          -- cached count
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lang_code) REFERENCES languages(code)
        ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE(lang_code, name)
);

-- ── Vocabulary words ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS words (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    lang_code           TEXT NOT NULL,
    category_id         INTEGER NOT NULL,
    word                TEXT NOT NULL,
    translation         TEXT NOT NULL,
    example             TEXT DEFAULT '',
    example_translation TEXT DEFAULT '',
    difficulty          INTEGER DEFAULT 1 CHECK(difficulty BETWEEN 1 AND 5),
    phonetic            TEXT DEFAULT '',
    part_of_speech      TEXT DEFAULT '',
    audio_path          TEXT DEFAULT '',
    notes               TEXT DEFAULT '',
    created_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lang_code) REFERENCES languages(code)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE(lang_code, word, category_id)
);

-- ── User flashcard progress (SM-2 / Leitner) ───────────────────────────
CREATE TABLE IF NOT EXISTS user_progress (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lang_code       TEXT NOT NULL,
    word_id         INTEGER NOT NULL,
    box             INTEGER DEFAULT 0,          -- Leitner box (0=new..5=mastered)
    ease_factor     REAL DEFAULT 2.5,           -- SM-2 ease
    interval_days   INTEGER DEFAULT 0,
    repetitions     INTEGER DEFAULT 0,
    next_review     TEXT NOT NULL,               -- ISO date
    last_reviewed   TEXT,
    total_reviews   INTEGER DEFAULT 0,
    correct_count   INTEGER DEFAULT 0,
    FOREIGN KEY (lang_code) REFERENCES languages(code)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (word_id) REFERENCES words(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE(lang_code, word_id)
);

-- ── Quiz history ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS quiz_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lang_code       TEXT NOT NULL,
    category_id     INTEGER,                    -- NULL = mixed quiz
    score           INTEGER NOT NULL,
    total_questions INTEGER NOT NULL,
    time_taken_secs INTEGER DEFAULT 0,
    quiz_date       TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lang_code) REFERENCES languages(code)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(id)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- ── User settings ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ── Indexes ──────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_words_lang      ON words(lang_code);
CREATE INDEX IF NOT EXISTS idx_words_category   ON words(category_id);
CREATE INDEX IF NOT EXISTS idx_progress_lang    ON user_progress(lang_code);
CREATE INDEX IF NOT EXISTS idx_progress_review  ON user_progress(next_review);
CREATE INDEX IF NOT EXISTS idx_quiz_lang        ON quiz_history(lang_code);
CREATE INDEX IF NOT EXISTS idx_quiz_date        ON quiz_history(quiz_date);
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BUILTIN LANGUAGE DATA — shipped with the app
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BUILTIN_LANGUAGES = [
    {
        "code": "es", "name": "Spanish", "native_name": "Español",
        "flag_emoji": "🇪🇸", "description": "Learn Spanish from scratch",
    },
    {
        "code": "fr", "name": "French", "native_name": "Français",
        "flag_emoji": "🇫🇷", "description": "Learn French step by step",
    },
    {
        "code": "de", "name": "German", "native_name": "Deutsch",
        "flag_emoji": "🇩🇪", "description": "Learn German effectively",
    },
    {
        "code": "ja", "name": "Japanese", "native_name": "日本語",
        "flag_emoji": "🇯🇵", "description": "Learn Japanese basics",
    },
]

BUILTIN_CATEGORIES = {
    "es": [
        {"name": "Basics",   "icon": "🔰", "color": "#4A90D9", "sort_order": 1},
        {"name": "Food",     "icon": "🍕", "color": "#27AE60", "sort_order": 2},
        {"name": "Travel",   "icon": "✈️", "color": "#F39C12", "sort_order": 3},
        {"name": "Verbs",    "icon": "🏃", "color": "#E74C3C", "sort_order": 4},
    ],
    "fr": [
        {"name": "Basics",   "icon": "🔰", "color": "#4A90D9", "sort_order": 1},
        {"name": "Food",     "icon": "🍕", "color": "#27AE60", "sort_order": 2},
        {"name": "Travel",   "icon": "✈️", "color": "#F39C12", "sort_order": 3},
        {"name": "Verbs",    "icon": "🏃", "color": "#E74C3C", "sort_order": 4},
    ],
    "de": [
        {"name": "Basics",   "icon": "🔰", "color": "#4A90D9", "sort_order": 1},
        {"name": "Food",     "icon": "🍕", "color": "#27AE60", "sort_order": 2},
        {"name": "Travel",   "icon": "✈️", "color": "#F39C12", "sort_order": 3},
        {"name": "Verbs",    "icon": "🏃", "color": "#E74C3C", "sort_order": 4},
    ],
    "ja": [
        {"name": "Basics",   "icon": "🔰", "color": "#4A90D9", "sort_order": 1},
        {"name": "Food",     "icon": "🍕", "color": "#27AE60", "sort_order": 2},
        {"name": "Travel",   "icon": "✈️", "color": "#F39C12", "sort_order": 3},
        {"name": "Verbs",    "icon": "🏃", "color": "#E74C3C", "sort_order": 4},
    ],
}

BUILTIN_WORDS = {
    "es": {
        "Basics": [
            {"word": "Hola", "translation": "Hello", "example": "¡Hola! ¿Cómo estás?",
             "difficulty": 1, "phonetic": "OH-lah", "part_of_speech": "interjection"},
            {"word": "Adiós", "translation": "Goodbye", "example": "Adiós, hasta luego.",
             "difficulty": 1, "phonetic": "ah-DYOHS", "part_of_speech": "interjection"},
            {"word": "Por favor", "translation": "Please", "example": "Un café, por favor.",
             "difficulty": 1, "phonetic": "por fah-BOR", "part_of_speech": "phrase"},
            {"word": "Gracias", "translation": "Thank you", "example": "Muchas gracias por tu ayuda.",
             "difficulty": 1, "phonetic": "GRAH-thyahs", "part_of_speech": "interjection"},
            {"word": "Lo siento", "translation": "I'm sorry", "example": "Lo siento, no entiendo.",
             "difficulty": 1, "phonetic": "loh SYEHN-toh", "part_of_speech": "phrase"},
            {"word": "Sí", "translation": "Yes", "example": "Sí, estoy de acuerdo.",
             "difficulty": 1, "phonetic": "see", "part_of_speech": "adverb"},
            {"word": "No", "translation": "No", "example": "No, gracias.",
             "difficulty": 1, "phonetic": "noh", "part_of_speech": "adverb"},
            {"word": "Agua", "translation": "Water", "example": "¿Puedo tener agua?",
             "difficulty": 1, "phonetic": "AH-gwah", "part_of_speech": "noun"},
        ],
        "Food": [
            {"word": "Manzana", "translation": "Apple", "example": "Me gusta la manzana.",
             "difficulty": 1, "phonetic": "mahn-SAH-nah", "part_of_speech": "noun"},
            {"word": "Pan", "translation": "Bread", "example": "El pan está fresco.",
             "difficulty": 1, "phonetic": "pahn", "part_of_speech": "noun"},
            {"word": "Leche", "translation": "Milk", "example": "Quiero un vaso de leche.",
             "difficulty": 1, "phonetic": "LEH-cheh", "part_of_speech": "noun"},
            {"word": "Pollo", "translation": "Chicken", "example": "El pollo está delicioso.",
             "difficulty": 2, "phonetic": "POH-yoh", "part_of_speech": "noun"},
            {"word": "Cerveza", "translation": "Beer", "example": "Dos cervezas, por favor.",
             "difficulty": 2, "phonetic": "ther-BEH-thah", "part_of_speech": "noun"},
            {"word": "Queso", "translation": "Cheese", "example": "Me encanta el queso.",
             "difficulty": 2, "phonetic": "KEH-soh", "part_of_speech": "noun"},
            {"word": "Ensalada", "translation": "Salad", "example": "Una ensalada, por favor.",
             "difficulty": 2, "phonetic": "ehn-sah-LAH-dah", "part_of_speech": "noun"},
            {"word": "Desayuno", "translation": "Breakfast", "example": "El desayuno es a las ocho.",
             "difficulty": 2, "phonetic": "deh-sah-YOO-noh", "part_of_speech": "noun"},
        ],
        "Travel": [
            {"word": "Aeropuerto", "translation": "Airport", "example": "Vamos al aeropuerto.",
             "difficulty": 2, "phonetic": "ah-eh-roh-PWER-toh", "part_of_speech": "noun"},
            {"word": "Hotel", "translation": "Hotel", "example": "El hotel está cerca.",
             "difficulty": 2, "phonetic": "oh-TEHL", "part_of_speech": "noun"},
            {"word": "Playa", "translation": "Beach", "example": "La playa es hermosa.",
             "difficulty": 2, "phonetic": "PLAH-yah", "part_of_speech": "noun"},
            {"word": "Boleto", "translation": "Ticket", "example": "Necesito un boleto.",
             "difficulty": 2, "phonetic": "boh-LEH-toh", "part_of_speech": "noun"},
            {"word": "Maleta", "translation": "Suitcase", "example": "Mi maleta es pesada.",
             "difficulty": 3, "phonetic": "mah-LEH-tah", "part_of_speech": "noun"},
            {"word": "Pasaporte", "translation": "Passport", "example": "¿Dónde está mi pasaporte?",
             "difficulty": 3, "phonetic": "pah-sah-POR-teh", "part_of_speech": "noun"},
        ],
        "Verbs": [
            {"word": "Comer", "translation": "To eat", "example": "Quiero comer algo.",
             "difficulty": 2, "phonetic": "koh-MEHR", "part_of_speech": "verb"},
            {"word": "Beber", "translation": "To drink", "example": "¿Qué quieres beber?",
             "difficulty": 2, "phonetic": "beh-BEHR", "part_of_speech": "verb"},
            {"word": "Hablar", "translation": "To speak", "example": "¿Puedes hablar más despacio?",
             "difficulty": 2, "phonetic": "ah-BLAHR", "part_of_speech": "verb"},
            {"word": "Entender", "translation": "To understand", "example": "No entiendo la pregunta.",
             "difficulty": 3, "phonetic": "ehn-tehn-DEHR", "part_of_speech": "verb"},
            {"word": "Viajar", "translation": "To travel", "example": "Me gusta viajar.",
             "difficulty": 2, "phonetic": "byah-HAHR", "part_of_speech": "verb"},
            {"word": "Necesitar", "translation": "To need", "example": "Necesito ayuda.",
             "difficulty": 2, "phonetic": "neh-seh-see-TAHR", "part_of_speech": "verb"},
        ],
    },
    "fr": {
        "Basics": [
            {"word": "Bonjour", "translation": "Hello", "example": "Bonjour, comment allez-vous?",
             "difficulty": 1, "phonetic": "bohn-ZHOOR", "part_of_speech": "interjection"},
            {"word": "Au revoir", "translation": "Goodbye", "example": "Au revoir, à bientôt!",
             "difficulty": 1, "phonetic": "oh ruh-VWAHR", "part_of_speech": "phrase"},
            {"word": "S'il vous plaît", "translation": "Please", "example": "Un café, s'il vous plaît.",
             "difficulty": 1, "phonetic": "seel voo PLEH", "part_of_speech": "phrase"},
            {"word": "Merci", "translation": "Thank you", "example": "Merci beaucoup!",
             "difficulty": 1, "phonetic": "mair-SEE", "part_of_speech": "interjection"},
            {"word": "Excusez-moi", "translation": "Excuse me", "example": "Excusez-moi, où est la gare?",
             "difficulty": 1, "phonetic": "ex-koo-zay MWAH", "part_of_speech": "phrase"},
            {"word": "Oui", "translation": "Yes", "example": "Oui, je comprends.",
             "difficulty": 1, "phonetic": "WEE", "part_of_speech": "adverb"},
            {"word": "Non", "translation": "No", "example": "Non, merci.",
             "difficulty": 1, "phonetic": "NOHN", "part_of_speech": "adverb"},
            {"word": "Eau", "translation": "Water", "example": "Un verre d'eau, s'il vous plaît.",
             "difficulty": 1, "phonetic": "OH", "part_of_speech": "noun"},
        ],
        "Food": [
            {"word": "Pomme", "translation": "Apple", "example": "J'aime les pommes.",
             "difficulty": 1, "phonetic": "POHM", "part_of_speech": "noun"},
            {"word": "Pain", "translation": "Bread", "example": "Le pain est frais.",
             "difficulty": 1, "phonetic": "PAN", "part_of_speech": "noun"},
            {"word": "Lait", "translation": "Milk", "example": "Un verre de lait.",
             "difficulty": 1, "phonetic": "LEH", "part_of_speech": "noun"},
            {"word": "Fromage", "translation": "Cheese", "example": "Le fromage français est délicieux.",
             "difficulty": 2, "phonetic": "froh-MAHZH", "part_of_speech": "noun"},
            {"word": "Vin", "translation": "Wine", "example": "Un verre de vin rouge.",
             "difficulty": 2, "phonetic": "VAN", "part_of_speech": "noun"},
            {"word": "Croissant", "translation": "Croissant", "example": "Un croissant au beurre.",
             "difficulty": 1, "phonetic": "kwah-SAHN", "part_of_speech": "noun"},
            {"word": "Petit-déjeuner", "translation": "Breakfast", "example": "Le petit-déjeuner à huit heures.",
             "difficulty": 2, "phonetic": "puh-tee day-zhuh-NAY", "part_of_speech": "noun"},
            {"word": "Dîner", "translation": "Dinner", "example": "Le dîner est servi.",
             "difficulty": 2, "phonetic": "dee-NAY", "part_of_speech": "noun"},
        ],
        "Travel": [
            {"word": "Aéroport", "translation": "Airport", "example": "Allons à l'aéroport.",
             "difficulty": 2, "phonetic": "ah-ay-roh-POR", "part_of_speech": "noun"},
            {"word": "Hôtel", "translation": "Hotel", "example": "L'hôtel est proche.",
             "difficulty": 2, "phonetic": "oh-TEHL", "part_of_speech": "noun"},
            {"word": "Plage", "translation": "Beach", "example": "La plage est belle.",
             "difficulty": 2, "phonetic": "PLAHZH", "part_of_speech": "noun"},
            {"word": "Billet", "translation": "Ticket", "example": "J'ai besoin d'un billet.",
             "difficulty": 2, "phonetic": "bee-YAY", "part_of_speech": "noun"},
            {"word": "Valise", "translation": "Suitcase", "example": "Ma valise est lourde.",
             "difficulty": 3, "phonetic": "vah-LEEZ", "part_of_speech": "noun"},
            {"word": "Passeport", "translation": "Passport", "example": "Où est mon passeport?",
             "difficulty": 3, "phonetic": "pahs-POR", "part_of_speech": "noun"},
        ],
        "Verbs": [
            {"word": "Manger", "translation": "To eat", "example": "Je veux manger quelque chose.",
             "difficulty": 2, "phonetic": "mahn-ZHAY", "part_of_speech": "verb"},
            {"word": "Boire", "translation": "To drink", "example": "Que voulez-vous boire?",
             "difficulty": 2, "phonetic": "BWAHR", "part_of_speech": "verb"},
            {"word": "Parler", "translation": "To speak", "example": "Pouvez-vous parler plus lentement?",
             "difficulty": 2, "phonetic": "pahr-LAY", "part_of_speech": "verb"},
            {"word": "Comprendre", "translation": "To understand", "example": "Je ne comprends pas.",
             "difficulty": 3, "phonetic": "kohn-PRAHNDR", "part_of_speech": "verb"},
            {"word": "Voyager", "translation": "To travel", "example": "J'aime voyager.",
             "difficulty": 2, "phonetic": "vwah-yah-ZHAY", "part_of_speech": "verb"},
            {"word": "Aider", "translation": "To help", "example": "Pouvez-vous m'aider?",
             "difficulty": 2, "phonetic": "eh-DAY", "part_of_speech": "verb"},
        ],
    },
    "de": {
        "Basics": [
            {"word": "Hallo", "translation": "Hello", "example": "Hallo, wie geht es Ihnen?",
             "difficulty": 1, "phonetic": "HAH-loh", "part_of_speech": "interjection"},
            {"word": "Auf Wiedersehen", "translation": "Goodbye", "example": "Auf Wiedersehen, bis bald!",
             "difficulty": 1, "phonetic": "owf VEE-der-zay-en", "part_of_speech": "phrase"},
            {"word": "Bitte", "translation": "Please", "example": "Einen Kaffee, bitte.",
             "difficulty": 1, "phonetic": "BIT-teh", "part_of_speech": "adverb"},
            {"word": "Danke", "translation": "Thank you", "example": "Vielen Danke!",
             "difficulty": 1, "phonetic": "DAHN-keh", "part_of_speech": "interjection"},
            {"word": "Entschuldigung", "translation": "Excuse me", "example": "Entschuldigung, wo ist der Bahnhof?",
             "difficulty": 2, "phonetic": "ent-SHOOL-dee-goong", "part_of_speech": "noun"},
            {"word": "Ja", "translation": "Yes", "example": "Ja, ich verstehe.",
             "difficulty": 1, "phonetic": "yah", "part_of_speech": "adverb"},
            {"word": "Nein", "translation": "No", "example": "Nein, danke.",
             "difficulty": 1, "phonetic": "nine", "part_of_speech": "adverb"},
            {"word": "Wasser", "translation": "Water", "example": "Ein Glas Wasser, bitte.",
             "difficulty": 1, "phonetic": "VAH-ser", "part_of_speech": "noun"},
        ],
        "Food": [
            {"word": "Apfel", "translation": "Apple", "example": "Ich mag Äpfel.",
             "difficulty": 1, "phonetic": "AHP-fel", "part_of_speech": "noun"},
            {"word": "Brot", "translation": "Bread", "example": "Das Brot ist frisch.",
             "difficulty": 1, "phonetic": "BROHT", "part_of_speech": "noun"},
            {"word": "Milch", "translation": "Milk", "example": "Ein Glas Milch.",
             "difficulty": 1, "phonetic": "milKH", "part_of_speech": "noun"},
            {"word": "Käse", "translation": "Cheese", "example": "Der Käse ist lecker.",
             "difficulty": 2, "phonetic": "KAY-zeh", "part_of_speech": "noun"},
            {"word": "Bier", "translation": "Beer", "example": "Ein Bier, bitte.",
             "difficulty": 1, "phonetic": "beer", "part_of_speech": "noun"},
            {"word": "Frühstück", "translation": "Breakfast", "example": "Das Frühstück ist um acht.",
             "difficulty": 2, "phonetic": "FROO-shtook", "part_of_speech": "noun"},
            {"word": "Wurst", "translation": "Sausage", "example": "Die Bratwurst ist gut.",
             "difficulty": 2, "phonetic": "VOORST", "part_of_speech": "noun"},
            {"word": "Kartoffel", "translation": "Potato", "example": "Ich mag Kartoffeln.",
             "difficulty": 2, "phonetic": "kar-TOFF-el", "part_of_speech": "noun"},
        ],
        "Travel": [
            {"word": "Flughafen", "translation": "Airport", "example": "Wir gehen zum Flughafen.",
             "difficulty": 2, "phonetic": "FLOOK-hah-fen", "part_of_speech": "noun"},
            {"word": "Hotel", "translation": "Hotel", "example": "Das Hotel ist in der Nähe.",
             "difficulty": 2, "phonetic": "hoh-TEHL", "part_of_speech": "noun"},
            {"word": "Strand", "translation": "Beach", "example": "Der Strand ist schön.",
             "difficulty": 2, "phonetic": "shtrahn", "part_of_speech": "noun"},
            {"word": "Fahrkarte", "translation": "Ticket", "example": "Ich brauche eine Fahrkarte.",
             "difficulty": 3, "phonetic": "FAHR-kar-teh", "part_of_speech": "noun"},
            {"word": "Koffer", "translation": "Suitcase", "example": "Mein Koffer ist schwer.",
             "difficulty": 3, "phonetic": "KOFF-er", "part_of_speech": "noun"},
            {"word": "Reisepass", "translation": "Passport", "example": "Wo ist mein Reisepass?",
             "difficulty": 3, "phonetic": "RY-zeh-pahs", "part_of_speech": "noun"},
        ],
        "Verbs": [
            {"word": "Essen", "translation": "To eat", "example": "Ich möchte etwas essen.",
             "difficulty": 2, "phonetic": "ES-sen", "part_of_speech": "verb"},
            {"word": "Trinken", "translation": "To drink", "example": "Was möchten Sie trinken?",
             "difficulty": 2, "phonetic": "TRING-ken", "part_of_speech": "verb"},
            {"word": "Sprechen", "translation": "To speak", "example": "Können Sie langsamer sprechen?",
             "difficulty": 2, "phonetic": "SPREH-chen", "part_of_speech": "verb"},
            {"word": "Verstehen", "translation": "To understand", "example": "Ich verstehe nicht.",
             "difficulty": 3, "phonetic": "fer-SHTAY-en", "part_of_speech": "verb"},
            {"word": "Reisen", "translation": "To travel", "example": "Ich reise gerne.",
             "difficulty": 2, "phonetic": "RY-zen", "part_of_speech": "verb"},
            {"word": "Helfen", "translation": "To help", "example": "Können Sie mir helfen?",
             "difficulty": 2, "phonetic": "HEL-fen", "part_of_speech": "verb"},
        ],
    },
    "ja": {
        "Basics": [
            {"word": "こんにちは", "translation": "Hello", "example": "こんにちは、元気ですか？",
             "difficulty": 1, "phonetic": "Konnichiwa", "part_of_speech": "interjection"},
            {"word": "さようなら", "translation": "Goodbye", "example": "さようなら、また会いましょう。",
             "difficulty": 1, "phonetic": "Sayōnara", "part_of_speech": "interjection"},
            {"word": "お願いします", "translation": "Please", "example": "コーヒーをお願いします。",
             "difficulty": 1, "phonetic": "Onegaishimasu", "part_of_speech": "phrase"},
            {"word": "ありがとう", "translation": "Thank you", "example": "ありがとうございます。",
             "difficulty": 1, "phonetic": "Arigatō", "part_of_speech": "interjection"},
            {"word": "すみません", "translation": "Excuse me", "example": "すみません、駅はどこですか？",
             "difficulty": 1, "phonetic": "Sumimasen", "part_of_speech": "phrase"},
            {"word": "はい", "translation": "Yes", "example": "はい、分かります。",
             "difficulty": 1, "phonetic": "Hai", "part_of_speech": "adverb"},
            {"word": "いいえ", "translation": "No", "example": "いいえ、結構です。",
             "difficulty": 1, "phonetic": "Īe", "part_of_speech": "adverb"},
            {"word": "水", "translation": "Water", "example": "水をください。",
             "difficulty": 1, "phonetic": "Mizu", "part_of_speech": "noun"},
        ],
        "Food": [
            {"word": "りんご", "translation": "Apple", "example": "りんごが好きです。",
             "difficulty": 1, "phonetic": "Ringo", "part_of_speech": "noun"},
            {"word": "パン", "translation": "Bread", "example": "パンを食べます。",
             "difficulty": 1, "phonetic": "Pan", "part_of_speech": "noun"},
            {"word": "牛乳", "translation": "Milk", "example": "牛乳を飲みます。",
             "difficulty": 2, "phonetic": "Gyūnyū", "part_of_speech": "noun"},
            {"word": "魚", "translation": "Fish", "example": "魚が好きです。",
             "difficulty": 1, "phonetic": "Sakana", "part_of_speech": "noun"},
            {"word": "お茶", "translation": "Tea", "example": "お茶をどうぞ。",
             "difficulty": 1, "phonetic": "Ocha", "part_of_speech": "noun"},
            {"word": "ご飯", "translation": "Rice", "example": "ご飯を食べましょう。",
             "difficulty": 1, "phonetic": "Gohan", "part_of_speech": "noun"},
            {"word": "朝ごはん", "translation": "Breakfast", "example": "朝ごはんは八時です。",
             "difficulty": 2, "phonetic": "Asagohan", "part_of_speech": "noun"},
            {"word": "晩ごはん", "translation": "Dinner", "example": "晩ごはんは何ですか？",
             "difficulty": 2, "phonetic": "Bangohan", "part_of_speech": "noun"},
        ],
        "Travel": [
            {"word": "空港", "translation": "Airport", "example": "空港へ行きます。",
             "difficulty": 2, "phonetic": "Kūkō", "part_of_speech": "noun"},
            {"word": "ホテル", "translation": "Hotel", "example": "ホテルは近いです。",
             "difficulty": 2, "phonetic": "Hoteru", "part_of_speech": "noun"},
            {"word": "駅", "translation": "Station", "example": "駅はどこですか？",
             "difficulty": 2, "phonetic": "Eki", "part_of_speech": "noun"},
            {"word": "切符", "translation": "Ticket", "example": "切符を買います。",
             "difficulty": 3, "phonetic": "Kippu", "part_of_speech": "noun"},
            {"word": "荷物", "translation": "Luggage", "example": "荷物が重いです。",
             "difficulty": 3, "phonetic": "Nimotsu", "part_of_speech": "noun"},
            {"word": "パスポート", "translation": "Passport", "example": "パスポートを見せてください。",
             "difficulty": 3, "phonetic": "Pasupōto", "part_of_speech": "noun"},
        ],
        "Verbs": [
            {"word": "食べる", "translation": "To eat", "example": "何か食べたいです。",
             "difficulty": 2, "phonetic": "Taberu", "part_of_speech": "verb"},
            {"word": "飲む", "translation": "To drink", "example": "何を飲みますか？",
             "difficulty": 2, "phonetic": "Nomu", "part_of_speech": "verb"},
            {"word": "話す", "translation": "To speak", "example": "ゆっくり話してください。",
             "difficulty": 2, "phonetic": "Hanasu", "part_of_speech": "verb"},
            {"word": "分かる", "translation": "To understand", "example": "分かりません。",
             "difficulty": 2, "phonetic": "Wakaru", "part_of_speech": "verb"},
            {"word": "行く", "translation": "To go", "example": "どこへ行きますか？",
             "difficulty": 2, "phonetic": "Iku", "part_of_speech": "verb"},
            {"word": "見る", "translation": "To see", "example": "見てください。",
             "difficulty": 2, "phonetic": "Miru", "part_of_speech": "verb"},
        ],
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SCHEMA VALIDATOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SchemaValidator:
    """Validates that a SQLite database conforms to the PolyGlot schema."""

    REQUIRED_TABLES = {
        "schema_info": {"key", "value"},
        "languages": {"code", "name", "native_name"},
        "categories": {"id", "lang_code", "name"},
        "words": {"id", "lang_code", "category_id", "word", "translation", "difficulty"},
        "user_progress": {"id", "lang_code", "word_id", "box", "next_review"},
        "quiz_history": {"id", "lang_code", "score", "total_questions", "quiz_date"},
        "user_settings": {"key", "value"},
    }

    # Valid ISO 639-1 language codes (subset)
    VALID_LANG_CODES = {
        "aa","ab","af","ak","am","an","ar","as","av","ay","az",
        "ba","be","bg","bh","bi","bm","bn","bo","br","bs",
        "ca","ce","ch","co","cr","cs","cu","cv","cy",
        "da","de","dv","dz",
        "ee","el","en","eo","es","et","eu",
        "fa","ff","fi","fj","fo","fr","fy",
        "ga","gd","gl","gn","gu","gv",
        "ha","he","hi","ho","hr","ht","hu","hy","hz",
        "ia","id","ie","ig","ii","ik","io","is","it","iu",
        "ja","jv",
        "ka","kg","ki","kj","kk","kl","km","kn","ko","kr","ks","ku","kv","kw","ky",
        "la","lb","lg","li","ln","lo","lt","lu","lv",
        "mg","mh","mi","mk","ml","mn","mr","ms","mt","my",
        "na","nb","nd","ne","ng","nl","nn","no","nr","nv","ny",
        "oc","oj","om","or",
        "pa","pi","pl","ps","pt",
        "qu",
        "rm","rn","ro","ru","rw",
        "sa","sc","sd","se","sg","si","sk","sl","sm","sn","so","sq","sr","ss","st","su","sv","sw",
        "ta","te","tg","th","ti","tk","tl","tn","to","tr","ts","tt","tw","ty",
        "ug","uk","ur","uz",
        "ve","vi","vo",
        "wa","wo",
        "xh",
        "yi","yo",
        "za","zh","zu",
    }

    @classmethod
    def validate(cls, db_path: Path) -> tuple[bool, list[str]]:
        """Validate a database file. Returns (is_valid, list_of_errors)."""
        errors: list[str] = []

        # 1. File exists and is readable
        if not db_path.exists():
            errors.append(f"Database file not found: {db_path}")
            return False, errors

        if db_path.stat().st_size < 100:
            errors.append("Database file is too small — likely corrupted or empty.")
            return False, errors

        # 2. Can open as SQLite
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA integrity_check")
            cursor = conn.cursor()
        except sqlite3.DatabaseError as e:
            errors.append(f"Cannot open database: {e}")
            return False, errors

        try:
            # 3. Check required tables
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            existing_tables = {row[0] for row in cursor.fetchall()}

            for table, required_cols in cls.REQUIRED_TABLES.items():
                if table not in existing_tables:
                    errors.append(f"Missing required table: '{table}'")
                    continue

                # 4. Check required columns
                cursor.execute(f"PRAGMA table_info({table})")
                existing_cols = {row[1] for row in cursor.fetchall()}
                missing_cols = required_cols - existing_cols
                if missing_cols:
                    errors.append(
                        f"Table '{table}' missing columns: {', '.join(missing_cols)}"
                    )

            # 5. Check schema version
            if "schema_info" in existing_tables:
                try:
                    cursor.execute(
                        "SELECT value FROM schema_info WHERE key='schema_version'"
                    )
                    row = cursor.fetchone()
                    if row and row[0] != SCHEMA_VERSION:
                        errors.append(
                            f"Schema version mismatch: expected {SCHEMA_VERSION}, "
                            f"got {row[0]}. The app may need updating."
                        )
                except sqlite3.OperationalError:
                    errors.append("Cannot read schema version from schema_info table.")

            # 6. Validate language data
            if "languages" in existing_tables:
                cursor.execute("SELECT code, name, native_name FROM languages")
                for code, name, native_name in cursor.fetchall():
                    if not code or len(code) < 2:
                        errors.append(f"Invalid language code: '{code}'")
                    elif code.lower() not in cls.VALID_LANG_CODES and len(code) == 2:
                        errors.append(
                            f"Language code '{code}' is not a recognized ISO 639-1 code."
                        )
                    if not name:
                        errors.append(f"Language with code '{code}' has no name.")
                    if not native_name:
                        errors.append(
                            f"Language '{code}' missing native_name."
                        )

            # 7. Check foreign key integrity
            if "words" in existing_tables and "categories" in existing_tables:
                cursor.execute("""
                    SELECT COUNT(*) FROM words w
                    LEFT JOIN categories c ON w.category_id = c.id
                    WHERE c.id IS NULL
                """)
                orphan_words = cursor.fetchone()[0]
                if orphan_words > 0:
                    errors.append(
                        f"{orphan_words} word(s) reference non-existent categories."
                    )

            if "words" in existing_tables and "languages" in existing_tables:
                cursor.execute("""
                    SELECT DISTINCT w.lang_code FROM words w
                    LEFT JOIN languages l ON w.lang_code = l.code
                    WHERE l.code IS NULL
                """)
                invalid_langs = [row[0] for row in cursor.fetchall()]
                if invalid_langs:
                    errors.append(
                        f"Words reference unknown language code(s): {', '.join(invalid_langs)}"
                    )

            # 8. Check minimum data
            if "words" in existing_tables:
                cursor.execute("SELECT COUNT(*) FROM words")
                count = cursor.fetchone()[0]
                if count == 0:
                    errors.append("Database contains no words — nothing to learn!")

        except sqlite3.OperationalError as e:
            errors.append(f"Database query error: {e}")
        finally:
            conn.close()

        return len(errors) == 0, errors


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DATABASE MANAGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DatabaseManager:
    """Manages all database operations for PolyGlot."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # ── Connection ────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Open database connection with foreign keys enabled."""
        try:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.row_factory = sqlite3.Row
            logger.info(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.critical(f"Failed to connect to database: {e}")
            raise DatabaseCorruptedError(
                "Cannot connect to the database.",
                details=str(e)
            )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn

    # ── Initialization ────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Create tables and seed built-in data if needed."""
        try:
            self.conn.executescript(SCHEMA_SQL)

            # Set schema version
            self.conn.execute(
                "INSERT OR REPLACE INTO schema_info (key, value) VALUES (?, ?)",
                ("schema_version", SCHEMA_VERSION),
            )
            self.conn.commit()

            # Seed built-in languages if not present
            existing = self.get_language_codes()
            for lang in BUILTIN_LANGUAGES:
                if lang["code"] not in existing:
                    self._seed_language(lang)
                    logger.info(f"Seeded built-in language: {lang['name']}")

            self._update_cached_counts()
            self.conn.commit()
            logger.info("Database initialized successfully.")

        except sqlite3.Error as e:
            logger.error(f"Database initialization failed: {e}")
            raise DatabaseCorruptedError(
                "Failed to initialize the database.",
                details=str(e),
            )

    def _seed_language(self, lang_data: dict) -> None:
        """Insert a built-in language with its categories and words."""
        code = lang_data["code"]

        self.conn.execute(
            """INSERT OR IGNORE INTO languages
               (code, name, native_name, flag_emoji, description)
               VALUES (?, ?, ?, ?, ?)""",
            (code, lang_data["name"], lang_data["native_name"],
             lang_data.get("flag_emoji", ""), lang_data.get("description", "")),
        )

        # Insert categories
        if code in BUILTIN_CATEGORIES:
            for cat in BUILTIN_CATEGORIES[code]:
                self.conn.execute(
                    """INSERT OR IGNORE INTO categories
                       (lang_code, name, icon, color, sort_order)
                       VALUES (?, ?, ?, ?, ?)""",
                    (code, cat["name"], cat["icon"], cat["color"], cat["sort_order"]),
                )

        # Insert words
        if code in BUILTIN_WORDS:
            for cat_name, words in BUILTIN_WORDS[code].items():
                cat_row = self.conn.execute(
                    "SELECT id FROM categories WHERE lang_code=? AND name=?",
                    (code, cat_name),
                ).fetchone()

                if not cat_row:
                    logger.warning(
                        f"Category '{cat_name}' not found for language '{code}', skipping words."
                    )
                    continue

                cat_id = cat_row["id"]
                for w in words:
                    try:
                        self.conn.execute(
                            """INSERT OR IGNORE INTO words
                               (lang_code, category_id, word, translation,
                                example, difficulty, phonetic, part_of_speech)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (code, cat_id, w["word"], w["translation"],
                             w.get("example", ""), w.get("difficulty", 1),
                             w.get("phonetic", ""), w.get("part_of_speech", "")),
                        )
                    except sqlite3.IntegrityError:
                        logger.debug(f"Duplicate word skipped: {w['word']} ({code})")

    def _update_cached_counts(self) -> None:
        """Update word_count caches in languages and categories tables."""
        self.conn.execute("""
            UPDATE categories SET word_count = (
                SELECT COUNT(*) FROM words WHERE category_id = categories.id
            )
        """)
        self.conn.execute("""
            UPDATE languages SET word_count = (
                SELECT COUNT(*) FROM words WHERE lang_code = languages.code
            )
        """)

    # ── Language Operations ───────────────────────────────────────────────

    def get_language_codes(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT code FROM languages ORDER BY name"
        ).fetchall()
        return [r["code"] for r in rows]

    def get_languages(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT code, name, native_name, flag_emoji, description,
                      word_count, author, version
               FROM languages ORDER BY name"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_language(self, code: str) -> dict | None:
        row = self.conn.execute(
            """SELECT code, name, native_name, flag_emoji, description,
                      word_count, author, version
               FROM languages WHERE code=?""",
            (code,),
        ).fetchone()
        return dict(row) if row else None

    def language_exists(self, code: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM languages WHERE code=?", (code,)
        ).fetchone()
        return row is not None

    def remove_language(self, code: str) -> None:
        """Remove a language and all associated data."""
        if not self.language_exists(code):
            raise LanguageNotFoundError(
                f"Language '{code}' not found.",
                details="The language code does not exist in the database."
            )
        # Check it's not a built-in that we want to protect? Let user decide.
        self.conn.execute("DELETE FROM languages WHERE code=?", (code,))
        self.conn.commit()
        logger.info(f"Removed language: {code}")

    # ── Category Operations ───────────────────────────────────────────────

    def get_categories(self, lang_code: str) -> list[dict]:
        if not self.language_exists(lang_code):
            raise LanguageNotFoundError(
                f"Language '{lang_code}' not found.",
                details="Cannot fetch categories for an unsupported language."
            )
        rows = self.conn.execute(
            """SELECT id, lang_code, name, description, icon, color,
                      sort_order, word_count
               FROM categories WHERE lang_code=?
               ORDER BY sort_order, name""",
            (lang_code,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Word Operations ───────────────────────────────────────────────────

    def get_words(self, lang_code: str, category_id: int | None = None) -> list[dict]:
        if not self.language_exists(lang_code):
            raise LanguageNotFoundError(
                f"Language '{lang_code}' not found.",
                details="Cannot fetch words for an unsupported language."
            )
        if category_id is not None:
            rows = self.conn.execute(
                """SELECT w.id, w.word, w.translation, w.example,
                          w.example_translation, w.difficulty,
                          w.phonetic, w.part_of_speech, w.notes,
                          c.name as category_name
                   FROM words w
                   JOIN categories c ON w.category_id = c.id
                   WHERE w.lang_code=? AND w.category_id=?
                   ORDER BY w.difficulty, w.word""",
                (lang_code, category_id),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT w.id, w.word, w.translation, w.example,
                          w.example_translation, w.difficulty,
                          w.phonetic, w.part_of_speech, w.notes,
                          c.name as category_name
                   FROM words w
                   JOIN categories c ON w.category_id = c.id
                   WHERE w.lang_code=?
                   ORDER BY c.sort_order, w.difficulty, w.word""",
                (lang_code,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_word_count(self, lang_code: str) -> int:
        row = self.conn.execute(
            "SELECT word_count FROM languages WHERE code=?", (lang_code,)
        ).fetchone()
        return row["word_count"] if row else 0

    # ── Progress Operations (SM-2 / Leitner) ─────────────────────────────

    def update_word_progress(self, lang_code: str, word_id: int, correct: bool) -> None:
        """Update progress for a word using SM-2 algorithm."""
        existing = self.conn.execute(
            "SELECT * FROM user_progress WHERE lang_code=? AND word_id=?",
            (lang_code, word_id),
        ).fetchone()

        today = datetime.now().strftime("%Y-%m-%d")

        if existing is None:
            # New word
            box = 1 if correct else 0
            ease = 2.5
            interval = 1 if correct else 0
            reps = 1 if correct else 0
            next_date = (datetime.now() + timedelta(days=interval)).strftime("%Y-%m-%d")
            self.conn.execute(
                """INSERT INTO user_progress
                   (lang_code, word_id, box, ease_factor, interval_days,
                    repetitions, next_review, last_reviewed, total_reviews, correct_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (lang_code, word_id, box, ease, interval, reps, next_date, today,
                 1 if correct else 0),
            )
        else:
            e = dict(existing)
            total = e["total_reviews"] + 1
            correct_count = e["correct_count"] + (1 if correct else 0)
            ease = e["ease_factor"]

            if correct:
                # SM-2: increase ease, interval
                ease = max(1.3, ease + 0.1)
                if e["repetitions"] == 0:
                    interval = 1
                elif e["repetitions"] == 1:
                    interval = 6
                else:
                    interval = int(e["interval_days"] * ease)
                reps = e["repetitions"] + 1
                box = min(5, e["box"] + 1)
            else:
                # Reset: back to box 0
                reps = 0
                interval = 0
                box = max(0, e["box"] - 1)
                ease = max(1.3, ease - 0.2)

            next_date = (datetime.now() + timedelta(days=interval)).strftime("%Y-%m-%d")

            self.conn.execute(
                """UPDATE user_progress
                   SET box=?, ease_factor=?, interval_days=?, repetitions=?,
                       next_review=?, last_reviewed=?, total_reviews=?,
                       correct_count=?
                   WHERE lang_code=? AND word_id=?""",
                (box, ease, interval, reps, next_date, today,
                 total, correct_count, lang_code, word_id),
            )

        self.conn.commit()

    def get_words_for_review(self, lang_code: str, limit: int = 20) -> list[dict]:
        """Get words that are due for review."""
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self.conn.execute(
            """SELECT w.*, up.box, up.ease_factor, up.interval_days,
                      up.repetitions, up.next_review
               FROM words w
               JOIN user_progress up ON w.id = up.word_id
               WHERE w.lang_code=? AND up.next_review <= ?
               ORDER BY up.box ASC, up.next_review ASC
               LIMIT ?""",
            (lang_code, today, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_learned_word_ids(self, lang_code: str) -> set[int]:
        """Get IDs of words that have been reviewed at least once correctly."""
        rows = self.conn.execute(
            "SELECT word_id FROM user_progress WHERE lang_code=? AND correct_count > 0",
            (lang_code,),
        ).fetchall()
        return {r["word_id"] for r in rows}

    def get_mastered_word_ids(self, lang_code: str) -> set[int]:
        """Get IDs of words in Leitner box 4+."""
        rows = self.conn.execute(
            "SELECT word_id FROM user_progress WHERE lang_code=? AND box >= 4",
            (lang_code,),
        ).fetchall()
        return {r["word_id"] for r in rows}

    def get_progress_stats(self, lang_code: str) -> dict:
        """Get aggregate progress statistics for a language."""
        total = self.get_word_count(lang_code)
        learned = len(self.get_learned_word_ids(lang_code))
        mastered = len(self.get_mastered_word_ids(lang_code))

        row = self.conn.execute(
            """SELECT COALESCE(SUM(total_reviews), 0) as total_reviews,
                      COALESCE(SUM(correct_count), 0) as total_correct
               FROM user_progress WHERE lang_code=?""",
            (lang_code,),
        ).fetchone()

        due_row = self.conn.execute(
            """SELECT COUNT(*) as count FROM user_progress
               WHERE lang_code=? AND next_review <= ?""",
            (lang_code, datetime.now().strftime("%Y-%m-%d")),
        ).fetchone()

        return {
            "total_words": total,
            "words_learned": learned,
            "words_mastered": mastered,
            "total_reviews": row["total_reviews"] if row else 0,
            "total_correct": row["total_correct"] if row else 0,
            "words_due": due_row["count"] if due_row else 0,
        }

    # ── Quiz Operations ──────────────────────────────────────────────────

    def save_quiz_result(self, lang_code: str, category_id: int | None,
                         score: int, total: int, time_secs: int = 0) -> int:
        cursor = self.conn.execute(
            """INSERT INTO quiz_history
               (lang_code, category_id, score, total_questions, time_taken_secs)
               VALUES (?, ?, ?, ?, ?)""",
            (lang_code, category_id, score, total, time_secs),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_quiz_history(self, lang_code: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            """SELECT qh.*, c.name as category_name
               FROM quiz_history qh
               LEFT JOIN categories c ON qh.category_id = c.id
               WHERE qh.lang_code=?
               ORDER BY qh.quiz_date DESC LIMIT ?""",
            (lang_code, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_avg_quiz_score(self, lang_code: str) -> float:
        row = self.conn.execute(
            """SELECT AVG(CAST(score AS FLOAT) / total_questions) as avg_pct
               FROM quiz_history WHERE lang_code=?""",
            (lang_code,),
        ).fetchone()
        return (row["avg_pct"] * 100) if row and row["avg_pct"] is not None else 0.0

    # ── Streak ────────────────────────────────────────────────────────────

    def update_streak(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        row = self.conn.execute(
            "SELECT value FROM user_settings WHERE key='last_session'"
        ).fetchone()
        last_session = row["value"] if row else None

        streak_row = self.conn.execute(
            "SELECT value FROM user_settings WHERE key='streak'"
        ).fetchone()
        current_streak = int(streak_row["value"]) if streak_row else 0

        if last_session == today:
            return current_streak

        if last_session == yesterday:
            current_streak += 1
        else:
            current_streak = 1

        self.conn.execute(
            "INSERT OR REPLACE INTO user_settings (key, value) VALUES ('streak', ?)",
            (str(current_streak),),
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO user_settings (key, value) VALUES ('last_session', ?)",
            (today,),
        )
        self.conn.commit()
        return current_streak

    def get_streak(self) -> int:
        row = self.conn.execute(
            "SELECT value FROM user_settings WHERE key='streak'"
        ).fetchone()
        return int(row["value"]) if row else 0

    # ── Settings ──────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM user_settings WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    # ── Import / Export ───────────────────────────────────────────────────

    def import_language_pack(self, pack_path: Path) -> tuple[bool, str]:
        """Import a language pack from an external .db file."""
        try:
            # Validate the pack
            is_valid, errors = SchemaValidator.validate(pack_path)
            if not is_valid:
                error_text = "\n".join(f"  • {e}" for e in errors)
                return False, f"Validation failed:\n{error_text}"

            # Open the pack
            pack_conn = sqlite3.connect(str(pack_path))
            pack_conn.row_factory = sqlite3.Row

            # Get languages from the pack
            lang_rows = pack_conn.execute(
                "SELECT * FROM languages"
            ).fetchall()

            if not lang_rows:
                pack_conn.close()
                return False, "The language pack contains no languages."

            imported = []
            skipped = []
            errors_list = []

            for lang_row in lang_rows:
                lang = dict(lang_row)
                code = lang["code"]

                # Validate language code
                if not code or len(code) < 2:
                    errors_list.append(
                        f"Invalid language code '{code}' — must be ISO 639-1."
                    )
                    continue

                # Check if language already exists
                if self.language_exists(code):
                    existing = self.get_language(code)
                    skipped.append(
                        f"{existing['flag_emoji']} {existing['name']} ({code}) "
                        f"— already installed"
                    )
                    continue

                # Insert language
                self.conn.execute(
                    """INSERT INTO languages
                       (code, name, native_name, flag_emoji, description,
                        author, version)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (code, lang["name"], lang["native_name"],
                     lang.get("flag_emoji", ""), lang.get("description", ""),
                     lang.get("author", "External"), lang.get("version", "1.0")),
                )

                # Insert categories
                cat_rows = pack_conn.execute(
                    "SELECT * FROM categories WHERE lang_code=?", (code,)
                ).fetchall()

                cat_id_map = {}  # old_id -> new_id
                for cat_row in cat_rows:
                    c = dict(cat_row)
                    cursor = self.conn.execute(
                        """INSERT INTO categories
                           (lang_code, name, description, sort_order, color, icon)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (code, c["name"], c.get("description", ""),
                         c.get("sort_order", 0), c.get("color", "#4A90D9"),
                         c.get("icon", "📋")),
                    )
                    cat_id_map[c["id"]] = cursor.lastrowid

                # Insert words
                word_rows = pack_conn.execute(
                    "SELECT * FROM words WHERE lang_code=?", (code,)
                ).fetchall()

                word_count = 0
                for word_row in word_rows:
                    w = dict(word_row)
                    new_cat_id = cat_id_map.get(w["category_id"])
                    if new_cat_id is None:
                        errors_list.append(
                            f"Word '{w['word']}' references unknown category — skipped."
                        )
                        continue
                    try:
                        self.conn.execute(
                            """INSERT INTO words
                               (lang_code, category_id, word, translation,
                                example, example_translation, difficulty,
                                phonetic, part_of_speech, audio_path, notes)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (code, new_cat_id, w["word"], w["translation"],
                             w.get("example", ""), w.get("example_translation", ""),
                             w.get("difficulty", 1), w.get("phonetic", ""),
                             w.get("part_of_speech", ""), w.get("audio_path", ""),
                             w.get("notes", "")),
                        )
                        word_count += 1
                    except sqlite3.IntegrityError:
                        errors_list.append(
                            f"Duplicate word skipped: '{w['word']}' ({code})"
                        )

                # Update cached count
                self.conn.execute(
                    "UPDATE languages SET word_count=? WHERE code=?",
                    (word_count, code),
                )
                for new_id in cat_id_map.values():
                    cnt = self.conn.execute(
                        "SELECT COUNT(*) FROM words WHERE category_id=?", (new_id,)
                    ).fetchone()[0]
                    self.conn.execute(
                        "UPDATE categories SET word_count=? WHERE id=?",
                        (cnt, new_id),
                    )

                imported.append(f"{lang['flag_emoji']} {lang['name']} ({word_count} words)")

            self.conn.commit()
            pack_conn.close()

            # Copy pack to packs directory
            try:
                shutil.copy2(str(pack_path), str(PACKS_DIR / pack_path.name))
            except OSError:
                pass  # Non-critical

            # Build result message
            parts = []
            if imported:
                parts.append("✅ Imported:\n" + "\n".join(f"  • {i}" for i in imported))
            if skipped:
                parts.append("⏭️ Skipped:\n" + "\n".join(f"  • {s}" for s in skipped))
            if errors_list:
                parts.append("⚠️ Warnings:\n" + "\n".join(f"  • {e}" for e in errors_list[:10]))

            return True, "\n\n".join(parts) if parts else "No languages found in pack."

        except sqlite3.Error as e:
            logger.error(f"Import failed: {e}")
            return False, f"Database error during import:\n{e}"
        except Exception as e:
            logger.error(f"Import failed: {e}")
            return False, f"Unexpected error during import:\n{e}"

    def export_language_pack(self, lang_code: str, output_path: Path) -> tuple[bool, str]:
        """Export a language as a standalone .db pack file."""
        try:
            lang = self.get_language(lang_code)
            if not lang:
                return False, f"Language '{lang_code}' not found."

            # Create new database
            if output_path.exists():
                output_path.unlink()

            pack_conn = sqlite3.connect(str(output_path))
            pack_conn.executescript(SCHEMA_SQL)
            pack_conn.execute(
                "INSERT OR REPLACE INTO schema_info (key, value) VALUES (?, ?)",
                ("schema_version", SCHEMA_VERSION),
            )

            # Copy language
            pack_conn.execute(
                """INSERT INTO languages
                   (code, name, native_name, flag_emoji, description, author, version)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (lang["code"], lang["name"], lang["native_name"],
                 lang["flag_emoji"], lang["description"],
                 lang.get("author", "PolyGlot"), lang.get("version", "1.0")),
            )

            # Copy categories
            categories = self.get_categories(lang_code)
            cat_id_map = {}
            for cat in categories:
                cursor = pack_conn.execute(
                    """INSERT INTO categories
                       (lang_code, name, description, sort_order, color, icon, word_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (lang_code, cat["name"], cat["description"],
                     cat["sort_order"], cat["color"], cat["icon"], cat["word_count"]),
                )
                cat_id_map[cat["id"]] = cursor.lastrowid

            # Copy words
            words = self.get_words(lang_code)
            for w in words:
                new_cat_id = cat_id_map.get(w["category_id"])
                if new_cat_id is None:
                    continue
                pack_conn.execute(
                    """INSERT INTO words
                       (lang_code, category_id, word, translation, example,
                        example_translation, difficulty, phonetic,
                        part_of_speech, audio_path, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (lang_code, new_cat_id, w["word"], w["translation"],
                     w.get("example", ""), w.get("example_translation", ""),
                     w.get("difficulty", 1), w.get("phonetic", ""),
                     w.get("part_of_speech", ""), w.get("audio_path", ""),
                     w.get("notes", "")),
                )

            pack_conn.commit()
            pack_conn.close()
            return True, f"Exported {lang['name']} ({len(words)} words) to:\n{output_path}"

        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False, f"Export failed: {e}"

    # ── Repair ────────────────────────────────────────────────────────────

    def repair_database(self) -> tuple[bool, str]:
        """Attempt to repair a corrupted database."""
        try:
            # Backup first
            backup_name = f"polyglot_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            backup_path = BACKUP_DIR / backup_name
            if self.db_path.exists():
                shutil.copy2(str(self.db_path), str(backup_path))

            # Try integrity check
            result = self.conn.execute("PRAGMA integrity_check").fetchone()

            if result[0] == "ok":
                # Re-create tables if missing
                self.conn.executescript(SCHEMA_SQL)
                self.conn.commit()
                return True, f"Database OK. Backup saved to:\n{backup_path}"
            else:
                # Corrupted — reinitialize
                self.close()
                self.db_path.unlink(missing_ok=True)
                self.connect()
                self.initialize()
                return True, (
                    f"Database was corrupted and has been rebuilt.\n"
                    f"Backup saved to:\n{backup_path}\n\n"
                    f"Note: Some progress data may have been lost."
                )

        except Exception as e:
            return False, f"Repair failed: {e}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CUSTOM WIDGETS (same visual design, enhanced)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FlipCard(QFrame):
    flipped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._showing_front = True
        self._word_data = {}
        self.setMinimumSize(400, 280)
        self.setMaximumSize(520, 350)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(30, 30, 30, 30)

        self.word_label = QLabel("")
        self.word_label.setAlignment(Qt.AlignCenter)
        self.word_label.setObjectName("cardWord")

        self.phonetic_label = QLabel("")
        self.phonetic_label.setAlignment(Qt.AlignCenter)
        self.phonetic_label.setObjectName("cardPhonetic")

        self.sub_label = QLabel("")
        self.sub_label.setAlignment(Qt.AlignCenter)
        self.sub_label.setObjectName("cardSub")
        self.sub_label.setWordWrap(True)

        self.pos_label = QLabel("")
        self.pos_label.setAlignment(Qt.AlignCenter)
        self.pos_label.setObjectName("cardPos")

        self.hint_label = QLabel("Tap to flip")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setObjectName("cardHint")

        self.layout.addStretch()
        self.layout.addWidget(self.word_label)
        self.layout.addWidget(self.phonetic_label)
        self.layout.addWidget(self.pos_label)
        self.layout.addWidget(self.sub_label)
        self.layout.addWidget(self.hint_label)
        self.layout.addStretch()

        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("flashcard")

    def set_card(self, word_data: dict, showing_front=True):
        self._word_data = word_data
        self._showing_front = showing_front
        if showing_front:
            self.word_label.setText(word_data.get("word", ""))
            self.phonetic_label.setText(word_data.get("phonetic", ""))
            self.pos_label.setText(word_data.get("part_of_speech", ""))
            self.sub_label.setText("")
            self.hint_label.setText("🔊  Tap to reveal translation")
            self.setStyleSheet("""
                #flashcard {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #4A90D9, stop:1 #357ABD);
                    border-radius: 20px; border: 2px solid #5BA3EC;
                }
                #cardWord { color: #FFFFFF; font-size: 36px; font-weight: bold; }
                #cardPhonetic { color: #A0C4F0; font-size: 15px; }
                #cardPos { color: #8BB8E8; font-size: 12px; font-style: italic; }
                #cardSub { color: #D0E4FF; font-size: 16px; font-style: italic; }
                #cardHint { color: #A0C4F0; font-size: 13px; margin-top: 10px; }
            """)
        else:
            self.word_label.setText(word_data.get("translation", ""))
            self.phonetic_label.setText("")
            self.pos_label.setText("")
            self.sub_label.setText(word_data.get("example", ""))
            self.hint_label.setText("🔊  Tap to see word")
            self.setStyleSheet("""
                #flashcard {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #27AE60, stop:1 #1E8449);
                    border-radius: 20px; border: 2px solid #2ECC71;
                }
                #cardWord { color: #FFFFFF; font-size: 36px; font-weight: bold; }
                #cardPhonetic { color: transparent; font-size: 0px; }
                #cardPos { color: transparent; font-size: 0px; }
                #cardSub { color: #D5F5E3; font-size: 15px; font-style: italic; }
                #cardHint { color: #A9DFBF; font-size: 13px; margin-top: 10px; }
            """)

    def mousePressEvent(self, event):
        self._showing_front = not self._showing_front
        self.set_card(self._word_data, self._showing_front)
        self.flipped.emit()
        super().mousePressEvent(event)

    def flip_to_front(self):
        self._showing_front = True
        self.set_card(self._word_data, True)


class CircularProgress(QWidget):
    def __init__(self, parent=None, size=120, line_width=8):
        super().__init__(parent)
        self._value = 0
        self._max_value = 100
        self._size = size
        self._line_width = line_width
        self._color = QColor("#4A90D9")
        self._bg_color = QColor("#2C3E50")
        self._text = ""
        self.setFixedSize(size, size)

    def set_value(self, val, max_val=100, text="", color=None):
        self._value = val
        self._max_value = max_val
        self._text = text
        if color:
            self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        margin = self._line_width // 2 + 2
        rect = QRect(margin, margin, self._size - 2 * margin, self._size - 2 * margin)
        pen = QPen(self._bg_color, self._line_width, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)
        progress = self._value / self._max_value if self._max_value > 0 else 0
        pen = QPen(self._color, self._line_width, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 90 * 16, -int(progress * 360 * 16))
        painter.setPen(QPen(self._color))
        font = QFont("Segoe UI", 14, QFont.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, self._text)
        painter.end()


class NavButton(QPushButton):
    def __init__(self, text, icon_char="", parent=None):
        super().__init__(parent)
        self._active = False
        self.setText(f"  {icon_char}  {text}")
        self.setMinimumHeight(48)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("navButton")
        self.update_style()

    @property
    def active(self):
        return self._active

    @active.setter
    def active(self, val):
        self._active = val
        self.update_style()

    def update_style(self):
        if self._active:
            self.setStyleSheet("""
                #navButton {
                    background: rgba(74, 144, 217, 0.2); color: #4A90D9;
                    border: none; border-left: 3px solid #4A90D9;
                    border-radius: 0 8px 8px 0; font-size: 14px;
                    font-weight: bold; text-align: left; padding-left: 20px;
                }
                #navButton:hover { background: rgba(74, 144, 217, 0.3); }
            """)
        else:
            self.setStyleSheet("""
                #navButton {
                    background: transparent; color: #8E9EAB;
                    border: none; border-left: 3px solid transparent;
                    border-radius: 0 8px 8px 0; font-size: 14px;
                    font-weight: normal; text-align: left; padding-left: 20px;
                }
                #navButton:hover {
                    background: rgba(255, 255, 255, 0.05); color: #BDC3C7;
                }
            """)


class CategoryCard(QFrame):
    clicked = Signal(str, int)  # category_name, category_id

    def __init__(self, title, cat_id, word_count, learned, color, icon="📋", parent=None):
        super().__init__(parent)
        self._title = title
        self._cat_id = cat_id
        self._color = color
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(110)
        self.setObjectName("categoryCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)

        header_row = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 20px;")
        title_lbl = QLabel(title)
        title_lbl.setObjectName("catTitle")
        header_row.addWidget(icon_lbl)
        header_row.addWidget(title_lbl)
        header_row.addStretch()

        progress_pct = int((learned / word_count * 100) if word_count > 0 else 0)
        progress_text = QLabel(f"{learned}/{word_count} words • {progress_pct}%")
        progress_text.setObjectName("catProgress")

        bar = QProgressBar()
        bar.setRange(0, word_count)
        bar.setValue(learned)
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setObjectName("catBar")

        layout.addLayout(header_row)
        layout.addWidget(progress_text)
        layout.addWidget(bar)

        self.setStyleSheet(f"""
            #categoryCard {{
                background: #1E2A38; border-radius: 14px;
                border: 1px solid #2C3E50;
            }}
            #categoryCard:hover {{
                border: 2px solid {color}; background: #223344;
            }}
            #catTitle {{ color: #FFFFFF; font-size: 16px; font-weight: bold; }}
            #catProgress {{ color: #8E9EAB; font-size: 12px; }}
            #catBar {{ background: #2C3E50; border-radius: 3px; }}
            #catBar::chunk {{ background: {color}; border-radius: 3px; }}
        """)

    def mousePressEvent(self, event):
        self.clicked.emit(self._title, self._cat_id)
        super().mousePressEvent(event)


class StreakWidget(QFrame):
    def __init__(self, streak, parent=None):
        super().__init__(parent)
        self.setObjectName("streakWidget")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        flame = QLabel("🔥")
        flame.setStyleSheet("font-size: 28px;")
        count = QLabel(str(streak))
        count.setStyleSheet("color: #F39C12; font-size: 22px; font-weight: bold;")
        label = QLabel("day streak")
        label.setStyleSheet("color: #F5B041; font-size: 13px;")
        layout.addWidget(flame)
        layout.addWidget(count)
        layout.addWidget(label)
        layout.addStretch()
        self.setStyleSheet("""
            #streakWidget {
                background: rgba(243, 156, 18, 0.1);
                border: 1px solid rgba(243, 156, 18, 0.3);
                border-radius: 12px;
            }
        """)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PAGES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DashboardPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.db: DatabaseManager = main_window.db
        self._current_lang = ""
        self._build_ui()

    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 20, 30, 20)
        self.main_layout.setSpacing(16)

    def refresh(self):
        # Clear
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        lang_code = self.db.get_setting("current_language", "es")
        self._current_lang = lang_code

        # Header
        header = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: bold;")

        self.lang_combo = QComboBox()
        languages = self.db.get_languages()
        for lang in languages:
            self.lang_combo.addItem(
                f"{lang['flag_emoji']} {lang['name']}", lang["code"]
            )
        idx = self.lang_combo.findData(lang_code)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(self._change_language)
        self.lang_combo.setStyleSheet("""
            QComboBox {
                background: #1E2A38; color: #FFFFFF;
                border: 1px solid #2C3E50; border-radius: 8px;
                padding: 8px 16px; font-size: 14px; min-width: 180px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #1E2A38; color: #FFFFFF;
                selection-background-color: #4A90D9;
                border: 1px solid #2C3E50;
            }
        """)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.lang_combo)
        self.main_layout.addLayout(header)

        # Streak
        streak = self.db.get_streak()
        self.main_layout.addWidget(StreakWidget(streak))

        # Stats
        try:
            stats = self.db.get_progress_stats(lang_code)
        except LanguageNotFoundError:
            stats = {"total_words": 0, "words_learned": 0, "words_mastered": 0,
                     "total_reviews": 0, "words_due": 0}

        lang_info = self.db.get_language(lang_code)
        quiz_count = len(self.db.get_quiz_history(lang_code, limit=1000))

        stats_frame = QHBoxLayout()
        stats_frame.setSpacing(16)
        stat_data = [
            ("📚", "Words Learned", str(stats["words_learned"]),
             f"of {stats['total_words']}", "#4A90D9"),
            ("⭐", "Mastered", str(stats["words_mastered"]),
             "words in box 4+", "#9B59B6"),
            ("🔄", "Total Reviews", str(stats["total_reviews"]),
             "all time", "#27AE60"),
            ("📝", "Quizzes", str(quiz_count), "completed", "#F39C12"),
        ]

        for icon, label, value, sub, color in stat_data:
            card = QFrame()
            card.setStyleSheet("""
                QFrame { background: #1E2A38; border-radius: 14px;
                         border: 1px solid #2C3E50; padding: 5px; }
            """)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(20, 15, 20, 15)
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet("font-size: 28px;")
            val_lbl = QLabel(value)
            val_lbl.setStyleSheet(f"color: {color}; font-size: 28px; font-weight: bold;")
            lab_lbl = QLabel(label)
            lab_lbl.setStyleSheet("color: #8E9EAB; font-size: 13px;")
            sub_lbl = QLabel(sub)
            sub_lbl.setStyleSheet("color: #5D6D7E; font-size: 11px;")
            cl.addWidget(icon_lbl)
            cl.addWidget(val_lbl)
            cl.addWidget(lab_lbl)
            cl.addWidget(sub_lbl)
            stats_frame.addWidget(card)
        self.main_layout.addLayout(stats_frame)

        # Due for review
        if stats["words_due"] > 0:
            due_btn = QPushButton(f"🔔  {stats['words_due']} words due for review — Click to review!")
            due_btn.setCursor(Qt.PointingHandCursor)
            due_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(231, 76, 60, 0.15); color: #E74C3C;
                    border: 1px solid rgba(231, 76, 60, 0.4); border-radius: 10px;
                    font-size: 14px; font-weight: bold; padding: 12px;
                }
                QPushButton:hover { background: rgba(231, 76, 60, 0.25); }
            """)
            due_btn.clicked.connect(lambda: self.mw.navigate_to_flashcards(
                "Due for Review", category_id=None
            ))
            self.main_layout.addWidget(due_btn)

        # Category cards
        cat_label = QLabel("Vocabulary Categories")
        cat_label.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: bold; margin-top: 6px;")
        self.main_layout.addWidget(cat_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        cat_container = QWidget()
        cat_layout = QGridLayout(cat_container)
        cat_layout.setSpacing(16)

        try:
            categories = self.db.get_categories(lang_code)
            learned_ids = self.db.get_learned_word_ids(lang_code)

            for i, cat in enumerate(categories):
                words = self.db.get_words(lang_code, cat["id"])
                learned = sum(1 for w in words if w["id"] in learned_ids)
                card = CategoryCard(
                    cat["name"], cat["id"], len(words),
                    learned, cat.get("color", "#4A90D9"),
                    cat.get("icon", "📋")
                )
                card.clicked.connect(self._open_flashcards)
                cat_layout.addWidget(card, i // 2, i % 2)

            # Mixed
            all_words = self.db.get_words(lang_code)
            all_learned = sum(1 for w in all_words if w["id"] in learned_ids)
            mix_card = CategoryCard(
                "Mixed (All)", None, len(all_words),
                all_learned, "#9B59B6", "🎲"
            )
            mix_card.clicked.connect(self._open_flashcards)
            cat_layout.addWidget(mix_card, len(categories) // 2, len(categories) % 2)

        except LanguageNotFoundError as e:
            err_lbl = QLabel(f"⚠️ {e.message}\n{e.details}")
            err_lbl.setStyleSheet("color: #E74C3C; font-size: 14px; padding: 20px;")
            cat_layout.addWidget(err_lbl, 0, 0)

        scroll.setWidget(cat_container)
        self.main_layout.addWidget(scroll, 1)

    def _change_language(self, index):
        code = self.lang_combo.itemData(index)
        if code:
            self.db.set_setting("current_language", code)
            self.refresh()

    def _open_flashcards(self, category_name, category_id):
        self.mw.navigate_to_flashcards(category_name, category_id)


class FlashcardPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.db: DatabaseManager = main_window.db
        self.words = []
        self.current_index = 0
        self._build_ui()

    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 20, 30, 20)
        self.main_layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #4A90D9;
                font-size: 14px; font-weight: bold; border: none; padding: 8px; }
            QPushButton:hover { color: #5BA3EC; }
        """)
        back_btn.clicked.connect(lambda: self.mw.navigate_to("dashboard"))

        self.title_label = QLabel("Flashcards")
        self.title_label.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
        self.counter_label = QLabel("0/0")
        self.counter_label.setStyleSheet("color: #8E9EAB; font-size: 14px;")

        header.addWidget(back_btn)
        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.counter_label)
        self.main_layout.addLayout(header)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background: #2C3E50; border-radius: 3px; }
            QProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #4A90D9, stop:1 #27AE60);
                border-radius: 3px;
            }
        """)
        self.main_layout.addWidget(self.progress_bar)

        # Card
        card_area = QHBoxLayout()
        card_area.addStretch()
        self.flashcard = FlipCard()
        card_area.addWidget(self.flashcard)
        card_area.addStretch()
        self.main_layout.addLayout(card_area, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)

        self.dont_know_btn = QPushButton("✗  Still Learning")
        self.dont_know_btn.setCursor(Qt.PointingHandCursor)
        self.dont_know_btn.setMinimumHeight(50)
        self.dont_know_btn.setStyleSheet("""
            QPushButton { background: #E74C3C; color: white; border: none;
                border-radius: 12px; font-size: 15px; font-weight: bold;
                padding: 12px 30px; }
            QPushButton:hover { background: #C0392B; }
        """)
        self.dont_know_btn.clicked.connect(self.mark_unknown)

        self.know_btn = QPushButton("✓  I Know This")
        self.know_btn.setCursor(Qt.PointingHandCursor)
        self.know_btn.setMinimumHeight(50)
        self.know_btn.setStyleSheet("""
            QPushButton { background: #27AE60; color: white; border: none;
                border-radius: 12px; font-size: 15px; font-weight: bold;
                padding: 12px 30px; }
            QPushButton:hover { background: #1E8449; }
        """)
        self.know_btn.clicked.connect(self.mark_known)

        btn_layout.addStretch()
        btn_layout.addWidget(self.dont_know_btn)
        btn_layout.addWidget(self.know_btn)
        btn_layout.addStretch()
        self.main_layout.addLayout(btn_layout)

        # Summary
        self.summary_frame = QFrame()
        self.summary_frame.setObjectName("summaryFrame")
        sl = QVBoxLayout(self.summary_frame)
        sl.setContentsMargins(40, 40, 40, 40)
        self.summary_label = QLabel("")
        self.summary_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: bold;")
        self.summary_detail = QLabel("")
        self.summary_detail.setAlignment(Qt.AlignCenter)
        self.summary_detail.setStyleSheet("color: #8E9EAB; font-size: 14px;")
        again_btn = QPushButton("🔄  Study Again")
        again_btn.setCursor(Qt.PointingHandCursor)
        again_btn.setMinimumHeight(50)
        again_btn.setStyleSheet("""
            QPushButton { background: #4A90D9; color: white; border: none;
                border-radius: 12px; font-size: 15px; font-weight: bold;
                padding: 12px 30px; }
            QPushButton:hover { background: #357ABD; }
        """)
        again_btn.clicked.connect(self._restart)
        sl.addWidget(self.summary_label)
        sl.addWidget(self.summary_detail)
        sl.addSpacing(10)
        sl.addWidget(again_btn, alignment=Qt.AlignCenter)
        self.summary_frame.setStyleSheet("""
            #summaryFrame { background: #1E2A38; border-radius: 20px; padding: 40px; }
        """)
        self.summary_frame.hide()
        self.main_layout.addWidget(self.summary_frame, 1)

        self._category_name = ""
        self._category_id = None
        self._known_count = 0
        self._unknown_count = 0

    def load_category(self, category_name, category_id=None):
        self._category_name = category_name
        self._category_id = category_id
        lang_code = self.db.get_setting("current_language", "es")

        try:
            if category_name == "Due for Review":
                self.words = self.db.get_words_for_review(lang_code, limit=20)
                if not self.words:
                    self.words = self.db.get_words(lang_code, category_id)
                    random.shuffle(self.words)
                    self.words = self.words[:10]
            elif category_id is not None:
                self.words = self.db.get_words(lang_code, category_id)
                random.shuffle(self.words)
            else:
                self.words = self.db.get_words(lang_code)
                random.shuffle(self.words)
        except LanguageNotFoundError as e:
            QMessageBox.warning(self, "Language Not Found",
                                f"{e.message}\n\n{e.details}")
            self.mw.navigate_to("dashboard")
            return

        if not self.words:
            QMessageBox.information(self, "No Words",
                                    "No vocabulary words found for this selection.")
            self.mw.navigate_to("dashboard")
            return

        self.current_index = 0
        self._known_count = 0
        self._unknown_count = 0
        self.title_label.setText(f"Flashcards — {category_name}")
        self.summary_frame.hide()
        self.flashcard.show()
        self.dont_know_btn.show()
        self.know_btn.show()
        self.progress_bar.show()
        self.counter_label.show()
        self._show_card()

    def _show_card(self):
        if self.current_index >= len(self.words):
            self._show_summary()
            return
        word_data = self.words[self.current_index]
        self.flashcard.flip_to_front()
        self.flashcard.set_card(word_data, showing_front=True)
        self.counter_label.setText(f"{self.current_index + 1}/{len(self.words)}")
        self.progress_bar.setRange(0, len(self.words))
        self.progress_bar.setValue(self.current_index)

    def mark_known(self):
        if self.current_index < len(self.words):
            w = self.words[self.current_index]
            lang = self.db.get_setting("current_language", "es")
            try:
                self.db.update_word_progress(lang, w["id"], correct=True)
            except Exception as e:
                logger.error(f"Progress update failed: {e}")
            self._known_count += 1
            self.current_index += 1
            self._show_card()

    def mark_unknown(self):
        if self.current_index < len(self.words):
            w = self.words[self.current_index]
            lang = self.db.get_setting("current_language", "es")
            try:
                self.db.update_word_progress(lang, w["id"], correct=False)
            except Exception as e:
                logger.error(f"Progress update failed: {e}")
            self._unknown_count += 1
            self.current_index += 1
            self._show_card()

    def _show_summary(self):
        self.flashcard.hide()
        self.dont_know_btn.hide()
        self.know_btn.hide()
        self.progress_bar.hide()
        self.counter_label.hide()

        self.db.update_streak()
        total = len(self.words)
        pct = int(self._known_count / total * 100) if total else 0
        emoji = "🌟" if pct >= 80 else "👍" if pct >= 50 else "💪"
        self.summary_label.setText(f"{emoji}  Session Complete!")
        self.summary_detail.setText(
            f"You knew {self._known_count} out of {total} words ({pct}%)\n"
            f"Keep practicing to master them all!"
        )
        self.summary_frame.show()

    def _restart(self):
        self.load_category(self._category_name, self._category_id)


class QuizPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.db: DatabaseManager = main_window.db
        self.questions = []
        self.current_q = 0
        self.score = 0
        self.answered = False
        self._build_ui()

    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 20, 30, 20)
        self.main_layout.setSpacing(16)

        header = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #4A90D9;
                font-size: 14px; font-weight: bold; border: none; padding: 8px; }
            QPushButton:hover { color: #5BA3EC; }
        """)
        back_btn.clicked.connect(lambda: self.mw.navigate_to("dashboard"))
        self.title_label = QLabel("Quiz Mode")
        self.title_label.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
        self.score_label = QLabel("Score: 0")
        self.score_label.setStyleSheet("color: #27AE60; font-size: 16px; font-weight: bold;")
        header.addWidget(back_btn)
        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.score_label)
        self.main_layout.addLayout(header)

        self.quiz_progress = QProgressBar()
        self.quiz_progress.setTextVisible(False)
        self.quiz_progress.setFixedHeight(6)
        self.quiz_progress.setStyleSheet("""
            QProgressBar { background: #2C3E50; border-radius: 3px; }
            QProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #F39C12, stop:1 #E74C3C); border-radius: 3px;
            }
        """)
        self.main_layout.addWidget(self.quiz_progress)

        # Selection
        self.selection_frame = QWidget()
        sel_layout = QVBoxLayout(self.selection_frame)
        sel_title = QLabel("Choose a Category")
        sel_title.setAlignment(Qt.AlignCenter)
        sel_title.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: bold;")
        sel_sub = QLabel("Test your vocabulary knowledge")
        sel_sub.setAlignment(Qt.AlignCenter)
        sel_sub.setStyleSheet("color: #8E9EAB; font-size: 14px;")
        sel_layout.addWidget(sel_title)
        sel_layout.addWidget(sel_sub)
        sel_layout.addSpacing(20)

        self.cat_buttons_layout = QVBoxLayout()
        sel_layout.addLayout(self.cat_buttons_layout)
        sel_layout.addStretch()

        # Question
        self.question_frame = QWidget()
        q_layout = QVBoxLayout(self.question_frame)
        self.question_number = QLabel("Question 1")
        self.question_number.setStyleSheet("color: #8E9EAB; font-size: 13px;")
        self.question_text = QLabel("")
        self.question_text.setAlignment(Qt.AlignCenter)
        self.question_text.setWordWrap(True)
        self.question_text.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: bold;")
        self.question_instruction = QLabel("")
        self.question_instruction.setAlignment(Qt.AlignCenter)
        self.question_instruction.setStyleSheet("color: #8E9EAB; font-size: 14px;")

        self.button_group = QButtonGroup()
        self.answer_buttons = []
        for i in range(4):
            btn = QRadioButton()
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QRadioButton {
                    color: #FFFFFF; font-size: 16px; padding: 14px 20px;
                    background: #1E2A38; border-radius: 10px;
                    border: 1px solid #2C3E50;
                }
                QRadioButton::indicator { width: 0; height: 0; }
                QRadioButton:hover { background: #253545; border: 1px solid #4A90D9; }
            """)
            self.answer_buttons.append(btn)
            self.button_group.addButton(btn, i)
            q_layout.addWidget(btn)

        self.button_group.buttonClicked.connect(self._on_answer)
        self.feedback_label = QLabel("")
        self.feedback_label.setAlignment(Qt.AlignCenter)
        self.feedback_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")

        self.next_btn = QPushButton("Next Question →")
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setStyleSheet("""
            QPushButton { background: #4A90D9; color: white; border: none;
                border-radius: 10px; font-size: 15px; font-weight: bold;
                padding: 12px 30px; }
            QPushButton:hover { background: #357ABD; }
            QPushButton:disabled { background: #2C3E50; color: #5D6D7E; }
        """)
        self.next_btn.clicked.connect(self._next_question)
        self.next_btn.setEnabled(False)

        q_layout.addWidget(self.question_number)
        q_layout.addSpacing(5)
        q_layout.addWidget(self.question_instruction)
        q_layout.addWidget(self.question_text)
        q_layout.addSpacing(20)
        for b in self.answer_buttons:
            q_layout.addWidget(b)
        q_layout.addWidget(self.feedback_label)
        q_layout.addWidget(self.next_btn, alignment=Qt.AlignCenter)
        q_layout.addStretch()

        # Result
        self.result_frame = QFrame()
        self.result_frame.setObjectName("resultFrame")
        rl = QVBoxLayout(self.result_frame)
        rl.setContentsMargins(40, 40, 40, 40)
        self.result_emoji = QLabel("")
        self.result_emoji.setAlignment(Qt.AlignCenter)
        self.result_emoji.setStyleSheet("font-size: 64px;")
        self.result_title = QLabel("")
        self.result_title.setAlignment(Qt.AlignCenter)
        self.result_title.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: bold;")
        self.result_score = QLabel("")
        self.result_score.setAlignment(Qt.AlignCenter)
        self.result_score.setStyleSheet("color: #8E9EAB; font-size: 18px;")
        retry_btn = QPushButton("🔄  Try Again")
        retry_btn.setCursor(Qt.PointingHandCursor)
        retry_btn.setStyleSheet("""
            QPushButton { background: #4A90D9; color: white; border: none;
                border-radius: 12px; font-size: 15px; font-weight: bold;
                padding: 14px 30px; }
            QPushButton:hover { background: #357ABD; }
        """)
        retry_btn.clicked.connect(self._show_selection)
        back2 = QPushButton("← Back to Dashboard")
        back2.setCursor(Qt.PointingHandCursor)
        back2.setStyleSheet("""
            QPushButton { background: transparent; color: #8E9EAB;
                border: 1px solid #2C3E50; border-radius: 12px;
                font-size: 14px; padding: 12px 30px; }
            QPushButton:hover { color: #FFFFFF; border: 1px solid #4A90D9; }
        """)
        back2.clicked.connect(lambda: self.mw.navigate_to("dashboard"))
        rl.addWidget(self.result_emoji)
        rl.addSpacing(10)
        rl.addWidget(self.result_title)
        rl.addWidget(self.result_score)
        rl.addSpacing(20)
        rl.addWidget(retry_btn, alignment=Qt.AlignCenter)
        rl.addWidget(back2, alignment=Qt.AlignCenter)
        self.result_frame.setStyleSheet("#resultFrame { background: #1E2A38; border-radius: 20px; }")
        self.result_frame.hide()

        self.main_layout.addWidget(self.selection_frame, 1)
        self.main_layout.addWidget(self.question_frame, 1)
        self.main_layout.addWidget(self.result_frame, 1)
        self.question_frame.hide()

    def _show_selection(self):
        self.selection_frame.show()
        self.question_frame.hide()
        self.result_frame.hide()

        while self.cat_buttons_layout.count():
            item = self.cat_buttons_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        lang_code = self.db.get_setting("current_language", "es")
        try:
            categories = self.db.get_categories(lang_code)
        except LanguageNotFoundError as e:
            lbl = QLabel(f"⚠️ {e.message}\n{e.details}")
            lbl.setStyleSheet("color: #E74C3C; font-size: 14px;")
            self.cat_buttons_layout.addWidget(lbl)
            return

        colors = ["#4A90D9", "#27AE60", "#F39C12", "#E74C3C", "#9B59B6", "#1ABC9C"]
        for i, cat in enumerate(categories):
            btn = QPushButton(f"  {cat.get('icon', '📋')}  {cat['name']}")
            btn.setCursor(Qt.PointingHandCursor)
            c = cat.get("color", colors[i % len(colors)])
            btn.setStyleSheet(f"""
                QPushButton {{ background: #1E2A38; color: #FFFFFF;
                    border: 1px solid {c}; border-radius: 12px;
                    font-size: 16px; font-weight: bold; padding: 16px; text-align: left; }}
                QPushButton:hover {{ background: #223344; border: 2px solid {c}; }}
            """)
            btn.clicked.connect(lambda checked, cid=cat["id"]: self._start_quiz(cid))
            self.cat_buttons_layout.addWidget(btn)

        mix_btn = QPushButton("  🎲  Mixed (All Categories)")
        mix_btn.setCursor(Qt.PointingHandCursor)
        mix_btn.setStyleSheet("""
            QPushButton { background: #1E2A38; color: #F39C12;
                border: 2px solid #F39C12; border-radius: 12px;
                font-size: 16px; font-weight: bold; padding: 16px; text-align: left; }
            QPushButton:hover { background: #223344; }
        """)
        mix_btn.clicked.connect(lambda: self._start_quiz(None))
        self.cat_buttons_layout.addWidget(mix_btn)

    def _start_quiz(self, category_id):
        lang_code = self.db.get_setting("current_language", "es")
        try:
            if category_id is not None:
                self.questions = self.db.get_words(lang_code, category_id)
            else:
                self.questions = self.db.get_words(lang_code)
        except LanguageNotFoundError as e:
            QMessageBox.warning(self, "Error", f"{e.message}\n\n{e.details}")
            return

        if len(self.questions) < 4:
            QMessageBox.warning(self, "Not Enough Words",
                                "Need at least 4 words for a quiz.")
            return

        random.shuffle(self.questions)
        self.questions = self.questions[:min(10, len(self.questions))]
        self.current_q = 0
        self.score = 0
        self.answered = False
        self._category_id = category_id

        self.selection_frame.hide()
        self.result_frame.hide()
        self.question_frame.show()
        self.score_label.setText("Score: 0")
        self._show_question()

    def _show_question(self):
        if self.current_q >= len(self.questions):
            self._show_results()
            return
        self.answered = False
        self.next_btn.setEnabled(False)
        self.feedback_label.setText("")

        q = self.questions[self.current_q]
        self.question_number.setText(f"Question {self.current_q + 1} of {len(self.questions)}")

        q_type = random.choice(["w2t", "t2w"])
        if q_type == "w2t":
            self.question_text.setText(q["word"])
            self.question_instruction.setText("What is the translation?")
            correct = q["translation"]
        else:
            self.question_text.setText(q["translation"])
            self.question_instruction.setText(f'What means "{q["translation"]}"?')
            correct = q["word"]

        all_answers = []
        lang_code = self.db.get_setting("current_language", "es")
        try:
            all_words = self.db.get_words(lang_code)
            if q_type == "w2t":
                all_answers = list(set(w["translation"] for w in all_words))
            else:
                all_answers = list(set(w["word"] for w in all_words))
        except LanguageNotFoundError:
            all_answers = [correct]

        if correct in all_answers:
            all_answers.remove(correct)
        random.shuffle(all_answers)
        wrong = all_answers[:3]
        answers = wrong + [correct]
        random.shuffle(answers)
        self._correct_idx = answers.index(correct)
        self._correct_answer = correct

        for i, btn in enumerate(self.answer_buttons):
            btn.setText(f"  {answers[i]}")
            btn.setChecked(False)
            btn.setStyleSheet("""
                QRadioButton { color: #FFFFFF; font-size: 16px; padding: 14px 20px;
                    background: #1E2A38; border-radius: 10px; border: 1px solid #2C3E50; }
                QRadioButton::indicator { width: 0; height: 0; }
                QRadioButton:hover { background: #253545; border: 1px solid #4A90D9; }
            """)

        self.quiz_progress.setRange(0, len(self.questions))
        self.quiz_progress.setValue(self.current_q)

    def _on_answer(self, button):
        if self.answered:
            return
        self.answered = True
        self.next_btn.setEnabled(True)
        idx = self.button_group.id(button)
        correct = (idx == self._correct_idx)

        for i, btn in enumerate(self.answer_buttons):
            if i == self._correct_idx:
                btn.setStyleSheet("""
                    QRadioButton { color: #FFFFFF; font-size: 16px; padding: 14px 20px;
                        background: rgba(39,174,96,0.3); border-radius: 10px;
                        border: 2px solid #27AE60; }
                    QRadioButton::indicator { width: 0; height: 0; }
                """)
            elif i == idx and not correct:
                btn.setStyleSheet("""
                    QRadioButton { color: #FFFFFF; font-size: 16px; padding: 14px 20px;
                        background: rgba(231,76,60,0.3); border-radius: 10px;
                        border: 2px solid #E74C3C; }
                    QRadioButton::indicator { width: 0; height: 0; }
                """)

        if correct:
            self.score += 1
            self.score_label.setText(f"Score: {self.score}")
            self.feedback_label.setStyleSheet("color: #27AE60; font-size: 16px; font-weight: bold; margin-top: 10px;")
            self.feedback_label.setText("✓ Correct!")
        else:
            self.feedback_label.setStyleSheet("color: #E74C3C; font-size: 16px; font-weight: bold; margin-top: 10px;")
            self.feedback_label.setText(f"✗ Answer: {self._correct_answer}")

    def _next_question(self):
        self.current_q += 1
        self._show_question()

    def _show_results(self):
        self.question_frame.hide()
        self.result_frame.show()
        total = len(self.questions)
        pct = int(self.score / total * 100) if total else 0
        emoji = "🏆" if pct == 100 else "🌟" if pct >= 80 else "👍" if pct >= 60 else "💪" if pct >= 40 else "📚"
        title = {100: "Perfect!", 80: "Excellent!", 60: "Good Job!",
                 40: "Keep Practicing!", 0: "Study More!"}.get(
            max(k for k in [0, 40, 60, 80, 100] if k <= pct), "Keep Going!")

        self.result_emoji.setText(emoji)
        self.result_title.setText(title)
        self.result_score.setText(f"{self.score}/{total} correct ({pct}%)")

        lang_code = self.db.get_setting("current_language", "es")
        try:
            self.db.save_quiz_result(lang_code, self._category_id, self.score, total)
            self.db.update_streak()
        except Exception as e:
            logger.error(f"Failed to save quiz result: {e}")


class StatsPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.db: DatabaseManager = main_window.db
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(20)

        title = QLabel("Statistics")
        title.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: bold;")
        layout.addWidget(title)

        lang_code = self.db.get_setting("current_language", "es")
        try:
            stats = self.db.get_progress_stats(lang_code)
            avg_quiz = self.db.get_avg_quiz_score(lang_code)
            streak = self.db.get_streak()
        except LanguageNotFoundError:
            stats = {"total_words": 0, "words_learned": 0, "words_mastered": 0,
                     "total_reviews": 0, "words_due": 0}
            avg_quiz = 0.0
            streak = 0

        # Circles
        circles_layout = QHBoxLayout()
        circles_layout.setSpacing(30)
        circle_data = [
            (stats["words_learned"], stats["total_words"],
             str(stats["words_learned"]), "Words Learned", "#4A90D9"),
            (int(avg_quiz), 100, f"{int(avg_quiz)}%", "Avg Quiz Score", "#27AE60"),
            (streak, max(streak, 30), str(streak), "Day Streak", "#F39C12"),
            (stats["words_mastered"], stats["total_words"],
             str(stats["words_mastered"]), "Mastered", "#9B59B6"),
        ]
        for val, mx, text, label, color in circle_data:
            frame = QFrame()
            frame.setStyleSheet("QFrame { background: #1E2A38; border-radius: 14px; }")
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(20, 20, 20, 10)
            fl.setAlignment(Qt.AlignCenter)
            circle = CircularProgress(size=130, line_width=10)
            circle.set_value(val, mx, text, color)
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #8E9EAB; font-size: 13px; margin-top: 5px;")
            fl.addWidget(circle, alignment=Qt.AlignCenter)
            fl.addWidget(lbl)
            circles_layout.addWidget(frame)
        layout.addLayout(circles_layout)

        # Quiz history
        hist_label = QLabel("Quiz History")
        hist_label.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(hist_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        hist_container = QWidget()
        hist_layout = QVBoxLayout(hist_container)
        hist_layout.setSpacing(8)

        try:
            quizzes = self.db.get_quiz_history(lang_code, limit=20)
        except LanguageNotFoundError:
            quizzes = []

        if quizzes:
            for q in quizzes:
                row = QFrame()
                row.setStyleSheet("""
                    QFrame { background: #1E2A38; border-radius: 8px;
                             border: 1px solid #2C3E50; }
                """)
                rl = QHBoxLayout(row)
                rl.setContentsMargins(16, 10, 16, 10)
                pct = int(q["score"] / q["total_questions"] * 100) if q["total_questions"] else 0
                color = "#27AE60" if pct >= 70 else "#F39C12" if pct >= 40 else "#E74C3C"
                score_lbl = QLabel(f"{q['score']}/{q['total_questions']}")
                score_lbl.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")
                cat_name = q.get("category_name") or "Mixed"
                cat_lbl = QLabel(cat_name)
                cat_lbl.setStyleSheet("color: #8E9EAB; font-size: 13px;")
                date_lbl = QLabel(q.get("quiz_date", "")[:16])
                date_lbl.setStyleSheet("color: #5D6D7E; font-size: 12px;")
                bar = QProgressBar()
                bar.setRange(0, q["total_questions"])
                bar.setValue(q["score"])
                bar.setTextVisible(False)
                bar.setFixedHeight(6)
                bar.setFixedWidth(120)
                bar.setStyleSheet(f"""
                    QProgressBar {{ background: #2C3E50; border-radius: 3px; }}
                    QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}
                """)
                rl.addWidget(score_lbl)
                rl.addWidget(cat_lbl)
                rl.addWidget(bar)
                rl.addStretch()
                rl.addWidget(date_lbl)
                hist_layout.addWidget(row)
        else:
            no_data = QLabel("No quizzes taken yet!")
            no_data.setStyleSheet("color: #5D6D7E; font-size: 14px; padding: 20px;")
            no_data.setAlignment(Qt.AlignCenter)
            hist_layout.addWidget(no_data)

        scroll.setWidget(hist_container)
        layout.addWidget(scroll, 1)


class LanguagesPage(QWidget):
    """Manage installed languages — import, export, remove."""
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.db: DatabaseManager = main_window.db
        self._build_ui()

    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 20, 30, 20)
        self.main_layout.setSpacing(16)

    def refresh(self):
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        title = QLabel("Manage Languages")
        title.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: bold;")
        self.main_layout.addWidget(title)

        # Import / Export buttons
        btn_row = QHBoxLayout()

        import_btn = QPushButton("📥  Import Language Pack (.db)")
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.setStyleSheet("""
            QPushButton { background: #4A90D9; color: white; border: none;
                border-radius: 12px; font-size: 14px; font-weight: bold;
                padding: 14px 24px; }
            QPushButton:hover { background: #357ABD; }
        """)
        import_btn.clicked.connect(self._import_pack)

        repair_btn = QPushButton("🔧  Repair Database")
        repair_btn.setCursor(Qt.PointingHandCursor)
        repair_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #F39C12;
                border: 1px solid #F39C12; border-radius: 12px;
                font-size: 13px; padding: 12px 20px; }
            QPushButton:hover { background: rgba(243, 156, 18, 0.1); }
        """)
        repair_btn.clicked.connect(self._repair_db)

        btn_row.addWidget(import_btn)
        btn_row.addStretch()
        btn_row.addWidget(repair_btn)
        self.main_layout.addLayout(btn_row)

        # Info
        info_lbl = QLabel(
            "Import external .db language packs that follow the PolyGlot schema. "
            "Each pack is validated before import."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: #5D6D7E; font-size: 12px; margin-bottom: 8px;")
        self.main_layout.addWidget(info_lbl)

        # Language table
        languages = self.db.get_languages()

        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(
            ["Language", "Code", "Words", "Author", "Version", "Actions"]
        )
        table.setRowCount(len(languages))
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setStyleSheet("""
            QTableWidget {
                background: #1E2A38; color: #FFFFFF; border: 1px solid #2C3E50;
                border-radius: 10px; gridline-color: #2C3E50;
                font-size: 13px;
            }
            QHeaderView::section {
                background: #151F2B; color: #8E9EAB; border: none;
                padding: 10px; font-weight: bold; font-size: 12px;
            }
            QTableWidget::item { padding: 8px; }
            QTableWidget::item:selected { background: rgba(74, 144, 217, 0.2); }
        """)

        for row, lang in enumerate(languages):
            table.setItem(row, 0, QTableWidgetItem(
                f"{lang['flag_emoji']} {lang['name']} ({lang['native_name']})"
            ))
            table.setItem(row, 1, QTableWidgetItem(lang["code"]))
            table.setItem(row, 2, QTableWidgetItem(str(lang.get("word_count", 0))))
            table.setItem(row, 3, QTableWidgetItem(lang.get("author", "")))
            table.setItem(row, 4, QTableWidgetItem(lang.get("version", "")))

            # Actions widget
            actions = QWidget()
            al = QHBoxLayout(actions)
            al.setContentsMargins(4, 4, 4, 4)

            export_btn = QPushButton("📤 Export")
            export_btn.setCursor(Qt.PointingHandCursor)
            export_btn.setStyleSheet("""
                QPushButton { background: #27AE60; color: white; border: none;
                    border-radius: 6px; font-size: 11px; padding: 5px 10px; }
                QPushButton:hover { background: #1E8449; }
            """)
            export_btn.clicked.connect(
                lambda checked, c=lang["code"]: self._export_lang(c)
            )

            remove_btn = QPushButton("🗑️ Remove")
            remove_btn.setCursor(Qt.PointingHandCursor)
            remove_btn.setStyleSheet("""
                QPushButton { background: #E74C3C; color: white; border: none;
                    border-radius: 6px; font-size: 11px; padding: 5px 10px; }
                QPushButton:hover { background: #C0392B; }
            """)
            remove_btn.clicked.connect(
                lambda checked, c=lang["code"], n=lang["name"]: self._remove_lang(c, n)
            )

            al.addWidget(export_btn)
            al.addWidget(remove_btn)
            table.setCellWidget(row, 5, actions)

        self.main_layout.addWidget(table, 1)

        # Schema info
        schema_lbl = QLabel(
            f"Schema version: {SCHEMA_VERSION}  •  "
            f"Required tables: {len(SchemaValidator.REQUIRED_TABLES)}  •  "
            f"DB path: {DB_PATH}"
        )
        schema_lbl.setStyleSheet("color: #3D4F5F; font-size: 11px;")
        schema_lbl.setWordWrap(True)
        self.main_layout.addWidget(schema_lbl)

    def _import_pack(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Language Pack", str(PACKS_DIR),
            "Database Files (*.db);;All Files (*)"
        )
        if not path:
            return

        pack_path = Path(path)

        # Pre-validate and show errors
        is_valid, errors = SchemaValidator.validate(pack_path)
        if not is_valid:
            error_text = "\n".join(f"  • {e}" for e in errors)
            QMessageBox.critical(
                self, "❌ Invalid Language Pack",
                f"The selected file failed validation:\n\n{error_text}\n\n"
                f"Please ensure the file follows the PolyGlot schema v{SCHEMA_VERSION}."
            )
            return

        # Import
        try:
            success, message = self.db.import_language_pack(pack_path)
            if success:
                QMessageBox.information(self, "✅ Import Successful", message)
            else:
                QMessageBox.warning(self, "⚠️ Import Issues", message)
        except InvalidLanguagePackError as e:
            QMessageBox.critical(self, "❌ Invalid Pack", f"{e.message}\n\n{e.details}")
        except DuplicateLanguageError as e:
            QMessageBox.warning(self, "⚠️ Duplicate", f"{e.message}\n\n{e.details}")
        except Exception as e:
            QMessageBox.critical(self, "❌ Error", f"Unexpected error:\n{e}")

        self.refresh()

    def _export_lang(self, code):
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export Language Pack",
            str(PACKS_DIR / f"polyglot_{code}.db"),
            "Database Files (*.db)"
        )
        if not path:
            return
        success, message = self.db.export_language_pack(code, Path(path))
        if success:
            QMessageBox.information(self, "✅ Exported", message)
        else:
            QMessageBox.critical(self, "❌ Export Failed", message)

    def _remove_lang(self, code, name):
        reply = QMessageBox.question(
            self, "Remove Language",
            f"Are you sure you want to remove {name} ({code})?\n\n"
            f"This will delete all associated vocabulary, progress, and quiz data.\n"
            f"This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.db.remove_language(code)
                QMessageBox.information(self, "Removed", f"{name} has been removed.")
            except LanguageNotFoundError as e:
                QMessageBox.warning(self, "Error", f"{e.message}")
            self.refresh()

    def _repair_db(self):
        reply = QMessageBox.question(
            self, "Repair Database",
            "This will check and attempt to repair the database.\n"
            "A backup will be created automatically.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            success, message = self.db.repair_database()
            if success:
                QMessageBox.information(self, "✅ Repair Complete", message)
            else:
                QMessageBox.critical(self, "❌ Repair Failed", message)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN WINDOW
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self._init_database()

        self.setWindowTitle("PolyGlot — Language Learning")
        self.setMinimumSize(1000, 700)
        self.resize(1100, 780)
        self._setup_ui()
        self._apply_theme()

    def _init_database(self):
        """Initialize database with full error handling."""
        try:
            self.db.connect()
            self.db.initialize()
            logger.info("Database initialized successfully.")
        except DatabaseCorruptedError as e:
            logger.critical(f"Database corrupted: {e}")
            # Attempt repair
            try:
                success, msg = self.db.repair_database()
                if success:
                    logger.info("Database repaired successfully.")
                else:
                    logger.critical(f"Repair failed: {msg}")
            except Exception:
                logger.critical("All recovery attempts failed.")
        except Exception as e:
            logger.critical(f"Unexpected database error: {e}")
            try:
                # Nuclear option — recreate
                if DB_PATH.exists():
                    backup = BACKUP_DIR / f"polyglot_emergency_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                    shutil.copy2(str(DB_PATH), str(backup))
                    DB_PATH.unlink()
                self.db = DatabaseManager()
                self.db.connect()
                self.db.initialize()
                logger.info("Database recreated from scratch.")
            except Exception as e2:
                logger.critical(f"Failed to recreate database: {e2}")

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar ──
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setObjectName("sidebar")
        sidebar.setStyleSheet("""
            #sidebar {
                background: #0F1923;
                border-right: 1px solid #1E2A38;
            }
        """)

        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 20, 0, 20)
        side_layout.setSpacing(4)

        logo_frame = QFrame()
        logo_layout = QVBoxLayout(logo_frame)
        logo_layout.setContentsMargins(20, 10, 20, 20)
        logo_lbl = QLabel("🌍 PolyGlot")
        logo_lbl.setStyleSheet("color: #4A90D9; font-size: 22px; font-weight: bold;")
        sub_lbl = QLabel("Learn languages easily")
        sub_lbl.setStyleSheet("color: #5D6D7E; font-size: 11px;")
        logo_layout.addWidget(logo_lbl)
        logo_layout.addWidget(sub_lbl)
        side_layout.addWidget(logo_frame)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #1E2A38; margin: 8px 16px;")
        side_layout.addWidget(sep)

        self.nav_buttons = {}
        nav_items = [
            ("dashboard", "🏠", "Dashboard"),
            ("flashcards", "🃏", "Flashcards"),
            ("quiz", "📝", "Quiz"),
            ("stats", "📊", "Statistics"),
            ("languages", "🌐", "Languages"),
        ]

        for key, icon, text in nav_items:
            btn = NavButton(text, icon)
            btn.clicked.connect(lambda checked, k=key: self.navigate_to(k))
            side_layout.addWidget(btn)
            self.nav_buttons[key] = btn

        side_layout.addStretch()

        ver = QLabel(f"v2.0 • Schema {SCHEMA_VERSION}")
        ver.setAlignment(Qt.AlignCenter)
        ver.setStyleSheet("color: #3D4F5F; font-size: 11px;")
        side_layout.addWidget(ver)

        main_layout.addWidget(sidebar)

        # ── Content ──
        content_frame = QFrame()
        content_frame.setObjectName("contentArea")
        content_frame.setStyleSheet("#contentArea { background: #151F2B; }")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)

        self.dashboard_page = DashboardPage(self)
        self.flashcard_page = FlashcardPage(self)
        self.quiz_page = QuizPage(self)
        self.stats_page = StatsPage(self)
        self.languages_page = LanguagesPage(self)

        self.stack.addWidget(self.dashboard_page)
        self.stack.addWidget(self.flashcard_page)
        self.stack.addWidget(self.quiz_page)
        self.stack.addWidget(self.stats_page)
        self.stack.addWidget(self.languages_page)

        main_layout.addWidget(content_frame, 1)

        self.navigate_to("dashboard")

    def navigate_to(self, page_name):
        if page_name == "dashboard":
            self.dashboard_page.refresh()
            self.stack.setCurrentWidget(self.dashboard_page)
        elif page_name == "flashcards":
            lang_code = self.db.get_setting("current_language", "es")
            try:
                cats = self.db.get_categories(lang_code)
                if cats:
                    self.flashcard_page.load_category(cats[0]["name"], cats[0]["id"])
                else:
                    self.flashcard_page.load_category("All Words", None)
            except LanguageNotFoundError:
                self.flashcard_page.load_category("All Words", None)
            self.stack.setCurrentWidget(self.flashcard_page)
        elif page_name == "quiz":
            self.quiz_page._show_selection()
            self.stack.setCurrentWidget(self.quiz_page)
        elif page_name == "stats":
            # Rebuild stats
            old = self.stats_page
            self.stats_page = StatsPage(self)
            idx = self.stack.indexOf(old)
            self.stack.removeWidget(old)
            old.deleteLater()
            self.stack.insertWidget(idx, self.stats_page)
            self.stack.setCurrentWidget(self.stats_page)
        elif page_name == "languages":
            self.languages_page.refresh()
            self.stack.setCurrentWidget(self.languages_page)

        for key, btn in self.nav_buttons.items():
            btn.active = (key == page_name)

    def navigate_to_flashcards(self, category_name, category_id=None):
        self.flashcard_page.load_category(category_name, category_id)
        self.stack.setCurrentWidget(self.flashcard_page)
        for key, btn in self.nav_buttons.items():
            btn.active = (key == "flashcards")

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow { background: #151F2B; }
            QScrollBar:vertical {
                background: #151F2B; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #2C3E50; border-radius: 4px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

    def closeEvent(self, event):
        self.db.close()
        logger.info("Application closed.")
        super().closeEvent(event)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#151F2B"))
    palette.setColor(QPalette.WindowText, QColor("#FFFFFF"))
    palette.setColor(QPalette.Base, QColor("#1E2A38"))
    palette.setColor(QPalette.AlternateBase, QColor("#151F2B"))
    palette.setColor(QPalette.ToolTipBase, QColor("#1E2A38"))
    palette.setColor(QPalette.ToolTipText, QColor("#FFFFFF"))
    palette.setColor(QPalette.Text, QColor("#FFFFFF"))
    palette.setColor(QPalette.Button, QColor("#1E2A38"))
    palette.setColor(QPalette.ButtonText, QColor("#FFFFFF"))
    palette.setColor(QPalette.BrightText, QColor("#E74C3C"))
    palette.setColor(QPalette.Link, QColor("#4A90D9"))
    palette.setColor(QPalette.Highlight, QColor("#4A90D9"))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()