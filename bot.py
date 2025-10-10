import os
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
from dotenv import load_dotenv
import os

load_dotenv()  # loads .env file
BOT_TOKEN = os.environ.get("7642147352:AAFhI8O8vpvSOovonO_A5UhTlTB4gpwFij4")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing! Please set it in .env or environment variables")
# ===== CONFIG =====
ADMIN_IDS = [7642147352]  # Replace with your Telegram ID(s)
DATABASE = "mega_cloud.db"
BOT_TOKEN = os.environ.get("7642147352:AAFhI8O8vpvSOovonO_A5UhTlTB4gpwFij4")  # Set in environment or .env
MAX_LOGIN_ATTEMPTS = 3
AUTO_DELETE_MINUTES = 30

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

# ===== MAIN FUNCTION =====
def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("myfiles", myfiles))

    # Messages
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, handle_file))

    # Callback buttons
    application.add_handler(CallbackQueryHandler(button_callback))

    # Run bot
    application.run_polling()

if __name__ == "__main__":
    main()


