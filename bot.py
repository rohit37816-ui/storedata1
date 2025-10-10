import os
import asyncio
import sqlite3
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
import nest_asyncio  # For compatibility with certain async environments

# CONFIGURATION
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = {6065778458}  # Replace with real admin Telegram IDs
DB_PATH = "filebot.db"
AUTO_DELETE_MINUTES = 30

# DATABASE SETUP
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        password TEXT,
        registered_at TEXT
    );
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        file_id TEXT,
        file_type TEXT,
        file_name TEXT,
        uploaded_at TEXT,
        deleted INTEGER DEFAULT 0,
        delete_at TEXT,
        FOREIGN KEY(owner_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        details TEXT,
        timestamp TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    conn.commit()
    conn.close()

# UTILITY FUNCTIONS
def log_action(user_id, action, details=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, action, details, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def check_admin(user_id):
    return user_id in ADMIN_IDS

async def auto_delete_file(file_db_id, delay_sec):
    await asyncio.sleep(delay_sec)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE files SET deleted = 1 WHERE id = ?", (file_db_id,))
    conn.commit()
    # Optionally log auto-deletion
    c.execute("SELECT owner_id FROM files WHERE id = ?", (file_db_id,))
    row = c.fetchone()
    if row:
        log_action(row[0], "auto-delete", f"File {file_db_id} auto-deleted")
    conn.close()

# COMMAND HANDLERS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Login", callback_data="login"),
         InlineKeyboardButton("Register", callback_data="register")]
    ])
    await update.message.reply_text("Welcome! Please login or register:", reply_markup=kb)

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE telegram_id = ?", (user_id,))
    row = c.fetchone()
    if row:
        owner_id = row[0]
        c.execute("UPDATE files SET deleted=1 WHERE owner_id=?", (owner_id,))
        log_action(owner_id, "logout", "User logged out and files deleted")
        await update.message.reply_text("You have been logged out. All your files are deleted.")
sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters

# ===== CONFIG =====
ADMIN_IDS = [6065778458]  # Replace with your Telegram ID(s)
DATABASE = "mega_cloud.db"
AUTO_DELETE_MINUTES = 30

# ===== BOT TOKEN =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing! Please set it in Render Environment Variables")

# ===== DATABASE SETUP =====
conn = sqlite3.connect(DATABASE, check_same_thread=False)
cur = conn.cursor()

cur.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    password TEXT,
    login_attempts INTEGER DEFAULT 0
)''')

cur.execute('''CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    user_id INTEGER,
    file_name TEXT,
    file_type TEXT,
    tag TEXT,
    is_deleted INTEGER DEFAULT 0,
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    download_count INTEGER DEFAULT 0
)''')

cur.execute('''CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')

conn.commit()

# ===== HELPERS =====
async def auto_delete_file(file_id, delay=AUTO_DELETE_MINUTES * 60):
    await asyncio.sleep(delay)
    cur.execute("UPDATE files SET is_deleted=1 WHERE file_id=?", (file_id,))
    conn.commit()

async def log_action(user_id, action):
    cur.execute("INSERT INTO logs (user_id, action) VALUES (?, ?)", (user_id, action))
    conn.commit()

def check_admin(user_id):
    return user_id in ADMIN_IDS

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Login/Register", callback_data="login_register")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome! Please login or register.", reply_markup=reply_markup)

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    cur.execute("DELETE FROM files WHERE user_id=?", (user_id,))
    conn.commit()
    await log_action(user_id, "Logged out, all files deleted")
    await update.message.reply_text("✅ You have logged out and all your files were deleted.")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not check_admin(user_id):
        await update.message.reply_text("❌ You are not an admin!")
        return
    keyboard = [
        [InlineKeyboardButton("View All Files", callback_data="adm_list_files")],
        [InlineKeyboardButton("Search User Files", callback_data="adm_search_user")],
        [InlineKeyboardButton("View User Credentials", callback_data="adm_view_users")],
        [InlineKeyboardButton("Global Auto-Clean", callback_data="adm_auto_clean")],
        [InlineKeyboardButton("View Logs", callback_data="adm_view_logs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚙️ Admin Panel", reply_markup=reply_markup)

async def myfiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    cur.execute("SELECT file_id, file_name, tag FROM files WHERE user_id=? AND is_deleted=0", (user_id,))
    rows = cur.fetchall()
    if rows:
        keyboard = [[InlineKeyboardButton(f"{r[1]} ({r[2]})", callback_data=f"file_{r[0]}")] for r in rows]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("📂 Your Files:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("You have no uploaded files.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    await query.edit_message_text(f"Button clicked: {data}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
