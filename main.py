import datetime
import os
import pathlib
from calendar import day_name
from io import BytesIO

import pandas as pd
import telebot
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from constant import general, user
from repositories import models
from repositories.database import engine
from repositories.models import User, UserRole, UserType,VerificationStatus
from repositories.utils import get_db
from utils.dependency import Dependency, inject
from utils.jalali import Gregorian


@inject
def setup_payment_categories(db: Session=Dependency(get_db)):
    # Check if categories already exist
    existing_categories = db.query(models.PaymentCategory).all()
    if existing_categories:
        return
    # Create categories if they don't exist
    categories = {
        UserType.EMPLOYEE: 10,
        UserType.STUDENT: 8,
        UserType.GENERAL: 12,
    }
    for account_type, cost in categories.items():
        category = models.PaymentCategory(
            account_type=account_type, session_cost=cost
        )
        db.add(category)
    db.commit()

# Define time slots for the sessions


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
setup_payment_categories()

BASE_DIR = pathlib.Path(__file__).parent.absolute()
load_dotenv(BASE_DIR / ".env")

bot_token = os.getenv("BOT_TOKEN")
if not bot_token:
    raise ValueError("BOT_TOKEN not found in environment variables")

bot = telebot.TeleBot(bot_token)


user_onboarding_state = {}


@bot.message_handler(commands=["start"])
@inject
def start_handler(message: telebot.types.Message, db: Session = Dependency(get_db)):
    user_id = message.from_user.id
    user_db = db.query(User).filter_by(user_id=user_id).first()
    if user_db:
        if user_db.role == models.UserRole.ADMIN:
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("View Users", callback_data="admin_view_users"),
                InlineKeyboardButton("View Sessions", callback_data="admin_view_sessions"),
            )
            markup.add(
                InlineKeyboardButton(
                    "Disable/Enable Session", callback_data="admin_toggle_session"
                ),
                InlineKeyboardButton(
                    "Generate Excel Report", callback_data="admin_generate_report"
                ),
            )
            markup.add(
                InlineKeyboardButton(
                    "Generate Monthly Sessions", callback_data="admin_generate_sessions"
                )
            )
            bot.send_message(message.chat.id, "Admin Panel:", reply_markup=markup)
        elif user_db.role == models.UserRole.USER:
            keyboard = ReplyKeyboardMarkup(
                resize_keyboard=True,
                row_width=3,
            )
            buttons = (
                KeyboardButton(user.Buttons.SHOW_SESSIONS),
                KeyboardButton(user.Buttons.SHOW_PAYMENT_HISTORY),
                KeyboardButton(user.Buttons.SHOW_PROFILE),
            )
            for button in buttons:
                keyboard.add(button)
            bot.send_message(
                message.from_user.id,
                user.Messages.WELLCOME_BACK,
                reply_markup=keyboard,
            )
        return
    user_onboarding_state[user_id] = {}
    user_onboarding_state[user_id]['first_message']= message.message_id
    markup = InlineKeyboardMarkup()
    keys = (
        InlineKeyboardButton(
            user.Buttons.EMPLOYEE["TEXT"],
            callback_data=user.Buttons.EMPLOYEE["CALLBACK_DATA"],
        ),
        InlineKeyboardButton(
            user.Buttons.STUDENT["TEXT"],
            callback_data=user.Buttons.STUDENT["CALLBACK_DATA"],
        ),
        InlineKeyboardButton(
            user.Buttons.GENERAL["TEXT"],
            callback_data=user.Buttons.GENERAL["CALLBACK_DATA"],
        ),
    )
    for key in keys:
        markup.row(key)
    bot.send_message(
        message.chat.id, user.Messages.SELECT_ACCOUNT_TYPE, reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: True)
