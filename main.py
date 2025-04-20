import datetime
import os
import pathlib
from calendar import day_name
from io import BytesIO
import threading

import pandas as pd
import telebot
import re
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from constant import user as CUSER
from repositories import models
from repositories.database import engine
from repositories.models import User, UserType, VerificationStatus
from repositories.utils import get_db
from utils.dependency import Dependency, inject
from utils.jalali import Gregorian


def convert_persian_numbers(input_text):
    persian_to_english = {
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }

    cleaned = input_text
    for persian, english in persian_to_english.items():
        cleaned = cleaned.replace(persian, english)
    return cleaned


@inject
def setup_payment_categories(db: Session = Dependency(get_db)):
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
        category = models.PaymentCategory(account_type=account_type, session_cost=cost)
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
TIMESLOTS = [
    "15:00-16:30",
    "16:30-18:00",
    "18:00-19:30",
    "19:30-21:00",
    "21:00-22:30",
]
models.Base.metadata.create_all(bind=engine)
setup_payment_categories()

BASE_DIR = pathlib.Path(__file__).parent.absolute()
load_dotenv(BASE_DIR / ".env")

bot_token = os.getenv("BOT_TOKEN")
if not bot_token:
    raise ValueError("BOT_TOKEN not found in environment variables")

bot = telebot.TeleBot(bot_token)

user_boarding = {}


@bot.message_handler(commands=["start"])
@inject
def start_handler(message: telebot.types.Message, db: Session = Dependency(get_db)):
    user_id = message.from_user.id
    user_db = db.query(User).filter_by(user_id=user_id).first()
    if user_db:
        if user_db.role == models.UserRole.ADMIN:
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("View Users", callback_data="ADMIN_VIEW_USERS"),
                InlineKeyboardButton(
                    "View Sessions", callback_data="ADMIN_VIEW_SESSIONS"
                ),
            )
            markup.add(
                InlineKeyboardButton(
                    "Disable/Enable Session", callback_data="ADMIN_TOGGLE_SESSION"
                ),
                InlineKeyboardButton(
                    "Generate Excel Report", callback_data="ADMIN_GENERATE_REPORT"
                ),
            )
            markup.add(
                InlineKeyboardButton(
                    "Generate Monthly Sessions", callback_data="ADMIN_GENERATE_SESSIONS"
                )
            )
            bot.send_message(message.chat.id, "Admin Panel:", reply_markup=markup)
        elif user_db.role == models.UserRole.USER:
            keyboard = ReplyKeyboardMarkup(
                resize_keyboard=True,
                row_width=3,
            )
            buttons = (
                KeyboardButton(CUSER.Buttons.SHOW_SESSIONS),
                KeyboardButton(CUSER.Buttons.SHOW_PAYMENT_HISTORY),
                KeyboardButton(CUSER.Buttons.SHOW_PROFILE),
            )
            for button in buttons:
                keyboard.add(button)
            bot.send_message(
                message.from_user.id,
                CUSER.Messages.WELLCOME_BACK,
                reply_markup=keyboard,
            )
        return
    markup = InlineKeyboardMarkup()
    keys = (
        InlineKeyboardButton(
            CUSER.Buttons.EMPLOYEE["TEXT"],
            callback_data=CUSER.Buttons.EMPLOYEE["CALLBACK_DATA"],
        ),
        InlineKeyboardButton(
            CUSER.Buttons.STUDENT["TEXT"],
            callback_data=CUSER.Buttons.STUDENT["CALLBACK_DATA"],
        ),
        InlineKeyboardButton(
            CUSER.Buttons.GENERAL["TEXT"],
            callback_data=CUSER.Buttons.GENERAL["CALLBACK_DATA"],
        ),
    )
    user_boarding[user_id] = {
        "first_message": message.message_id,
    }
    for key in keys:
        markup.row(key)
    bot.send_message(
        message.chat.id, CUSER.Messages.SELECT_ACCOUNT_TYPE, reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: True)
