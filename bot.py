import os
import asyncio
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
import nest_asyncio  # For Render async compatibility

# Configuration
BOT_TOKEN = "7642147352:AAFhI8O8vpvSOovonO_A5UhTlTB4gpwFij4"
ADMIN_IDS = {6065778458}
DB_PATH = "filebot.db"
AUTO_DELETE_MINUTES = 30

# Database setup
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
    c.execute("SELECT owner_id FROM files WHERE id = ?", (file_db_id,))
    row = c.fetchone()
    if row:
        log_action(row[0], "auto-delete", f"File {file_db_id} auto-deleted")
    conn.close()

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
    else:
        await update.message.reply_text("You are not logged in.")
    conn.commit()
    conn.close()

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_admin(user_id):
        await update.message.reply_text("Access denied.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("View All Files", callback_data="admin_all_files")],
        [InlineKeyboardButton("Search User Files", callback_data="admin_search_user")],
        [InlineKeyboardButton("View User Credentials", callback_data="admin_user_creds")],
        [InlineKeyboardButton("Global Auto-Clean", callback_data="admin_clean")],
        [InlineKeyboardButton("View Logs", callback_data="admin_logs")]
    ])
    await update.message.reply_text("Admin Panel:", reply_markup=kb)

async def myfiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE telegram_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        await update.message.reply_text("Please login to see your files.")
        conn.close()
        return
    owner_id = row[0]
    c.execute("SELECT id, file_type, file_name, uploaded_at FROM files WHERE owner_id = ? AND deleted = 0", (owner_id,))
    files = c.fetchall()
    if not files:
        await update.message.reply_text("No active files.")
        conn.close()
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{f[1]}: {f[2]} ({f[3]})", callback_data=f"file_{f[0]}")]
        for f in files
    ])
    await update.message.reply_text("Your active files:", reply_markup=kb)
    conn.close()

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    await query.edit_message_text(f"You clicked: {data}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE telegram_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        await update.message.reply_text("Please login before uploading files.")
        conn.close()
        return
    owner_id = row[0]
    file_obj = update.message.document or (update.message.photo[-1] if update.message.photo else None) or update.message.video
    if not file_obj:
        await update.message.reply_text("Unsupported file type.")
        conn.close()
        return
    file_id = file_obj.file_id
    file_type = (
        "document" if update.message.document
        else "photo" if update.message.photo
        else "video"
    )
    file_name = getattr(file_obj, "file_name", "unnamed")
    now = datetime.utcnow()
    delete_at = now + timedelta(minutes=AUTO_DELETE_MINUTES)
    c.execute(
        "INSERT INTO files (owner_id, file_id, file_type, file_name, uploaded_at, delete_at) VALUES (?, ?, ?, ?, ?, ?)",
        (owner_id, file_id, file_type, file_name, now.isoformat(), delete_at.isoformat())
    )
    file_db_id = c.lastrowid
    log_action(owner_id, "upload", f"Uploaded {file_type}: {file_name}")
    conn.commit()
    conn.close()
    await update.message.reply_text(f"File {file_name} uploaded and scheduled for auto-deletion.")
    asyncio.create_task(auto_delete_file(file_db_id, AUTO_DELETE_MINUTES * 60))

async def main_async():
    nest_asyncio.apply()
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    await app.bot.delete_webhook(drop_pending_updates=True)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("myfiles", myfiles))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, handle_file))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main_async())DATABASE = "mega_cloud.db"
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