@inject
def callback_cneter(call, db: Session = Dependency(get_db)):
    if call.data.startswith("ACCOUNT_TYPE"):
        user_id = call.from_user.id
        if user_id not in user_onboarding_state:
            return
        user_type = call.data.replace("ACCOUNT_TYPE_", "")
        user_onboarding_state[user_id]["account_type"] = user_type
        match user_type:
            case "EMPLOYEE":
                msg = bot.reply_to(call.message, user.Messages.ENTER_PERSONNEL_NUMBER)
                bot.register_next_step_handler(msg, handle_veryfication_token)
            case "STUDENT":
                msg = bot.reply_to(call.message, user.Messages.ENTER_STUDENT_NUMBER)
                bot.register_next_step_handler(msg, handle_veryfication_token)
            case "GENERAL":
                user_onboarding_state[user_id]["veryfication_token"] = None
                msg = bot.reply_to(call.message, user.Messages.ENTER_YOUR_NAME)
                bot.register_next_step_handler(msg, handle_name)
            case _:
                raise ValueError("Invalid account type selected")

    # if call.data == "ADMIN_VIEW_USERS":
    #     users = db.query(User).all()
    #     msg = "*کاربران:*\n"
    #     for u in users:
    #         msg += f"{u.name} {u.surname} | {u.phone_number} | {u.user_type.value}\n"
    #     bot.send_message(call.message.chat.id, msg or "No users found.")

    # if call.data == "ADMIN_VIEW_SESSIONS":
    #     sessions = db.query(models.Session).all()
    #     msg = "*سانس های زمین*\n"
    #     for s in sessions:
    #         booked = f"رزور شده {s.booked_user_id}" if s.booked_user_id else "آزاد"
    #         msg += f"{s.session_date} {s.time_slot} — {booked}\n"
    #     bot.send_message(
    #         call.message.chat.id, msg or "سانس های زمین پیدا نشد."
    #     )
    # if call.data == "ADMIN_TOGGLE_SESSION":
    #     bot.send_message(
    #         call.message.chat.id,
    #         "Send the session ID to toggle availability (enable/disable):",
    #     )

def handle_veryfication_token(message):
    user_id = message.from_user.id
    user_onboarding_state[user_id]["veryfication_token"] = message.text.strip()
    msg = bot.reply_to(message, user.Messages.ENTER_YOUR_NAME)
    bot.register_next_step_handler(msg, handle_name)

def handle_name(message):
    user_id = message.from_user.id
    user_onboarding_state[user_id]["name"] = message.text.strip()
    msg = bot.reply_to(message, user.Messages.ENTER_YOUR_SURNAME)
    bot.register_next_step_handler(msg, handle_surname)


def handle_surname(message):
    user_id = message.from_user.id
    user_onboarding_state[user_id]["surname"] = message.text.strip()
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(
        KeyboardButton(user.Buttons.SHEAR, request_contact=True)
    )
    bot.send_message(
        message.from_user.id,
        user.Messages.SHEAR_YOUR_NUMBER,
        reply_markup=keyboard,
    )
    # bot.register_next_step_handler(msg, handle_phone_number)


@bot.message_handler(content_types=["contact"])
@inject
def handle_phone_number(message, db=Dependency(get_db)):
    user_id = message.from_user.id
    if user_id not in user_onboarding_state:
        return
    user_onboarding_state[user_id]["phone_number"] = message.contact.phone_number
    data = user_onboarding_state[user_id].copy()
    user_onboarding_state.pop(user_id, None)
    user_db = User(
        user_id=user_id,
        name=data["name"],
        surname=data["surname"],
        phone_number=data["phone_number"],
        account_type=UserType[data["account_type"]],
        veryfication_token=data["veryfication_token"],
        is_active = True,
        is_verified = VerificationStatus.VERIFIED if data["account_type"] == "GENERAL" else VerificationStatus.PENDING,
        
    )
    db.add(user_db)
    db.commit()
    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=3,
    )
    buttons = (
        KeyboardButton(user.Buttons.SHOW_SESSIONS),
        KeyboardButton(user.Buttons.SHOW_PAYMENT_HISTORY),
        KeyboardButton(user.Buttons.SHOW_PROFILE),
    )
    for button in buttons:
        keyboard.add(button)
    
    for i in range(data['first_message'],message.message_id+1):
        bot.delete_message(message.chat.id,i)
    bot.send_message(
        message.from_user.id,
        user.Messages.SUCCESSFUL_REGISTRATION,
        reply_markup=keyboard,
    )