@inject
def callback_cneter(call, db: Session = Dependency(get_db)):
    if call.data.startswith("ACCOUNT_TYPE"):
        user_id = call.from_user.id
        user_type = call.data.replace("ACCOUNT_TYPE_", "")
        db_user = User(
            user_id=user_id,
            account_type=UserType[user_type],
        )

        match user_type:
            case "EMPLOYEE":
                msg = bot.reply_to(call.message, CUSER.Messages.ENTER_PERSONNEL_NUMBER)
                bot.register_next_step_handler(msg, handle_veryfication_token, db_user)
            case "STUDENT":
                msg = bot.reply_to(call.message, CUSER.Messages.ENTER_STUDENT_NUMBER)
                bot.register_next_step_handler(msg, handle_veryfication_token, db_user)
            case "GENERAL":
                db_user.veryfication_token = None
                # user_onboarding_state[user_id]["veryfication_token"] = None
                msg = bot.reply_to(call.message, CUSER.Messages.ENTER_YOUR_NAME)
                bot.register_next_step_handler(msg, handle_name, db_user)
            case _:
                raise ValueError("Invalid account type selected")

    if call.data.startswith("SESSION_DATE_"):
        date_str = call.data.split("_")[-1]
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        sessions = (
            db.query(models.Session).filter(models.Session.session_date == date).all()
        )
        jalali_date = Gregorian(date).persian_string()
        msg = f"*سانس های زمین برای {jalali_date}*\n"
        keyboard = InlineKeyboardMarkup()
        for s in sessions:
            if s.available:
                btn_text = f"{s.time_slot} — رزرو کن"
                keyboard.add(
                    InlineKeyboardButton(btn_text, callback_data=f"BOOK_{s.id}")
                )
        bot.edit_message_text(
            msg,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard,
        )
    if call.data == "ADMIN_START":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("View Users", callback_data="ADMIN_VIEW_USERS"),
            InlineKeyboardButton("View Sessions", callback_data="ADMIN_VIEW_SESSIONS"),
        )
        markup.add(
            InlineKeyboardButton(
                "Generate Excel Report", callback_data="ADMIN_GENERATE_REPORT"
            ),
        )
        markup.add(
            InlineKeyboardButton(
                "Generate Monthly Sessions", callback_data="ADMIN_GENERATE_SESSIONS"
            )
        )
        bot.edit_message_text(
            "Admin panel:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
        )
    if call.data.startswith("ADMIN_SESSION_DATE_"):
        date_str = call.data.split("_")[-1]
        date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        sessions = (
            db.query(models.Session).filter(models.Session.session_date == date).all()
        )
        jalali_date = Gregorian(date).persian_string()
        msg = f"*سانس های زمین برای {jalali_date}*\n"
        keyboard = InlineKeyboardMarkup()
        for s in sessions:
            if s.booked_user_id:
                btn_text = f"🔴{s.time_slot}"
            else:
                if s.available:
                    btn_text = f"🟢{s.time_slot}"
                else:
                    btn_text = f"🟡{s.time_slot}"

            keyboard.add(
                InlineKeyboardButton(
                    btn_text, callback_data=f"ADMIN_MANAGE_SESSION_{s.id}"
                )
            )
        keyboard.add(
            InlineKeyboardButton("بازگشت", callback_data=f"ADMIN_VIEW_SESSIONS")
        )
        bot.edit_message_text(
            msg,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard,
        )

    if call.data.startswith("ADMIN_MANAGE_SESSION_"):
        session_id = int(call.data.split("_")[-1])
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session:
            bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )
            return
        if session.booked_user_id:
            booked_user = (
                db.query(User).filter_by(user_id=session.booked_user_id).first()
            )
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(
                    f"لغو سانس", callback_data=f"ADMIN_SESSION_REFUND_{session_id}"
                )
            )
            markup.add(
                InlineKeyboardButton(
                    "بازگشت به منو سانس ها",
                    callback_data=f"ADMIN_SESSION_DATE_{session.session_date}",
                )
            )
            bot.edit_message_text(
                f"سانس: {Gregorian(session.session_date).persian_string()} {session.time_slot}\n توسط {booked_user.name} {booked_user.surname} گرفته شده است.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )
            return
        else:
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(
                    "غیر فعال سازی" if session.available else "فعال سازی",
                    callback_data=(
                        f"ADMIN_DEACTIVATE_SESSION_{session_id}"
                        if session.available
                        else f"ADMIN_ACTIVATE_SESSION_{session_id}"
                    ),
                )
            )
            markup.add(
                InlineKeyboardButton(
                    "بازگشت به منو سانس ها",
                    callback_data=f"ADMIN_SESSION_DATE_{session.session_date}",
                )
            )
            bot.edit_message_text(
                f"سانس: {Gregorian(session.session_date).persian_string()} {session.time_slot}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )
            return
    if call.data.startswith("ADMIN_SESSION_REFUND_"):
        session_id = int(call.data.split("_")[-1])
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session:
            bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )
            return
        bot.send_message(
            session.booked_user_id,
            f"سانس انتخابی شما لغو شده لطفا جهت دریافت وجه با پشتیبانی تماس بگیرید\n *اطلاعات سانس*\n{Gregorian(session.session_date).persian_string()} {session.time_slot}",
        )
    if call.data.startswith("ADMIN_DEACTIVATE_SESSION_"):
        session_id = int(call.data.split("_")[-1])
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session:
            bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )
            return
        session.available = False
        db.commit()
        db.refresh(session)
        bot.edit_message_text(
            f"سانس با موفقیت غبرفعال شد ✅",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton(
                    "بازگشت به منو سانس ها",
                    callback_data=f"ADMIN_SESSION_DATE_{session.session_date}",
                )
            ),
        )
        return
    if call.data.startswith("ADMIN_ACTIVATE_SESSION_"):
        session_id = int(call.data.split("_")[-1])
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session:
            bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )
            return
        session.available = True
        db.commit()
        db.refresh(session)
        bot.edit_message_text(
            f"سانس با موفقیت فعال شد ✅",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton(
                    "بازگشت به منو سانس ها",
                    callback_data=f"ADMIN_SESSION_DATE_{session.session_date}",
                )
            ),
        )
        return
    if call.data.startswith("BOOK_"):
        session_id = int(call.data.split("_")[1])
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session:
            bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )
            return
        # Show cost and ask for confirmation
        user = db.query(User).filter_by(user_id=call.from_user.id).first()
        if user.is_verified == VerificationStatus.VERIFIED:
            cost = int(
                db.query(models.PaymentCategory)
                .filter_by(account_type=user.account_type)
                .first()
                .session_cost
            )
        else:
            cost = int(session.cost)
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                f"Confirm Booking (${cost})", callback_data=f"CONFIRM_{session_id}"
            )
        )
        bot.edit_message_text(
            f"Session: {Gregorian(session.session_date).persian_string()} {session.time_slot}\nCost: ${cost}\nDo you want to book this session?",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
        )
        # bot.answer_callback_query(call.id)
    if call.data.startswith("CONFIRM_"):
        session_id = int(call.data.split("_")[1])
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session:
            bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )
            return
        user = db.query(User).filter_by(user_id=call.from_user.id).first()
        if user.is_verified == VerificationStatus.VERIFIED:
            cost = int(
                db.query(models.PaymentCategory)
                .filter_by(account_type=user.account_type)
                .first()
                .session_cost
            )
        else:
            cost = int(session.cost)
        # Create payment record
        payment = models.Payment(
            user_id=call.from_user.id,
            session_id=session_id,
            amount=cost,
            payment_date=datetime.datetime.now(),
        )
        db.add(payment)
        session.available = False
        session.booked_user_id = call.from_user.id
        db.commit()
        bot.edit_message_text(
            f"✅ Session booked successfully!\nSession: {Gregorian(session.session_date).persian_string()} {session.time_slot}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
        )
        # bot.answer_callback_query(call.id, "Session booked!")

    if call.data == "ADMIN_VIEW_USERS":
        # add pagination for it

        users = db.query(User).all()
        msg = "*کاربران:*\n"
        for u in users:
            msg += f"{u.name} {u.surname} | {u.phone_number} | {u.account_type.value} | {u.is_verified.value}\n"
        bot.send_message(call.message.chat.id, msg or "No users found.")

    if call.data == "ADMIN_VIEW_SESSIONS":
        user_id = call.from_user.id
        user_db = db.query(User).filter_by(user_id=user_id).first()
        if not user_db:
            bot.send_message(
                call.message.chat.id, "You need to register first. Use /start."
            )
            return
        today = datetime.date.today()
        dates = [today + datetime.timedelta(days=i) for i in range(3)]
        sessions = (
            db.query(models.Session)
            .filter(models.Session.session_date.in_(dates))
            .all()
        )
        if not sessions:
            bot.send_message(
                call.message.chat.id, "No sessions available for the next 3 days."
            )
            return
        sessions_by_date = {}
        for s in sessions:
            date_key = s.session_date
            if date_key not in sessions_by_date:
                sessions_by_date[date_key] = []
            sessions_by_date[date_key].append(s)

        msg = "*سانس های زمین*\n"
        keyboard = InlineKeyboardMarkup()
        # Iterate through dates in order
        for date in sorted(sessions_by_date.keys()):
            # Get day name in Persian
            day_name_en = day_name[date.weekday()]
            day_name_fa = PERSIAN_DAY_NAMES.get(day_name_en, day_name_en)

            # Add day header
            keyboard.row(
                InlineKeyboardButton(
                    f"{day_name_fa}", callback_data=f"ADMIN_SESSION_DATE_{date}"
                )
            )
        keyboard.row(
            InlineKeyboardButton("بازگشت به منو", callback_data=f"ADMIN_START")
        )
        bot.edit_message_text(
            msg,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard,
        )
        return

    if call.data == "ADMIN_GENERATE_SESSIONS":
        generating_msg = bot.send_message(
            call.message.chat.id,
            "Generating sessions for the next 30 days...",
        )
        # Call the function to generate sessions
        # Get the first day of next month
        today = datetime.date.today()
        # Generate sessions for the entire month
        sessions_created = 0
        current_date = today + datetime.timedelta(days=1)
        end_date = today + datetime.timedelta(days=30)
        general = (
            db.query(models.PaymentCategory)
            .filter_by(account_type=UserType.GENERAL)
            .first()
        )
        base_cost = general.session_cost

        existing_sessions = (
            db.query(models.Session)
            .filter(
                models.Session.session_date >= current_date,
                models.Session.session_date <= end_date,
            )
            .all()
        )

        # Create a set of (date, time_slot) tuples for quick lookup
        existing_session_keys = {
            (session.session_date, session.time_slot) for session in existing_sessions
        }

        while current_date <= end_date:
            # Generate sessions per day
            for time_slot in TIMESLOTS:
                # Check if this session already exists
                if (current_date, time_slot) not in existing_session_keys:
                    session = models.Session(
                        session_date=current_date,
                        time_slot=time_slot,
                        available=True,
                        cost=base_cost,
                    )
                    db.add(session)
                    sessions_created += 1
            current_date += datetime.timedelta(days=1)

        db.commit()
        # bot.answer_callback_query(
        #     call.id,
        #     f"Created {sessions_created} free sessions for next month!",
        #     show_alert=True,
        # )
        bot.edit_message_text(
            f"✅ Successfully generated {sessions_created} free sessions for 30 days!",
            call.message.chat.id,
            generating_msg.message_id,
        )
        # Schedule message deletion after 5 seconds
        def delete_message():
            try:
                bot.delete_message(call.message.chat.id, generating_msg.message_id)
            except Exception as e:
                print(f"Error deleting message: {e}")
                
        timer = threading.Timer(5.0, delete_message)
        timer.start()

    if call.data == "REPORT_ALL_PAYMENTS":
        # get user all payment and send him pdf version of exel file
        payments = db.query(models.Payment).filter_by(user_id=call.from_user.id).all()
        if not payments:
            bot.send_message(call.message.chat.id, "No payment history found.")
            return
        # Create a DataFrame from payment data
        payment_data = []
        for payment in payments:
            # Get session details for this payment
            session = db.query(models.Session).filter_by(id=payment.session_id).first()

            # Format date for better readability
            payment_date = payment.payment_date.strftime("%Y-%m-%d %H:%M")
            session_date = (
                session.session_date.strftime("%Y-%m-%d") if session else "N/A"
            )

            payment_data.append(
                {
                    "Payment ID": payment.id,
                    "Session Date": session_date,
                    "Time Slot": session.time_slot if session else "N/A",
                    "Amount": f"{payment.amount} $",
                    "Payment Date": payment_date,
                }
            )

        # Create Excel file in memory
        output_excel = BytesIO()
        df = pd.DataFrame(payment_data)
        df.to_excel(output_excel, index=False)
        output_excel.seek(0)

        # Send the Excel file
        bot.send_document(
            call.message.chat.id,
            output_excel,
            visible_file_name=f"payment_history_{call.from_user.id}.xlsx",
            caption="Your payment history report",
        )


