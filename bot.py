# Mega Telegram Cloud Storage Bot
# Python 3.10+, python-telegram-bot v20+
# Features: Mega user & admin features, upload/download, search, sharing, recommendations, delete all data

import sqlite3
import random
import string
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# ------------------------------
# CONFIGURATION
# ------------------------------
BOT_TOKEN = "7642147352:AAFhI8O8vpvSOovonO_A5UhTlTB4gpwFij4"
DEFAULT_LOGOUT_MINUTES = 30
ADMIN_IDS = [6065778458]  # Add your Telegram ID here

# ------------------------------
# DATABASE SETUP
# ------------------------------
conn = sqlite3.connect("mega_cloud.db")
cur = conn.cursor()

# Users table
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    password TEXT,
    is_admin INTEGER DEFAULT 0,
    logged_in INTEGER DEFAULT 0,
    last_active TIMESTAMP
)
""")

# Files table
cur.execute("""
CREATE TABLE IF NOT EXISTS files (
    file_id TEXT,
    user_id INTEGER,
    file_name TEXT,
    file_type TEXT,
    category TEXT,
    tags TEXT,
    upload_time TIMESTAMP,
    version INTEGER DEFAULT 1,
    is_deleted INTEGER DEFAULT 0,
    PRIMARY KEY(file_id, version)
)
""")

# Statistics table
cur.execute("""
CREATE TABLE IF NOT EXISTS stats (
    user_id INTEGER PRIMARY KEY,
    uploads INTEGER DEFAULT 0,
    downloads INTEGER DEFAULT 0
)
""")
conn.commit()

# ------------------------------
# UTILITIES
# ------------------------------
def generate_username():
    return "user" + ''.join(random.choices(string.digits, k=4))

def generate_password():
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choices(chars, k=8))

def update_last_active(user_id):
    cur.execute("UPDATE users SET last_active=? WHERE user_id=?", (datetime.now(), user_id))
    conn.commit()

def is_logged_out(user_id):
    cur.execute("SELECT last_active FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row and row[0]:
        last_active = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S.%f")
        return datetime.now() - last_active > timedelta(minutes=DEFAULT_LOGOUT_MINUTES)
    return True

# ------------------------------
# KEYBOARDS
# ------------------------------
user_menu = ReplyKeyboardMarkup([
    [KeyboardButton("📤 Upload File"), KeyboardButton("📁 My Files")],
    [KeyboardButton("🔍 Search File"), KeyboardButton("🕓 Recent Uploads")],
    [KeyboardButton("⭐ Favorites"), KeyboardButton("🚨 Delete All My Data"), KeyboardButton("🚪 Logout")]
], resize_keyboard=True)

admin_menu = ReplyKeyboardMarkup([
    [KeyboardButton("🛠 Admin Panel"), KeyboardButton("📊 Analytics")],
    [KeyboardButton("⚙️ Settings"), KeyboardButton("💾 Backup DB")]
], resize_keyboard=True)

# ------------------------------
# START & REGISTRATION
# ------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = cur.fetchone()

    if user and user[4]:  # logged_in
        update_last_active(user_id)
        menu = admin_menu if user_id in ADMIN_IDS else user_menu
        await update.message.reply_text(f"Welcome back, {user[1]}!", reply_markup=menu)
    else:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🆕 Generate Username & Password", callback_data="gen_creds")]])
        await update.message.reply_text("Welcome! Please create your credentials:", reply_markup=keyboard)

async def generate_credentials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    username = generate_username()
    password = generate_password()
    is_admin = 1 if user_id in ADMIN_IDS else 0

    try:
        cur.execute("INSERT INTO users (user_id, username, password, is_admin, logged_in, last_active) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, username, password, is_admin, 1, datetime.now()))
        cur.execute("INSERT OR IGNORE INTO stats (user_id, uploads, downloads) VALUES (?,0,0)", (user_id,))
        conn.commit()
        await query.edit_message_text(f"✅ Account created!\nUsername: {username}\nPassword: {password}")
        await query.message.reply_text("Main Menu:", reply_markup=admin_menu if is_admin else user_menu)
    except sqlite3.IntegrityError:
        await query.edit_message_text("Error creating account. Try /start again.")

# ------------------------------
# UPLOAD FILES
# ------------------------------
async def prompt_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📎 Send any file (photo, video, document, PDF, HTML)")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    update_last_active(user_id)

    file_id = None
    file_name = None
    file_type = "other"
    category = "Others"

    if update.message.document:
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name
        ext = file_name.split('.')[-1].lower()
        if ext in ["pdf"]:
            category = "PDFs"
        else:
            category = "Documents"
        file_type = "document"
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_name = f"photo_{datetime.now().timestamp()}.jpg"
        category = "Photos"
        file_type = "photo"
    elif update.message.video:
        file_id = update.message.video.file_id
        file_name = update.message.video.file_name or f"video_{datetime.now().timestamp()}.mp4"
        category = "Videos"
        file_type = "video"

    cur.execute("INSERT INTO files (file_id, user_id, file_name, file_type, category, tags, upload_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (file_id, user_id, file_name, file_type, category, "", datetime.now()))
    cur.execute("UPDATE stats SET uploads = uploads + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    await update.message.reply_text(f"✅ File saved: {file_name} ({category})")

# ------------------------------
# LIST USER FILES
# ------------------------------
async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cur.execute("SELECT file_id, file_name, category FROM files WHERE user_id=? AND is_deleted=0", (user_id,))
    files = cur.fetchall()
    if not files:
        await update.message.reply_text("📂 You have no uploaded files.")
        return
    for fid, name, cat in files:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("👁 View", callback_data=f"view_{fid}"),
                                    InlineKeyboardButton("🗑 Delete", callback_data=f"del_{fid}"),
                                    InlineKeyboardButton("⭐ Favorite", callback_data=f"fav_{fid}")]])
        await update.message.reply_text(f"{cat} - {name}", reply_markup=kb)

# ------------------------------
# FILE CALLBACK HANDLER
# ------------------------------
async def file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("view_"):
        fid = data.split("_")[1]
        cur.execute("SELECT file_id FROM files WHERE file_id=? AND is_deleted=0", (fid,))
        row = cur.fetchone()
        if row:
            await context.bot.send_document(user_id, row[0])
            cur.execute("UPDATE stats SET downloads = downloads +1 WHERE user_id=?", (user_id,))
            conn.commit()
    elif data.startswith("del_"):
        fid = data.split("_")[1]
        cur.execute("UPDATE files SET is_deleted=1 WHERE file_id=?", (fid,))
        conn.commit()
        await query.edit_message_text("🗑 File deleted successfully.")
    elif data.startswith("fav_"):
        await query.edit_message_text("⭐ File marked as favorite (placeholder)")

# ------------------------------
# USER DELETE ALL DATA
# ------------------------------
async def delete_all_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, Delete All", callback_data="confirm_del_all")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_del_all")]
    ])
    await update.message.reply_text("⚠ Are you sure you want to permanently delete ALL your files and account data?", reply_markup=keyboard)

async def confirm_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "confirm_del_all":
        # Delete all files
        cur.execute("UPDATE files SET is_deleted=1 WHERE user_id=?", (user_id,))
        # Delete user stats
        cur.execute("DELETE FROM stats WHERE user_id=?", (user_id,))
        # Delete user account
        cur.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        conn.commit()
        await query.edit_message_text("✅ All your files and account data have been deleted. Use /start to register again.")
    else:
        await query.edit_message_text("❌ Operation cancelled.")

# ------------------------------
# ADMIN PANEL (VIEW/DELETE FILES)
# ------------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not an admin!")
        return
    cur.execute("SELECT file_id, file_name, category, user_id, upload_time FROM files WHERE is_deleted=0")
    files = cur.fetchall()
    for fid, name, cat, uid, up_time in files:
        cur.execute("SELECT username FROM users WHERE user_id=?", (uid,))
        uname = cur.fetchone()[0] if cur.fetchone() else "Unknown"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("👁 View", callback_data=f"adm_view_{fid}"),
                                    InlineKeyboardButton("🗑 Delete", callback_data=f"adm_del_{fid}")]])
        await update.message.reply_text(f"📄 {name}\n👤 {uname}\n🕓 {up_time}\nCategory: {cat}", reply_markup=kb)

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("adm_view_"):
        fid = data.split("_")[2]
        cur.execute("
