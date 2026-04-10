import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "database.db")

def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Registrations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            exam_date TEXT,
            username TEXT,
            created_at TEXT NOT NULL
        )
    ''')

    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Users table (tracking bot users)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT
        )
    ''')

    # Default settings
    default_settings = [
        ('exam_info', "ℹ️ Ona tili Mock imtihoni haqida ma'lumot:\n• Sana: Belgilanmagan\n• Vaqt: 09:00\n• Manzil: BEST SCHOOL\n• Narx: Belgilanmagan"),
        ('deadline', '2026-12-31 23:59'),
        ('capacity', '100'),
        ('is_registration_open', '1')
    ]
    
    for key, value in default_settings:
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))

    conn.commit()
    conn.close()
    print(f"Database initialized at {DATABASE_PATH}")

if __name__ == "__main__":
    init_db()