# @bot.message_handler(commands=["sessions"])
# @inject
# def handle_sessions(message, db=Dependency(get_db)):
#     user_id = message.from_user.id
#     user = db.query(User).filter_by(user_id=user_id).first()
#     if not user:
#         bot.send_message(message.chat.id, "You need to register first. Use /start.")
#         return

#     today = datetime.date.today()
#     dates = [today + datetime.timedelta(days=i) for i in range(3)]
#     sessions = (
#         db.query(models.Session).filter(models.Session.session_date.in_(dates)).all()
#     )

#     is_admin_user = is_admin(message.from_user.id)
#     if not is_admin_user:
#         sessions = [s for s in sessions if s.available]

#     if not sessions:
#         bot.send_message(message.chat.id, "No sessions available for the next 3 days.")
#         return

#     sessions_by_date = {}
#     for s in sessions:
#         sessions_by_date.setdefault(s.session_date, []).append(s)

#     for date in dates:
#         day_sessions = sessions_by_date.get(date, [])
#         if not day_sessions:
#             continue

#         jalali_date = Gregorian(date).persian_string()
#         en_day = day_name[date.weekday()]
#         fa_day = PERSIAN_DAY_NAMES.get(en_day, en_day)
#         msg = f"*{fa_day}, {jalali_date}*\n"
#         markup = InlineKeyboardMarkup()
#         for s in day_sessions:
#             status = "Free" if s.available else "Booked"
#             if s.available:
#                 btn_text = f"{s.time_slot} — Book"
#                 markup.add(InlineKeyboardButton(btn_text, callback_data=f"book_{s.id}"))
#             else:
#                 btn_text = f"{s.time_slot} — Booked"
#                 markup.add(
#                     InlineKeyboardButton(
#                         btn_text, callback_data="unavailable", disabled=True
#                     )
#                 )
#             msg += f"🕒 {s.time_slot} — *{status}*\n"
#         bot.send_message(message.chat.id, msg, reply_markup=markup)


# @bot.callback_query_handler(func=lambda call: call.data.startswith("book_"))
# @inject
# def handle_book_session(call, db=Dependency(get_db)):
#     user_id = call.from_user.id
#     session_id = int(call.data.replace("book_", ""))
#     session = db.query(models.Session).filter_by(id=session_id, available=True).first()
#     if not session:
#         bot.answer_callback_query(
#             call.id, "This session is no longer available.", show_alert=True
#         )
#         return
#     # Show cost and ask for confirmation
#     user = db.query(User).filter_by(user_id=user_id).first()
#     cost = session.cost
#     markup = InlineKeyboardMarkup()
#     markup.add(
#         InlineKeyboardButton(
#             f"Confirm Booking (${cost})", callback_data=f"confirm_{session_id}"
#         )
#     )
#     bot.edit_message_text(
#         f"Session: {session.session_date} {session.time_slot}\nCost: ${cost}\nDo you want to book this session?",
#         chat_id=call.message.chat.id,
#         message_id=call.message.message_id,
#         reply_markup=markup,
#     )
#     bot.answer_callback_query(call.id)


# from sqlalchemy.exc import IntegrityError


# @bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_"))
# @inject
# def handle_confirm_booking(call, db=Dependency(get_db)):
#     try:
#         user_id = call.from_user.id
#         session_id = int(call.data.replace("confirm_", ""))
#         session = (
#             db.query(models.Session).filter_by(id=session_id, available=True).first()
#         )
#         if not session:
#             bot.answer_callback_query(
#                 call.id, "This session is no longer available.", show_alert=True
#             )
#             return
#         # Create payment record
#         payment = models.Payment(
#             user_id=user_id,
#             session_id=session_id,
#             amount=session.cost,
#             payment_date=datetime.datetime.now(),
#         )
#         db.add(payment)
#         session.available = False
#         session.booked_user_id = user_id
#         db.commit()
#     except IntegrityError:
#         db.rollback()
#         bot.answer_callback_query(
#             call.id,
#             "Session was booked by someone else. Please try another session.",
#             show_alert=True,
#         )
#         return
#     bot.edit_message_text(
#         f"✅ Session booked successfully!\nSession: {session.session_date} {session.time_slot}",
#         chat_id=call.message.chat.id,
#         message_id=call.message.message_id,
#     )
#     bot.answer_callback_query(call.id, "Session booked!")


