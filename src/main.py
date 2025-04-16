#!/usr/bin/python

# This is a simple echo bot using the decorator mechanism.
# It echoes any incoming text messages.
import os
import pathlib

import telebot
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# from src.utils import jalali
from src.repositories.models import User, UserType
from src.utils.jalali import Gregorian
import datetime as dt

from src.utils.dependency import Dependency, inject
# from repositories.utils import get_db
from .repositories.database import engine
from .repositories import models
# from .repositories.utils import get_db
# from .utils.dependency import Dependency, inject

import logging
import logging.config
import toml  # or import tomli as toml for Python < 3.11
import os
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from src.repositories.database import SessionLocal
import pandas as pd
from io import BytesIO

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# def setup_logging(stage="development"):
#     # Ensure logs directory exists
#     os.makedirs("logs", exist_ok=True)
    
#     # Load TOML config
#     with open("logging.toml", "r") as f:
#         config = toml.load(f)
    
#     # Apply logging configuration
#     logging.config.dictConfig(config)
    
#     # Select logger based on stage
#     logger_name = "myapp.dev" if stage == "development" else "myapp.prod"
#     return logging.getLogger(logger_name)
# logger = setup_logging(stage="development")

PERSIAN_DAY_NAMES = {
    "Monday": "دوشنبه",
    "Tuesday": "سه‌شنبه",
    "Wednesday": "چهارشنبه",
    "Thursday": "پنج‌شنبه",
    "Friday": "جمعه",
    "Saturday": "شنبه",
    "Sunday": "یکشنبه",
}
models.Base.metadata.create_all(bind=engine)


BASE_DIR = pathlib.Path(__file__).parent.absolute()
load_dotenv(BASE_DIR / ".env")

bot_token = os.getenv("BOT_TOKEN")
if not bot_token:
    raise ValueError("BOT_TOKEN not found in environment variables")

bot = telebot.TeleBot(bot_token)


user_onboarding_state = {}

@bot.message_handler(commands=['start'])
@inject
def start_handler(message:telebot.types.Message, db:Session=Dependency(get_db)):
    telegram_id = message.from_user.id
    user = db.query(User).filter_by(telegram_id=telegram_id).first()
    if user:
        bot.send_message(message.from_user.id, "You are already registered.")
        return
    user_onboarding_state[telegram_id] = {}
    markup = InlineKeyboardMarkup()
    keys=(
        InlineKeyboardButton("University Employee", callback_data="user_type_employee"),
        InlineKeyboardButton("University Student", callback_data="user_type_student"),
        InlineKeyboardButton("Other", callback_data="user_type_other")
    )
    for key in keys:
        markup.add(key)
    bot.send_message(message.chat.id, "Welcome! Please select your user type:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
@inject
def callback_cneter(call, db: Session = Dependency(get_db)):
    if call.data.startswith("user_type_"):
        telegram_id = call.from_user.id
        if telegram_id not in user_onboarding_state:
            return
        user_type = call.data.replace("user_type_", "")
        user_onboarding_state[telegram_id]['user_type'] = user_type
        msg = bot.reply_to(call.message, "Please enter your name:")
        bot.register_next_step_handler(msg, handle_name)

def handle_name(message):
    telegram_id = message.from_user.id
    user_onboarding_state[telegram_id]['name'] = message.text.strip()
    msg = bot.reply_to(message, "Please enter your surname:")
    bot.register_next_step_handler(msg,handle_surname)

def handle_surname(message):
    telegram_id = message.from_user.id
    user_onboarding_state[telegram_id]['surname'] = message.text.strip()
    markup = InlineKeyboardMarkup()
    button = InlineKeyboardButton("Share phone number", request_contact=True)
    markup.add(button)
    bot.send_message(message.from_user.id, "Please share your phone number:", reply_markup=markup)

@bot.message_handler(content_types=['contact'])
@inject
def handle_contact(message, db=Dependency(get_db)):
    telegram_id = message.from_user.id
    if telegram_id not in user_onboarding_state:
        return
    user_onboarding_state[telegram_id]['phone_number'] = message.contact.phone_number
    data = user_onboarding_state[telegram_id]
    user = User(
        telegram_id=telegram_id,
        name=data['name'],
        surname=data['surname'],
        phone_number=data['phone_number'],
        user_type=UserType[data['user_type']]
    )
    db.add(user)
    db.commit()
    bot.send_message(message.from_user.id, "Registration complete! You can now use the bot.", reply_markup=telebot.types.ReplyKeyboardRemove())
    user_onboarding_state.pop(telegram_id, None)

import datetime
from calendar import day_name


@bot.message_handler(commands=['sessions'])
@inject
def handle_sessions(message, db=Dependency(get_db)):
    telegram_id = message.from_user.id
    user = db.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        bot.send_message(message.chat.id, "You need to register first. Use /start.")
        return

    today = datetime.date.today()
    dates = [today + datetime.timedelta(days=i) for i in range(3)]
    sessions = db.query(models.Session).filter(models.Session.session_date.in_(dates)).all()

    is_admin = False  # Set your admin check here
    if not is_admin:
        sessions = [s for s in sessions if s.available]

    if not sessions:
        bot.send_message(message.chat.id, "No sessions available for the next 3 days.")
        return

    sessions_by_date = {}
    for s in sessions:
        sessions_by_date.setdefault(s.session_date, []).append(s)

    for date in dates:
        day_sessions = sessions_by_date.get(date, [])
        if not day_sessions:
            continue

        jalali_date = Gregorian(date).persian_string()
        en_day = day_name[date.weekday()]
        fa_day = PERSIAN_DAY_NAMES.get(en_day, en_day)
        msg = f"<b>{fa_day}, {jalali_date}</b>\n"
        markup = InlineKeyboardMarkup()
        for s in day_sessions:
            status = "Free" if s.available else "Booked"
            if s.available:
                btn_text = f"{s.time_slot} — Book"
                markup.add(InlineKeyboardButton(btn_text, callback_data=f"book_{s.id}"))
            else:
                btn_text = f"{s.time_slot} — Booked"
                markup.add(InlineKeyboardButton(btn_text, callback_data="unavailable", disabled=True))
            msg += f"🕒 {s.time_slot} — <b>{status}</b>\n"
        bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("book_"))
