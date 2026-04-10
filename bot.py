import io
import csv
import sqlite3
import os
from datetime import datetime
from dotenv import load_dotenv
from init_db import init_db

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# =========================
# Setup & Config
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@BestITM")
DATABASE_PATH = os.getenv("DATABASE_PATH", "database.db")

# =========================
# Database Helpers
# =========================
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_setting(key, default=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    return "".join(ch for ch in phone if ch.isdigit())

# =========================
# Checks
# =========================
async def is_subscribed(bot, user_id: int) -> bool:
    try:
        chat_member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

def is_registration_open():
    # Check manual toggle
    if get_setting('is_registration_open') == '0':
        return False, "Kechirasiz, ro'yxatdan o'tish yopilgan. ❌"

    # Check capacity
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM registrations")
    count = cur.fetchone()[0]
    conn.close()
    
    max_capacity = int(get_setting('capacity', '100'))
    if count >= max_capacity:
        return False, "Kechirasiz, barcha joylar to'ldi. 🏟"

    # Check deadline
    deadline_str = get_setting('deadline')
    if deadline_str:
        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
            if datetime.now() > deadline:
                return False, f"Kechirasiz, ro'yxatdan o'tish muddati tugagan ({deadline_str}). ⏰"
        except ValueError:
            pass
            
    return True, ""

# =========================
# /start
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id
    username = user.username or ""

    # Track user
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

    if not await is_subscribed(context.bot, user_id):
        keyboard = [
            [InlineKeyboardButton("🔔 Kanalga obuna bo‘lish", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
            [InlineKeyboardButton("✅ Obuna bo‘ldim", callback_data="check_subscription")],
        ]
        await update.message.reply_text(
            "Botdan foydalanish uchun kanalga obuna bo‘lishingiz kerak! 👇",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    exam_info = get_setting('exam_info')
    await update.message.reply_text(exam_info)

    open_status, msg = is_registration_open()
    if not open_status:
        await update.message.reply_text(msg)
        return

    reply_keyboard = [["Ona tili mock imtihoni"]]
    context.user_data.clear()
    await update.message.reply_text(
        "Ro‘yxatdan o‘tish uchun tugmani bosing:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
    )

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if await is_subscribed(context.bot, user_id):
        await query.message.delete()
        exam_info = get_setting('exam_info')
        await query.message.reply_text(exam_info)
        
        open_status, msg = is_registration_open()
        if not open_status:
            await query.message.reply_text(msg)
            return

        reply_keyboard = [["Ona tili mock imtihoni"]]
        await query.message.reply_text(
            "Ro‘yxatdan o‘tish uchun tugmani bosing:",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
        )
    else:
        await query.answer("Siz hali ham kanalga obuna bo‘lmagansiz! 🔔", show_alert=True)

# =========================
# Registration Flow
# =========================
async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "Ona tili mock imtihoni":
        open_status, msg = is_registration_open()
        if not open_status:
            await update.message.reply_text(msg)
            return
            
        context.user_data["step"] = "full_name"
        await update.message.reply_text("Iltimos, to'liq ismingizni kiriting (F.I.O):")
    else:
        await update.message.reply_text("Iltimos, berilgan tugmadan foydalaning.")

async def handle_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["full_name"] = update.message.text.strip()
    context.user_data["step"] = "phone_number"
    
    phone_button = ReplyKeyboardMarkup(
        [[KeyboardButton("📞 Telefon raqamni yuborish", request_contact=True)]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    await update.message.reply_text("Endi telefon raqamingizni yuboring:", reply_markup=phone_button)

async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact:
        await update.message.reply_text("Iltimos, pastdagi tugma orqali telefon raqamingizni yuboring.")
        return

    full_name = context.user_data.get("full_name")
    phone_raw = contact.phone_number
    phone_norm = normalize_phone(phone_raw)
    username = update.message.from_user.username or ""

    if not full_name:
        await update.message.reply_text("Xatolik yuz berdi. Iltimos, /start dan qayta boshlang.")
        return

    # Check duplicate
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM registrations WHERE phone = ?", (phone_raw,))
    if cur.fetchone():
        await update.message.reply_text("Siz allaqachon ro‘yxatdan o‘tgansiz! 😊")
        conn.close()
        context.user_data.clear()
        return

    # Check capacity again right before save
    open_status, msg = is_registration_open()
    if not open_status:
        await update.message.reply_text(msg)
        conn.close()
        return

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO registrations (full_name, phone, exam_date, username, created_at) VALUES (?, ?, ?, ?, ?)",
        (full_name, phone_raw, "Ona tili mock (Smena 1)", username, created_at)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text("Tabriklaymiz! Siz Ona tili mock imtihoniga muvaffaqiyatli ro‘yxatdan o‘tdingiz! ✅")
    context.user_data.clear()

# =========================
# Admin Panel
# =========================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return

    keyboard = [
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("⏰ Muddatni belgilash", callback_data="set_deadline")],
        [InlineKeyboardButton("🏟 Sig'imni belgilash", callback_data="set_capacity")],
        [InlineKeyboardButton("📢 Reklama", callback_data="send_ad")],
        [InlineKeyboardButton("📂 Eksport (CSV)", callback_data="admin_export")],
    ]
    await update.message.reply_text("Admin panel:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        return

    data = query.data
    if data == "admin_stats":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM registrations")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users")
        u_total = cur.fetchone()[0]
        conn.close()
        
        deadline = get_setting('deadline', 'Belgilanmagan')
        cap = get_setting('capacity', '100')
        
        msg = f"📊 Statistika:\n• Ro'yxatdan o'tganlar: {total}\n• Bot a'zolari: {u_total}\n• Sig'im: {cap}\n• Deadline: {deadline}"
        await query.message.reply_text(msg)

    elif data == "set_deadline":
        context.user_data["step"] = "admin_set_deadline"
        await query.message.reply_text("Yangi deadline kiriting (Format: YYYY-MM-DD HH:MM):\nMasalan: 2026-05-15 18:00")

    elif data == "set_capacity":
        context.user_data["step"] = "admin_set_capacity"
        await query.message.reply_text("Maksimal sig'imni kiriting (son):")

    elif data == "send_ad":
        context.user_data["step"] = "admin_send_ad"
        await query.message.reply_text("Reklama xabarini yuboring:")

    elif data == "admin_export":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM registrations")
        rows = cur.fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "FIO", "Phone", "Exam", "Username", "Time"])
        writer.writerows(rows)
        output.seek(0)

        bio = io.BytesIO(output.getvalue().encode("utf-8"))
        bio.name = "registrations.csv"
        await context.bot.send_document(chat_id=query.from_user.id, document=bio)

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")
    text = update.message.text.strip()
    
    if step == "admin_set_deadline":
        try:
            datetime.strptime(text, "%Y-%m-%d %H:%M")
            set_setting('deadline', text)
            await update.message.reply_text(f"Deadline muvaffaqiyatli o'rnatildi: {text} ✅")
        except ValueError:
            await update.message.reply_text("Noto'g'ri format. Iltimos, qaytadan kiriting (YYYY-MM-DD HH:MM):")
            return

    elif step == "admin_set_capacity":
        if text.isdigit():
            set_setting('capacity', text)
            await update.message.reply_text(f"Maksimal sig'im o'rnatildi: {text} ✅")
        else:
            await update.message.reply_text("Iltimos, faqat son kiriting:")
            return

    elif step == "admin_send_ad":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        users = cur.fetchall()
        conn.close()
        
        count = 0
        for u in users:
            try:
                await context.bot.send_message(u['user_id'], text)
                count += 1
            except Exception:
                pass
        await update.message.reply_text(f"Reklama {count} kishiga yuborildi. ✅")

    context.user_data.clear()

# =========================
# Main Router
# =========================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")
    text = update.message.text
    
    if step is None:
        if text == "Ona tili mock imtihoni":
            await handle_choice(update, context)
        return

    if step == "full_name":
        await handle_full_name(update, context)
    elif step.startswith("admin_"):
        await handle_admin_input(update, context)

def main():
    if not BOT_TOKEN:
        print("Xatolik: BOT_TOKEN topilmadi!")
        return

    # Initialize database
    init_db()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    
    app.add_handler(CallbackQueryHandler(check_subscription, pattern="check_subscription"))
    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_|^set_"))
    
    app.add_handler(MessageHandler(filters.CONTACT, handle_phone_number))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