# ADMIN_user_id = 1697165816  # <-- Replace with your admin Telegram ID




# @bot.message_handler(func=lambda message: True)
# @inject
# def admin_toggle_session_action(message, db=Dependency(get_db)):
#     session_id = int(message.text)
#     session = db.query(models.Session).filter_by(id=session_id).first()
#     if not session:
#         bot.send_message(message.chat.id, "Session not found.")
#         return
#     session.available = not session.available
#     db.commit()
#     status = "enabled" if session.available else "disabled"
#     bot.send_message(message.chat.id, f"Session {session_id} is now {status}.")


# @bot.callback_query_handler(func=lambda call: call.data == "admin_generate_report")
# @inject
# def admin_generate_report(call, db=Dependency(get_db)):
#     # Users DataFrame
#     users = db.query(User).all()
#     users_data = [
#         {
#             "Telegram ID": u.user_id,
#             "Name": u.name,
#             "Surname": u.surname,
#             "Phone": u.phone_number,
#             "User Type": u.user_type.value,
#         }
#         for u in users
#     ]
#     df_users = pd.DataFrame(users_data)

#     # Payments DataFrame
#     payments = db.query(models.Payment).all()
#     payments_data = []
#     for p in payments:
#         session = db.query(models.Session).filter_by(id=p.session_id).first()
#         payments_data.append(
#             {
#                 "User ID": p.user_id,
#                 "Session ID": p.session_id,
#                 "Session Date": session.session_date if session else "",
#                 "Time Slot": session.time_slot if session else "",
#                 "Amount": p.amount,
#                 "Payment Date": p.payment_date,
#             }
#         )
#     df_payments = pd.DataFrame(payments_data)

#     # Write to Excel in memory
#     output = BytesIO()
#     with pd.ExcelWriter(output, engine="openpyxl") as writer:
#         df_users.to_excel(writer, sheet_name="Users", index=False)
#         df_payments.to_excel(writer, sheet_name="Payments", index=False)
#     output.seek(0)
#     bot.send_document(call.message.chat.id, output, visible_file_name="report.xlsx")
#     bot.answer_callback_query(call.id, "Report generated.")


# @bot.callback_query_handler(func=lambda call: call.data == "admin_generate_sessions")
# @inject
# def admin_generate_sessions(call, db=Dependency(get_db)):
#     if call.from_user.id != ADMIN_user_id:
#         bot.answer_callback_query(call.id, "Unauthorized action", show_alert=True)
#         return

#     # Get the first day of next month
#     today = datetime.date.today()
#     if today.month == 12:
#         next_month = datetime.date(today.year + 1, 1, 1)
#     else:
#         next_month = datetime.date(today.year, today.month + 1, 1)

#     # Generate sessions for the entire month
#     sessions_created = 0
#     current_date = next_month

#     while current_date.month == next_month.month:
#         # Skip Fridays (assuming Friday is the weekend)
#         if current_date.weekday() != 4:  # Friday is 4 in Python's weekday system
#             # Generate 5 sessions per day
#             # Add at the top with other constants
#             PRICING = {"employee": 10, "student": 8, "other": 12}

#             # In admin_generate_sessions function
#             for time_slot in time_slots:
#                 base_cost = 10  # Base cost for others
#                 session = models.Session(
#                     session_date=current_date,
#                     time_slot=time_slot,
#                     available=True,
#                     cost=base_cost,
#                 )
#                 db.add(session)
#                 sessions_created += 1
#         current_date += datetime.timedelta(days=1)

#     db.commit()
#     bot.answer_callback_query(
#         call.id,
#         f"Created {sessions_created} free sessions for next month!",
#         show_alert=True,
#     )
#     bot.edit_message_text(
#         f"✅ Successfully generated {sessions_created} free sessions for {next_month.strftime('%B %Y')}",
#         chat_id=call.message.chat.id,
#         message_id=call.message.message_id,
#     )


bot.infinity_polling()
