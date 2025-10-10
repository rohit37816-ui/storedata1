import os
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters

# ===== CONFIG =====
ADMIN_IDS = [6065778458]  # Replace with your Telegram ID(s)
DATABASE = "mega_cloud.db"
MAX_LOGIN_ATTEMPTS = 3
AUTO_DELETE_MINUTES = 30

# ===== BOT TOKEN from Render Environment Variable =====
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
async def auto_delete_file(file_id, delay=AUTO_DELETE_MINUTES*60):
    await asyncio.sleep(delay)
    cur.execute("UPDATE files SET is_deleted=1 WHERE file_id=?", (file_id,))
    conn.commit()

async def log_action(user_id, action):
    cur.execute("INSERT INTO logs (user_id, action) VALUES (?, ?)", (user_id, action))
    conn.commit()

def check_admin(user_id):
    return user_id in ADMIN_IDS

# ===== COMMANDS =====
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

# ===== CALLBACK HANDLER =====
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    await query.edit_message_text(f"Button clicked: {data}")

# ===== MESSAGE HANDLERS =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    await update.message.reply_text(f"Received text: {text}")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    file_obj = None
    file_type = None

    if update.message.document:
        file_obj = update.message.document
        file_type = "document"
    elif update.message.photo:
        file_obj = update.message.photo[-1]
        file_type = "photo"
    elif update.message.video:
        file_obj = update.message.video
        file_type = "video"
    else:
        await update.message.reply_text("❌ Unsupported file type.")
        return

    file_id_db = file_obj.file_id
    file_name = getattr(file_obj, 'file_name', 'unknown')
    tag = getattr(file_obj, 'mime_type', 'general')
    cur.execute("INSERT OR REPLACE INTO files (file_id, user_id, file_name, file_type, tag) VALUES (?, ?, ?, ?, ?)",
                (file_id_db, user_id, file_name, file_type, tag))
    conn.commit()

    await update.message.reply_text(f"✅ File uploaded successfully! Auto-delete in {AUTO_DELETE_MINUTES} minutes.")
    await log_action(user_id, f"Uploaded file: {file_name}")
    asyncio.create_task(auto_delete_file(file_id_db))

# ===== ASYNC MAIN FUNCTION =====
async def main_async():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Delete the webhook to prevent conflicts with polling
    await application.bot.delete_webhook()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("myfiles", myfiles))

    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, handle_file))

    application.add_handler(CallbackQueryHandler(button_callback))

    # Run bot with polling
    await application.run_polling()

if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_async())cur.execute('''CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()

# ===== HELPERS =====
async def auto_delete_file(file_id, delay=AUTO_DELETE_MINUTES*60):
    await asyncio.sleep(delay)
    cur.execute("UPDATE files SET is_deleted=1 WHERE file_id=?", (file_id,))
    conn.commit()

async def log_action(user_id, action):
    cur.execute("INSERT INTO logs (user_id, action) VALUES (?, ?)", (user_id, action))
    conn.commit()

def check_admin(user_id):
    return user_id in ADMIN_IDS

# ===== COMMANDS =====
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

# ===== CALLBACK HANDLER =====
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    # Placeholder for all callback handling
    await query.edit_message_text(f"Button clicked: {data}")

# ===== MESSAGE HANDLERS =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    await update.message.reply_text(f"Received text: {text}")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    file_obj = None
    file_type = None

    if update.message.document:
        file_obj = update.message.document
        file_type = "document"
    elif update.message.photo:
        file_obj = update.message.photo[-1]
        file_type = "photo"
    elif update.message.video:
        file_obj = update.message.video
        file_type = "video"
    else:
        await update.message.reply_text("❌ Unsupported file type.")
        return

    file_id_db = file_obj.file_id
    file_name = getattr(file_obj, 'file_name', 'unknown')
    tag = getattr(file_obj, 'mime_type', 'general')
    cur.execute("INSERT OR REPLACE INTO files (file_id, user_id, file_name, file_type, tag) VALUES (?, ?, ?, ?, ?)",
                (file_id_db, user_id, file_name, file_type, tag))
    conn.commit()

    await update.message.reply_text(f"✅ File uploaded successfully! Auto-delete in {AUTO_DELETE_MINUTES} minutes.")
    await log_action(user_id, f"Uploaded file: {file_name}")
    asyncio.create_task(auto_delete_file(file_id_db))

# ===== ASYNC MAIN FUNCTION =====
import asyncio 

async def main_async():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # delete webhook to avoid conflicts
    await application.bot.delete_webhook()

    # add handlers ...
    application.add_handler(CommandHandler("start", start))
    # add other handlers

    await application.run_polling()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main_async())
    # Adding handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("myfiles", myfiles))

    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, handle_file))

    application.add_handler(CallbackQueryHandler(button_callback))

    # Start the bot with polling
    import asyncio

async def main_async():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    await application.bot.delete_webhook()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    # Add other handlers...

    await application.run_polling()

import asyncio

if __name__ == "__main__":
    loop = asyncio.get_event_loop()  # Get or create the event loop
    loop.run_until_complete(main_async())  # Run the async main function until complete

