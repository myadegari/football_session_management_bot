from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from constant.general import PERSIAN_DAY_NAMES, TIMESLOTS
from repositories import models
from utils.jalali import Gregorian
import datetime
from calendar import day_name
import threading

class UserFlow:
    def __init__(self,bot):
        self.bot = bot
    def start(self,call,message=None,first_time=False):
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
        if first_time:
            self.bot.send_message(message.chat.id, "Admin Panel:", reply_markup=markup)
        else:
            self.bot.edit_message_text(
                "Admin panel:",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )
    def seesion_date(self,call,db):
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
        self.bot.edit_message_text(
            msg,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard,
        )
    def manage_session(self,call,db):
        session_id = int(call.data.split("_")[-1])
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session:
            self.bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )
            return
        if session.booked_user_id:
            booked_user = (
                db.query(models.User).filter_by(user_id=session.booked_user_id).first()
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
            self.bot.edit_message_text(
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
            self.bot.edit_message_text(
                f"سانس: {Gregorian(session.session_date).persian_string()} {session.time_slot}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )
            return
    def session_refund(self,call,db):
        session_id = int(call.data.split("_")[-1])
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session:
            self.bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )
            return
        self.bot.send_message(
            session.booked_user_id,
            f"سانس انتخابی شما لغو شده لطفا جهت دریافت وجه با پشتیبانی تماس بگیرید\n *اطلاعات سانس*\n{Gregorian(session.session_date).persian_string()} {session.time_slot}",
        )
    def deactive_session(self,call,db):
        session_id = int(call.data.split("_")[-1])
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session:
            self.bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )
            return
        session.available = False
        db.commit()
        db.refresh(session)
        self.bot.edit_message_text(
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
    def active_session(self,call,db):
        session_id = int(call.data.split("_")[-1])
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session:
            self.bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )
            return
        session.available = True
        db.commit()
        db.refresh(session)
        self.bot.edit_message_text(
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
    def view_sessions(self,call,db):
        user_id = call.from_user.id
        user_db = db.query(models.User).filter_by(user_id=user_id).first()
        if not user_db:
            self.bot.send_message(
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
            self.bot.send_message(
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
        self.bot.edit_message_text(
            msg,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard,
        )
        return
    def view_users(self,call,db):
        # add pagination for it

        users = db.query(models.User).all()
        msg = "*کاربران:*\n"
        for u in users:
            msg += f"{u.name} {u.surname} | {u.phone_number} | {u.account_type.value} | {u.is_verified.value}\n"
        self.bot.send_message(call.message.chat.id, msg or "No users found.")
    def generate_sessions(self,call,db):
        generating_msg = self.bot.send_message(
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
            .filter_by(account_type=models.UserType.GENERAL)
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
        self.bot.edit_message_text(
            f"✅ Successfully generated {sessions_created} free sessions for 30 days!",
            call.message.chat.id,
            generating_msg.message_id,
        )
        # Schedule message deletion after 5 seconds
        def delete_message():
            try:
                self.bot.delete_message(call.message.chat.id, generating_msg.message_id)
            except Exception as e:
                print(f"Error deleting message: {e}")
                
        timer = threading.Timer(5.0, delete_message)
        timer.start()