@inject
def handle_book_session(call, db=Dependency(get_db)):
    telegram_id = call.from_user.id
    session_id = int(call.data.replace("book_", ""))
    session = db.query(models.Session).filter_by(id=session_id, available=True).first()
    if not session:
        bot.answer_callback_query(call.id, "This session is no longer available.", show_alert=True)
        return
    # Show cost and ask for confirmation
    user = db.query(User).filter_by(telegram_id=telegram_id).first()
    cost = session.cost
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"Confirm Booking (${cost})", callback_data=f"confirm_{session_id}"))
    bot.edit_message_text(
        f"Session: {session.session_date} {session.time_slot}\nCost: ${cost}\nDo you want to book this session?",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_"))
@inject
def handle_confirm_booking(call, db=Dependency(get_db)):
    telegram_id = call.from_user.id
    session_id = int(call.data.replace("confirm_", ""))
    session = db.query(models.Session).filter_by(id=session_id, available=True).first()
    if not session:
        bot.answer_callback_query(call.id, "This session is no longer available.", show_alert=True)
        return
    # Simulate payment and book session
    session.available = False
    session.booked_user_id = telegram_id
    db.commit()
    bot.edit_message_text(
        f"✅ Session booked successfully!\nSession: {session.session_date} {session.time_slot}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.answer_callback_query(call.id, "Session booked!")

# ...existing code...


ADMIN_TELEGRAM_ID = 123456789  # <-- Replace with your admin Telegram ID

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_TELEGRAM_ID:
        bot.send_message(message.chat.id, "You are not authorized to use admin commands.")
        return
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("View Users", callback_data="admin_view_users"),
        InlineKeyboardButton("View Sessions", callback_data="admin_view_sessions"),
    )
    markup.add(
        InlineKeyboardButton("Disable/Enable Session", callback_data="admin_toggle_session"),
        InlineKeyboardButton("Generate Excel Report", callback_data="admin_generate_report"),
    )
    bot.send_message(message.chat.id, "Admin Panel:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_view_users")
@inject
def admin_view_users(call, db=Dependency(get_db)):
    users = db.query(User).all()
    msg = "<b>Users:</b>\n"
    for u in users:
        msg += f"{u.name} {u.surname} | {u.phone_number} | {u.user_type.value}\n"
    bot.send_message(call.message.chat.id, msg or "No users found.", parse_mode="HTML")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_view_sessions")
@inject
def admin_view_sessions(call, db=Dependency(get_db)):
    sessions = db.query(models.Session).all()
    msg = "<b>Sessions:</b>\n"
    for s in sessions:
        booked = f"Booked by {s.booked_user_id}" if s.booked_user_id else "Free"
        msg += f"{s.session_date} {s.time_slot} — {booked}\n"
    bot.send_message(call.message.chat.id, msg or "No sessions found.", parse_mode="HTML")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_toggle_session")
def admin_toggle_session_prompt(call):
    bot.send_message(call.message.chat.id, "Send the session ID to toggle availability (enable/disable):")
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_TELEGRAM_ID and m.text and m.text.isdigit())
@inject
def admin_toggle_session_action(message, db=Dependency(get_db)):
    session_id = int(message.text)
    session = db.query(models.Session).filter_by(id=session_id).first()
    if not session:
        bot.send_message(message.chat.id, "Session not found.")
        return
    session.available = not session.available
    db.commit()
    status = "enabled" if session.available else "disabled"
    bot.send_message(message.chat.id, f"Session {session_id} is now {status}.")

@bot.callback_query_handler(func=lambda call: call.data == "admin_generate_report")
@inject
def admin_generate_report(call, db=Dependency(get_db)):
    # Users DataFrame
    users = db.query(User).all()
    users_data = [{
        "Telegram ID": u.telegram_id,
        "Name": u.name,
        "Surname": u.surname,
        "Phone": u.phone_number,
        "User Type": u.user_type.value
    } for u in users]
    df_users = pd.DataFrame(users_data)

    # Payments DataFrame
    payments = db.query(models.Payment).all()
    payments_data = []
    for p in payments:
        session = db.query(models.Session).filter_by(id=p.session_id).first()
        payments_data.append({
            "User ID": p.user_id,
            "Session ID": p.session_id,
            "Session Date": session.session_date if session else "",
            "Time Slot": session.time_slot if session else "",
            "Amount": p.amount,
            "Payment Date": p.payment_date~
        })
    df_payments = pd.DataFrame(payments_data)

    # Write to Excel in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_users.to_excel(writer, sheet_name='Users', index=False)
        df_payments.to_excel(writer, sheet_name='Payments', index=False)
    output.seek(0)
    bot.send_document(call.message.chat.id, output, visible_file_name="report.xlsx")
    bot.answer_callback_query(call.id, "Report generated.")


def main():
    bot.infinity_polling()