@bot.message_handler(func=lambda message: True)
@inject
def message_center(message, db: Session = Dependency(get_db)):
    if message.text == CUSER.Buttons.SHOW_PROFILE:
        user_db = db.query(User).filter_by(user_id=message.from_user.id).first()
        if not user_db:
            bot.send_message(
                message.chat.id,
                "You need to register first. Use /start.",
            )
            return
        status = {
            VerificationStatus.VERIFIED: "🟢 تایید شده",
            VerificationStatus.PENDING: "🟡 در حال بررسی",
            VerificationStatus.REJECTED: "🔴 رد شده",
        }
        account_type = {
            UserType.EMPLOYEE: "👨‍💼 کارمندی",
            UserType.STUDENT: "👨‍🎓 دانشجویی",
            UserType.GENERAL: "🤵 عمومی",
        }
        msg = (
            f"*پروفایل کاربری*\n"
            f"نام: {user_db.name}\n"
            f"نام خانوادگی: {user_db.surname}\n"
            f"شماره تماس: {user_db.phone_number}+\n"
            f"نوع حساب: {account_type[user_db.account_type]}\n"
            f"وضعیت: {status[user_db.is_verified]}\n"
            # f"تاریخ ثبت نام: {user_db.created_at}\n"
        )
        bot.send_message(message.chat.id, msg, parse_mode="Markdown")
        return
    if message.text == CUSER.Buttons.SHOW_SESSIONS:
        user_id = message.from_user.id
        user_db = db.query(User).filter_by(user_id=user_id).first()
        if not user_db:
            bot.send_message(message.chat.id, "You need to register first. Use /start.")
            return
        today = datetime.date.today()
        dates = [today + datetime.timedelta(days=i) for i in range(3)]
        sessions = (
            db.query(models.Session)
            .filter(models.Session.session_date.in_(dates))
            .all()
        )
        if not sessions:
            bot.send_message(
                message.chat.id, "No sessions available for the next 3 days."
            )
            return
        sessions_by_date = {}
        for s in sessions:
            date_key = s.session_date
            if date_key not in sessions_by_date:
                sessions_by_date[date_key] = []
            sessions_by_date[date_key].append(s)

        msg = "*سانس های زمین*\n"
        keyboard = InlineKeyboardMarkup()
        # Iterate through dates in order
        for date in sorted(sessions_by_date.keys()):
            # Get day name in Persian
            day_name_en = day_name[date.weekday()]
            day_name_fa = PERSIAN_DAY_NAMES.get(day_name_en, day_name_en)

            # Add day header
            keyboard.row(
                InlineKeyboardButton(
                    f"{day_name_fa}", callback_data=f"SESSION_DATE_{date}"
                )
            )

        bot.send_message(message.chat.id, msg, reply_markup=keyboard)
        return
    if message.text == CUSER.Buttons.SHOW_PAYMENT_HISTORY:
        user_id = message.from_user.id
        user_db = db.query(User).filter_by(user_id=user_id).first()
        if not user_db:
            bot.send_message(message.chat.id, "You need to register first. Use /start.")
            return
        payments = db.query(models.Payment).filter_by(user_id=user_id).first()
        if not payments:
            bot.send_message(message.chat.id, "No payment history found.")
            return
        msg = "*تاریخچه پرداخت*\n"
        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton(
                "گزارش سه تراکنش اخیر", callback_data="REPORT_RECENT_PAYMENTS"
            )
        )
        keyboard.row(
            InlineKeyboardButton(
                "گزارش تمام تراکنش ها", callback_data="REPORT_ALL_PAYMENTS"
            )
        )
        bot.send_message(message.chat.id, msg, reply_markup=keyboard)
        # for p in payments:
        #     session = db.query(models.Session).filter_by(id=p.session_id).first()
        #     msg += (
        #         f"سانس: {Gregorian(session.session_date).persian_string()} {session.time_slot}\n"
        #         f"مبلغ: ${p.amount}\n"
        #         f"تاریخ پرداخت: {p.payment_date}\n\n"
        #     )
        # bot.send_message(message.chat.id, msg, parse_mode="Markdown")
        return


