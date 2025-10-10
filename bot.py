import os
import asyncio
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
import nest_asyncio

# Configuration
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7642147352:AAFhI8O8vpvSOovonO_A5UhTlTB4gpwFij4")
ADMIN_IDS = {6065778458}
DB_PATH = "filebot.db"
AUTO_DELETE_MINUTES = 30

# Ensure only one event loop
nest_asyncio.apply()

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
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, action, details, datetime.utcnow().isoformat())
        )
        conn.commit()
    except Exception as e:
        print("DB log error:", e)
    finally:
        conn.close()

def check_admin(user_id):
    return user_id in ADMIN_IDS

async def auto_delete_file(file_db_id, delay_sec):
    try:
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
    except Exception as e:
        print("Auto-delete error:", e)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Login", callback_data="login"),
         InlineKeyboardButton("Register", callback_data="register")]
    ])
    await update.message.reply_text("Welcome! Please login or register:", reply_markup=kb)

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
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
    except Exception as e:
        print("Logout error:", e)
    finally:
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
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE telegram_id = ?", (user_id,))
        row = c.fetchone()
        if not row:
            await update.message.reply_text("Please login to see your files.")
            return
        owner_id = row[0]
        c.execute("SELECT id, file_type, file_name, uploaded_at FROM files WHERE owner_id = ? AND deleted = 0", (owner_id,))
        files = c.fetchall()
        if not files:
            await update.message.reply_text("No active files.")
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{f[1]}: {f[2]} ({f[3]})", callback_data=f"file_{f[0]}")]
            for f in files
        ])
        await update.message.reply_text("Your active files:", reply_markup=kb)
    except Exception as e:
        print("Myfiles error:", e)
    finally:
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
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE telegram_id = ?", (user_id,))
        row = c.fetchone()
        if not row:
            await update.message.reply_text("Please login before uploading files.")
            return
        owner_id = row[0]
        file_obj = update.message.document or (update.message.photo[-1] if update.message.photo else None) or update.message.video
        if not file_obj:
            await update.message.reply_text("Unsupported file type.")
            return
        file_id = file_obj.file_id
        file_type = (
            "document" if update.message.document
            else "photo" if update.message.photo
            else "video"
        )
        # Fix for photo file_name missing
        file_name = getattr(file_obj, "file_name", None) or "unknown"
        now = datetime.utcnow()
        delete_at = now + timedelta(minutes=AUTO_DELETE_MINUTES)
        c.execute(
            "INSERT INTO files (owner_id, file_id, file_type, file_name, uploaded_at, delete_at) VALUES (?, ?, ?, ?, ?, ?)",
            (owner_id, file_id, file_type, file_name, now.isoformat(), delete_at.isoformat())
        )
        file_db_id = c.lastrowid
        log_action(owner_id, "upload", f"Uploaded {file_type}: {file_name}")
        conn.commit()
        await update.message.reply_text(f"File {file_name} uploaded and scheduled for auto-deletion.")
        # Use create_task for background delete, avoid blocking
        asyncio.create_task(auto_delete_file(file_db_id, AUTO_DELETE_MINUTES * 60))
    except Exception as e:
        print("File upload error:", e)
    finally:
        conn.close()

async def main_async():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    await app.bot.delete_webhook(drop_pending_updates=True)
    # Add handlers only once
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("myfiles", myfiles))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, handle_file))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main_async())