def handle_veryfication_token(message, db_user: User):
    if db_user.user_id == message.from_user.id:
        try:
            input_text = message.text.strip()
            # Convert Persian/Arabic numerals to ASCII digits
            cleaned = convert_persian_numbers(input_text)
            cleaned = re.sub(r"\D+", "", cleaned.strip(), flags=re.UNICODE)
            if not cleaned:
                msg = bot.reply_to(message, CUSER.Messages.INVALID_NUMBER)
                bot.register_next_step_handler(msg, handle_veryfication_token)
                return

            db_user.veryfication_token = cleaned
            msg = bot.reply_to(message, CUSER.Messages.ENTER_YOUR_NAME)
            bot.register_next_step_handler(msg, handle_name, db_user)
        except:
            raise ValueError("Invalid input. Please enter a valid number.")
    return


def handle_name(message, db_user: User):
    if db_user.user_id == message.from_user.id:
        try:
            cleaned = re.sub(r"[0-9\W_]+", " ", message.text.strip(), flags=re.UNICODE)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if not cleaned:
                msg = bot.reply_to(message, CUSER.Messages.INVALID_NAME)
                bot.register_next_step_handler(msg, handle_name, db_user)
                return
            db_user.name = cleaned
            msg = bot.reply_to(message, CUSER.Messages.ENTER_YOUR_SURNAME)
            bot.register_next_step_handler(msg, handle_surname, db_user)
        except:
            raise ValueError("Invalid input. Please enter a valid name.")
    return


@inject
def handle_surname(message, db_user: User, db: Session = Dependency(get_db)):
    if db_user.user_id == message.from_user.id:
        try:
            cleaned = re.sub(r"[0-9\W_]+", " ", message.text.strip(), flags=re.UNICODE)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if not cleaned:
                msg = bot.reply_to(message, CUSER.Messages.INVALID_SURNAME)
                bot.register_next_step_handler(msg, handle_surname, db_user)
                return
            db_user.surname = cleaned
            keyboard = ReplyKeyboardMarkup(
                resize_keyboard=True, one_time_keyboard=True
            ).add(KeyboardButton(CUSER.Buttons.SHEAR, request_contact=True))
            msg = bot.reply_to(
                message, CUSER.Messages.SHEAR_YOUR_NUMBER, reply_markup=keyboard
            )
            db.add(db_user)
            db.commit()
        except:
            raise ValueError("Invalid input. Please enter a valid surname.")
    return

    # bot.register_next_step_handler(msg, handle_phone_number)


@bot.message_handler(content_types=["contact"])
@inject
def handle_phone_number(message, db=Dependency(get_db)):
    user_db = db.query(User).filter_by(user_id=message.from_user.id).first()
    if not user_db:
        bot.send_message(
            message.chat.id,
            "You need to register first. Use /start.",
        )
        return
    elif user_db.phone_number:
        return
    elif all(user_db.name and user_db.surname) and not user_db.phone_number:
        user_db.phone_number = message.contact.phone_number
        user_db.is_active = True
        user_db.is_verified = (
            VerificationStatus.VERIFIED
            if user_db.account_type == "GENERAL"
            else VerificationStatus.PENDING
        )
        db.commit()
        db.refresh(user_db)

        keyboard = ReplyKeyboardMarkup(
            resize_keyboard=True,
            row_width=3,
        )
        buttons = (
            KeyboardButton(CUSER.Buttons.SHOW_SESSIONS),
            KeyboardButton(CUSER.Buttons.SHOW_PAYMENT_HISTORY),
            KeyboardButton(CUSER.Buttons.SHOW_PROFILE),
        )
        for button in buttons:
            keyboard.add(button)
        bot.send_message(message.from_user.id, CUSER.Messages.SUCCESSFUL_REGISTRATION)
        bot.send_message(
            message.from_user.id,
            CUSER.Messages.WELLCOME_BACK,
            reply_markup=keyboard,
        )
        first_message = user_boarding[message.from_user.id]["first_message"]
        user_boarding.pop(message.from_user.id, None)
        for i in range(first_message, message.message_id + 1):
            bot.delete_message(message.chat.id, i)


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


# bot.infinity_polling()
bot.polling(none_stop=True, interval=0)
