import time
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from sqlalchemy.orm import Session
from constant.general import ACCOUNT_TYPE, PERSIAN_DAY_NAMES, STATUS, TIMESLOTS
from repositories import models
from utility import convert_english_numbers
from utils.jalali import Gregorian
import datetime
from calendar import day_name
from io import BytesIO
import threading

import pandas as pd
from math import ceil # Add this import
from utils.dependency import Dependency, inject
from repositories.utils import get_db

# Define constants for pagination
USERS_PER_PAGE = 10

class UserFlow:
    def __init__(self,bot):
        self.bot = bot
        self.user_boarding={}
    def _get_session_or_warn(self, call, db, session_id):
        """Fetches a session by ID or sends a warning if not found."""
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session:
            try:
                # Translate: "This session is no longer available."
                self.bot.answer_callback_query(
                    call.id, "این سانس دیگر در دسترس نیست.", show_alert=True
                )
            except Exception as e:
                print(f"Error answering callback query: {e}") # Log error if needed
            return None
        return session
    def _send_and_delete(self, chat_id, text, delay=5):
        sent_message = self.bot.send_message(chat_id, text)
        def delete():
            time.sleep(delay)
            try:
                self.bot.delete_message(chat_id, sent_message.message_id)
            except Exception as e:
                print(f"Error deleting message: {e}")
        threading.Thread(target=delete).start()

    def start(self, call, message=None, first_time=False):
        from telebot.types import ReplyKeyboardRemove
        markup = InlineKeyboardMarkup(row_width=1) # Adjust row width if needed
        markup.add(
            # Translate: "View Users"
            InlineKeyboardButton("مشاهده کاربران", callback_data="ADMIN_VIEW_USERS_PAGE_1"), # Start on page 1
            # Translate: "View Sessions"
            InlineKeyboardButton("مشاهده سانس‌ها", callback_data="ADMIN_VIEW_SESSIONS"),
            # Translate: "Generate Excel Report"
            InlineKeyboardButton(
                "دریافت گزارش اکسل", callback_data="ADMIN_GENERATE_REPORT"
            ),
            # Translate: "Generate Monthly Sessions"
            InlineKeyboardButton(
                "ایجاد سانس‌های ماهانه", callback_data="ADMIN_GENERATE_SESSIONS"
            ),
            # Translate: "Change Session Costs"
            InlineKeyboardButton(
                "تغییر هزینه سانس‌ها", callback_data="ADMIN_CHANGE_BASED_COST"
            ),
            # Translate: "User Verification"
            )
        # Translate: "Admin Panel:"
        text = "پنل مدیریت:"
        if first_time:
            mag = self.bot.send_message(message.chat.id, "در حال ورود به پنل مدیریت...", reply_markup=ReplyKeyboardRemove(selective=True))
            self.bot.delete_message(message.chat.id, mag.message_id) # Delete the message after sending
            self.bot.send_message(message.chat.id, text, reply_markup=markup)
        elif call:
            try:
                self.bot.edit_message_text(
                    text,
                    message_id=call.message.message_id,
                    reply_markup=markup,
                )
            except Exception as e:
                print(f"Error editing message: {e}") # Handle potential API errors (e.g., message not modified)
        else:
            self.bot.send_message(message.chat.id, text, reply_markup=markup)


    def seesion_date(self, call, db):
        try:
            date_str = call.data.split("_")[-1]
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except (IndexError, ValueError):
            # Translate: "Invalid date format."
            self.bot.answer_callback_query(call.id, "فرمت تاریخ نامعتبر است.", show_alert=True)
            return

        sessions = (
            db.query(models.Session).filter(models.Session.session_date == date).order_by(models.Session.time_slot).all() # Order sessions by time
        )
        jalali_date = Gregorian(date).persian_string()
        msg = f"*سانس‌های زمین برای {jalali_date}*\n" # Already Persian
        keyboard = InlineKeyboardMarkup()

        for s in sessions:
            if s.booked_user_id:
                # Translate: "(Booked)"
                btn_text = f"🔴 {s.time_slot} (رزرو شده)"
            elif s.available:
                # Translate: "(Available)"
                btn_text = f"🟢 {s.time_slot} (موجود)"
            else:
                # Translate: "(Inactive)"
                btn_text = f"🟡 {s.time_slot} (غیرفعال)"

            keyboard.add(
                InlineKeyboardButton(
                    btn_text, callback_data=f"ADMIN_MANAGE_SESSION_{s.id}"
                )
            )
        keyboard.add(
            InlineKeyboardButton("بازگشت", callback_data="ADMIN_VIEW_SESSIONS") # Already Persian
        )
        try:
            self.bot.edit_message_text(
                msg,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard,
                parse_mode="Markdown" # Ensure Markdown is parsed
            )
        except Exception as e:
            print(f"Error editing message: {e}")

    def manage_session(self, call, db):
        try:
            session_id = int(call.data.split("_")[-1])
        except (IndexError, ValueError):
            # Translate: "Invalid session ID."
            self.bot.answer_callback_query(call.id, "شناسه سانس نامعتبر است.", show_alert=True)
            return

        session = self._get_session_or_warn(call, db, session_id)
        if not session:
            return # Warning already sent by helper

        markup = InlineKeyboardMarkup()
        session_info = f"سانس: {Gregorian(session.session_date).persian_string()} {session.time_slot}" # Already Persian

        if session.booked_user_id:
            booked_user = (
                db.query(models.User).filter_by(user_id=session.booked_user_id).first()
            )
            user_info = f"توسط {booked_user.name} {booked_user.surname} رزرو شده است." if booked_user else "توسط کاربر نامشخص رزرو شده است."
            msg = f"{session_info}\n{user_info}"
            markup.add(
                # Translate: "لغو و استرداد وجه"
                    "لغو رزرو و استرداد وجه", callback_data=f"ADMIN_SESSION_REFUND_{session_id}"
                )
        else:
            msg = session_info
            action_text = "غیرفعال‌سازی" if session.available else "فعال‌سازی"
            action_callback = (
                f"ADMIN_DEACTIVATE_SESSION_{session_id}"
                if session.available
                else f"ADMIN_ACTIVATE_SESSION_{session_id}"
            )
            markup.add(
                InlineKeyboardButton(
                    action_text, callback_data=action_callback
                )
            )

        markup.add(
            # Translate: "بازگشت به منو سانس ها"
            InlineKeyboardButton(
                "بازگشت به لیست سانس‌ها",
                callback_data=f"ADMIN_SESSION_DATE_{session.session_date}",
            )
        )
        try:
            self.bot.edit_message_text(
                msg,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )
        except Exception as e:
            print(f"Error editing message: {e}")


    def session_refund(self, call, db):
        try:
            session_id = int(call.data.split("_")[-1])
        except (IndexError, ValueError):
            # Translate: "Invalid session ID."
            self.bot.answer_callback_query(call.id, "شناسه سانس نامعتبر است.", show_alert=True)
            return

        session = self._get_session_or_warn(call, db, session_id)
        if not session:
            return

        if not session.booked_user_id:
            # Translate: "This session is not booked."
            self.bot.answer_callback_query(call.id, "این سانس رزرو نشده است.", show_alert=True)
            return

        # --- Logic for refund (e.g., update session, notify user) ---
        booked_user_id = session.booked_user_id
        session_details = f"{Gregorian(session.session_date).persian_string()} {session.time_slot}"

        # Update session state (make it available again, remove user booking)
        session.booked_user_id = None
        session.available = True # Or False depending on desired state after refund
        db.commit()
        db.refresh(session)

        # Notify user
        try:
            # Translate user notification message
            self.bot.send_message(
                booked_user_id,
                f"سانس انتخابی شما توسط مدیریت لغو شد. وجه پرداختی به زودی به حساب شما بازگردانده خواهد شد.\n*اطلاعات سانس*\n{session_details}",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Error sending refund notification to user {booked_user_id}: {e}")

        # Update the admin message
        # Translate: "✅ سانس لغو و کاربر مطلع شد."
        self.bot.answer_callback_query(call.id, "✅ سانس لغو و به کاربر اطلاع داده شد.")
        # Go back to the session management view for this session
        self.manage_session(call, db) # Refresh the view


    def _toggle_session_availability(self, call, db, available_status):
        """Helper to activate/deactivate a session."""
        try:
            session_id = int(call.data.split("_")[-1])
        except (IndexError, ValueError):
            # Translate: "Invalid session ID."
            self.bot.answer_callback_query(call.id, "شناسه سانس نامعتبر است.", show_alert=True)
            return

        session = self._get_session_or_warn(call, db, session_id)
        if not session:
            return

        if session.booked_user_id:
             # Translate: "Cannot change status of a booked session."
             self.bot.answer_callback_query(call.id, "امکان تغییر وضعیت سانس رزرو شده وجود ندارد.", show_alert=True)
             return

        session.available = available_status
        db.commit()
        db.refresh(session)

        status_text = "فعال" if available_status else "غیرفعال"
        try:
            # Translate: "سانس با موفقیت ... شد ✅"
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ سانس با موفقیت {status_text} شد.",
                reply_markup=InlineKeyboardMarkup(
                    InlineKeyboardButton(
                        # Translate: "بازگشت به منو سانس ها"
                        "بازگشت به لیست سانس‌ها",
                        callback_data=f"ADMIN_SESSION_DATE_{session.session_date}",
                    )
                ),
            )
        except Exception as e:
            print(f"Error editing message: {e}")

    def deactive_session(self, call, db):
        self._toggle_session_availability(call, db, available_status=False)

    def active_session(self, call, db):
        self._toggle_session_availability(call, db, available_status=True)


    def view_sessions(self, call, db):
        # No need to check user registration here if this is admin-only flow
        today = datetime.date.today()
        # Show sessions for the next 7 days, for example
        num_days_to_show = 7
        dates = [today + datetime.timedelta(days=i) for i in range(num_days_to_show)]

        # Fetch sessions efficiently
        sessions = (
            db.query(models.Session)
            .filter(models.Session.session_date.in_(dates))
            .order_by(models.Session.session_date) # Order by date
            .all()
        )

        sessions_by_date = {}
        for s in sessions:
            date_key = s.session_date
            if date_key not in sessions_by_date:
                sessions_by_date[date_key] = []
            sessions_by_date[date_key].append(s) # Sessions are already ordered by time if fetched that way

        # Translate: "*نمایش سانس های زمین*"
        msg = "*نمایش سانس‌های زمین*\n"
        keyboard = InlineKeyboardMarkup()

        if not sessions_by_date:
             # Translate: "No sessions found for the next ... days."
             msg += f"\nسانسی برای {num_days_to_show} روز آینده یافت نشد."
        else:
            # Iterate through the desired dates to maintain order
            for date in dates:
                if date in sessions_by_date: # Check if there are sessions for this date
                    day_name_en = day_name[date.weekday()]
                    day_name_fa = PERSIAN_DAY_NAMES.get(day_name_en, day_name_en)
                    jalali_date_str = Gregorian(date).persian_string() # Add Jalali date string

                    # Add day header button
                    keyboard.add( # Use add() instead of row() for single button rows
                        InlineKeyboardButton(
                            f"{day_name_fa} - {jalali_date_str}", callback_data=f"ADMIN_SESSION_DATE_{date}"
                        )
                    )

        keyboard.add(
            # Translate: "بازگشت به منو اصلی"
            InlineKeyboardButton("بازگشت به پنل مدیریت", callback_data="ADMIN_START")
        )
        try:
            self.bot.edit_message_text(
                msg,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Error editing message: {e}")


    def view_users(self, call, db):
        page = 1
        # Extract page number from callback data if present
        if call.data.startswith("ADMIN_VIEW_USERS_PAGE_"):
            try:
                page = int(call.data.split("_")[-1])
            except (ValueError, IndexError):
                page = 1 # Default to page 1 on error

        offset = (page - 1) * USERS_PER_PAGE
        users_query = db.query(models.User)
        total_users = users_query.count()
        # Use math.ceil for calculating total_pages
        total_pages = ceil(total_users / USERS_PER_PAGE) if total_users > 0 else 1
        users_page = users_query.offset(offset).limit(USERS_PER_PAGE).all()

        # Translate: "*کاربران (صفحه .../...):*"
        markup = InlineKeyboardMarkup()
        msg = f"*کاربران (صفحه {page}/{total_pages}):*\n\n"
        if not users_page:
            # Translate: "No users found."
            msg += "کاربری یافت نشد."
        else:
            for u in users_page:
                markup.row(
                    InlineKeyboardButton(
                        f"👤 {u.name or ''} {u.surname or ''}",
                        callback_data=f"ADMIN_VIEW_USER_{page}_{u.user_id}"
                    )
                )

        nav_buttons = []
        if page > 1:
            nav_buttons.append(
                # Translate: "⬅️ قبلی"
                InlineKeyboardButton("⬅️ قبلی", callback_data=f"ADMIN_VIEW_USERS_PAGE_{page-1}")
            )
        if page < total_pages:
            nav_buttons.append(
                # Translate: "بعدی ➡️"
                InlineKeyboardButton("بعدی ➡️", callback_data=f"ADMIN_VIEW_USERS_PAGE_{page+1}")
            )

        if nav_buttons:
            markup.row(*nav_buttons) # Add navigation buttons in one row

        # Translate: "بازگشت به منو اصلی"
        markup.add(InlineKeyboardButton("بازگشت به پنل مدیریت", callback_data="ADMIN_START"))

        try:
            # Use edit_message_text if navigating pages, send_message if called initially?
            # Assuming edit for simplicity as it replaces the previous message/keyboard
            self.bot.edit_message_text(
                msg,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )
        except Exception as e:
            # If message hasn't changed (e.g., same page content), API might error
            if "message is not modified" not in str(e):
                print(f"Error editing message for view_users: {e}")
            # Optionally, answer callback query to acknowledge button press even if message doesn't change

    def view_user_details(self,call,db):
        id = call.data.split("_")[-1]
        page = call.data.split("_")[-2]
        user_db = db.query(models.User).filter_by(user_id=int(id)).first()
        
        markup = InlineKeyboardMarkup()
        msg = f"*مشخصات کابر:*\n"
        # Translate labels
        msg += f"👤 نام: {user_db.name or ''} {user_db.surname or ''}\n" \
            f"📞 شماره تماس: {f'{user_db.phone_number}+' or 'ثبت نشده'}\n"\
            f"🏷️ نوع حساب: {ACCOUNT_TYPE[user_db.account_type]}\n" \
            f"✅ وضعیت تایید: {STATUS[user_db.is_verified]}\n"

        markup.add(
            InlineKeyboardButton(
                "مشاهده رزروها", callback_data=f"ADMIN_VIEW_USER_BOOKINGS_FROM_{page}_{id}_PAGE_1"
            ),
            InlineKeyboardButton(
                "مشاهده پرداخت‌ها", callback_data=f"ADMIN_VIEW_USER_PAYMENTS_FROM_{page}_{id}_PAGE_1"
            ),
            InlineKeyboardButton(
                "بررسی و تغییر وضعیت کابر", callback_data=f"ADMIN_VIEW_USER_VERIFICATION_FROM_{page}_{id}"
            ),
            InlineKeyboardButton(
                "بازگشت به لیست کاربران", callback_data=f"ADMIN_VIEW_USERS_PAGE_{page}"
            ),
            row_width=1

        )
        try:
            # Use edit_message_text if navigating pages, send_message if called initially?
            # Assuming edit for simplicity as it replaces the previous message/keyboard
            self.bot.edit_message_text(
                msg,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )
        except Exception as e:
            # If message hasn't changed (e.g., same page content), API might error
            if "message is not modified" not in str(e):
                print(f"Error editing message for view_users: {e}")
            # Optionally, answer callback query to acknowledge button press even if message doesn't change
            try:
                self.bot.answer_callback_query(call.id)
            except Exception: pass # Ignore errors here
    def view_user_bookings(self,call,db):
        #"ADMIN_VIEW_USER_BOOKINGS_FROM_{page}_{user_id}_PAGE_1"
        # try:
        from_page,user_id,_,call_page = call.data.split("_")[-4:]
        user_db = db.query(models.User).filter_by(user_id=user_id).first()
        # except:
        #     # Translate: "Invalid user ID."
        #     self._send_and_delete(
        #         call.message.chat.id,
        #         "شناسه کاربر نامعتبر است.",
        #         delay=2
        #     )
        #     return
        try:
            page = int(call_page)
        except (ValueError, IndexError):
            page = 1 # Default to page 1 on error

        offset = (page - 1) * USERS_PER_PAGE
        user_total_booking = db.query(models.Session).filter_by(booked_user_id=user_id).count()
        # Use math.ceil for calculating total_pages
        total_pages = ceil(user_total_booking / USERS_PER_PAGE) if user_total_booking > 0 else 1
        users_page = db.query(models.Session).filter_by(booked_user_id=user_id).offset(offset).limit(USERS_PER_PAGE).all()

        # Added default values for potentially missing attributes
        markup = InlineKeyboardMarkup()
        msg = f"*رزروهای کابر:*\n"
        msg += f"نام: {user_db.name or ''} {user_db.surname or ''}\n"

        if not users_page:
            # Translate: "No bookings found."
            msg += "رزروی  یافت نشد."
        else:
            # use pagination

            for booking in users_page:
                session = db.query(models.Session).filter_by(id=booking.id).first()
                if session:
                    jalali_date = Gregorian(session.session_date).persian_string()
                    msg += f"📅 تاریخ: {jalali_date} - {session.time_slot}\n"
                else:
                    msg += "سانس نامعتبر است.\n"
        nav_buttons = []
        if page > 1:
            nav_buttons.append(
                # Translate: "⬅️ قبلی"
                InlineKeyboardButton("⬅️ قبلی", callback_data=f"ADMIN_VIEW_USER_BOOKINGS_FROM_{from_page}_{user_id}_PAGE_{page-1}")
            )
        if page < total_pages:
            nav_buttons.append(
                # Translate: "بعدی ➡️"
                InlineKeyboardButton("بعدی ➡️", callback_data=f"ADMIN_VIEW_USER_BOOKINGS_FROM_{from_page}_{user_id}_PAGE_{page+1}")
            )

        if nav_buttons:
            markup.row(*nav_buttons) # Add navigation buttons in one row

        # Translate: "بازگشت به منو اصلی"
        markup.add(
            InlineKeyboardButton(
                "بازگشت به مشخصات کاربر", callback_data=f"ADMIN_VIEW_USER_{from_page}_{user_id}"
            ))
        markup.add(InlineKeyboardButton("بازگشت به پنل مدیریت", callback_data="ADMIN_START"))
        try:
            # Use edit_message_text if navigating pages, send_message if called initially?
            # Assuming edit for simplicity as it replaces the previous message/keyboard
            self.bot.edit_message_text(
                msg,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )
        except Exception as e:
            # If message hasn't changed (e.g., same page content), API might error
            if "message is not modified" not in str(e):
                print(f"Error editing message for view_users: {e}")
            # Optionally, answer callback query to acknowledge button press even if message doesn't change
            try:
                self.bot.answer_callback_query(call.id)
            except Exception: pass # Ignore errors here
    def change_based_cost(self,call,db):
        type_based_costs = db.query(models.PaymentCategory).all()
        markup = InlineKeyboardMarkup()
        msg = f"*هزینه های سانس ها:*\n"
        for type_based_cost in type_based_costs:
            msg += f"🏷️ نوع حساب: {ACCOUNT_TYPE[type_based_cost.account_type]}\n" \
                f"💰 هزینه سانس: {convert_english_numbers(type_based_cost.session_cost)} تومان\n"
            markup.add(
                InlineKeyboardButton(
                    f"تغییر هزینه {ACCOUNT_TYPE[type_based_cost.account_type]}",
                    callback_data=f"ADMIN_CHANGE_BASED_COST_{type_based_cost.account_type.value}"
                )
            )
        markup.add(
            InlineKeyboardButton(
                "بازگشت به پنل مدیریت",
                callback_data="ADMIN_START"
            )
        )
        try:
            self.bot.edit_message_text(
                msg,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
                parse_mode="Markdown"
            )
        except Exception as e:
            # If message hasn't changed (e.g., same page content), API might error
            if "message is not modified" not in str(e):
                print(f"Error editing message for view_users: {e}")
            # Optionally, answer callback query to acknowledge button press even if message doesn't change
            try:
                self.bot.answer_callback_query(call.id)
            except Exception: pass

    def change_cost(self,call,db):
        account_type = call.data.split("_")[-1]
        based_cost = db.query(models.PaymentCategory).filter_by(account_type=account_type).first()
        msg = f"*تغییر هزینه سانس {based_cost.account_type.value}:*\n"
        msg += f"میزان هزینه سانسس را وارد کنید."
        message = self.bot.edit_message_text(
                msg,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None,
                parse_mode="Markdown"
            )
        self.user_boarding[call.message.chat.id] = call.message.message_id
        self.bot.register_next_step_handler(message, self.handle_cost_change, based_cost)

    @inject
    def handle_cost_change(self,message,based_cost,db:Session=Dependency(get_db)):
        try:
            new_cost = int(message.text)
            based_cost.session_cost = new_cost
            db.commit()
            self._send_and_delete(
                message.chat.id,
                "✅هزینه سانس با موفقیت تغییر یافت.",
                5
            )
            for i in range(self.user_boarding[message.chat.id] , message.message_id+1):
                self.bot.delete_message(
                    message.chat.id,
                    i
                )
            self.user_boarding.pop(message.chat.id)
            self.start(call=None,message=message)
        except ValueError:
            self.bot.send_message(
                message.chat.id,
                "لطفا یک عدد وارد کنید."
            )
            self.bot.register_next_step_handler(message, self.handle_cost_change, based_cost)

    def user_verification(self,call,db):
        #ADMIN_VIEW_USER_VERIFICATION_FROM_{page}_{id}
        from_page,user_id = call.data.split("_")[-2:]
        user_db = db.query(models.User).filter_by(user_id=user_id)
    def generate_sessions(self, call, db):
        try:
            # Translate: "⏳ در حال تولید سانس ها برای ۳۰ روز آینده..."
            generating_msg = self.bot.send_message(
                call.message.chat.id,
                "⏳ در حال ایجاد سانس‌ها برای ۳۰ روز آینده...",
            )
        except Exception as e:
            print(f"Error sending 'generating' message: {e}")
            # Optionally notify admin via callback query
            # Translate: "Error starting generation."
            self.bot.answer_callback_query(call.id, "خطا در شروع عملیات ایجاد سانس‌ها.", show_alert=True)
            return

        sessions_created = 0
        try:
            # --- Session Generation Logic ---
            today = datetime.date.today()
            start_date = today + datetime.timedelta(days=1) # Start from tomorrow
            end_date = today + datetime.timedelta(days=30) # Up to 30 days from today

            # Fetch base cost once
            general_category = (
                db.query(models.PaymentCategory)
                .filter_by(account_type=models.UserType.GENERAL)
                .first()
            )
            if not general_category:
                 # Handle error: Base cost category not found
                 # Translate: "❌ خطا: دسته بندی هزینه پایه یافت نشد."
                 self.bot.edit_message_text(
                     "❌ خطا: دسته‌بندی هزینه پایه یافت نشد.",
                     call.message.chat.id,
                     generating_msg.message_id,
                 )
                 return

            base_cost = general_category.session_cost

            # Fetch existing sessions in the date range efficiently
            existing_sessions = (
                db.query(models.Session.session_date, models.Session.time_slot) # Select only needed columns
                .filter(
                    models.Session.session_date >= start_date,
                    models.Session.session_date <= end_date,
                )
                .all()
            )
            existing_session_keys = set(existing_sessions) # Set of (date, time_slot) tuples

            sessions_to_add = []
            current_date = start_date
            while current_date <= end_date:
                for time_slot in TIMESLOTS:
                    if (current_date, time_slot) not in existing_session_keys:
                        sessions_to_add.append(models.Session(
                            session_date=current_date,
                            time_slot=time_slot,
                            available=True,
                            cost=base_cost,
                        ))
                current_date += datetime.timedelta(days=1)

            if sessions_to_add:
                db.add_all(sessions_to_add)
                db.commit()
                sessions_created = len(sessions_to_add)

            # --- Success Message ---
            # Translate: "✅ با موفقیت ... سانس جدید برای ۳۰ روز آینده ایجاد شد."
            final_msg = f"✅ با موفقیت {convert_english_numbers(sessions_created)} سانس جدید برای ۳۰ روز آینده ایجاد شد."
            self.bot.edit_message_text(
                final_msg,
                call.message.chat.id,
                generating_msg.message_id,
            )

        except Exception as e:
            # --- Error Handling ---
            db.rollback() # Rollback any partial changes
            print(f"Error generating sessions: {e}")
            # Translate: "❌ خطا در تولید سانس ها: ..."
            error_msg = f"❌ خطا در ایجاد سانس‌ها: {e}"
            self.bot.edit_message_text(
                error_msg,
                call.message.chat.id,
                generating_msg.message_id,
            )
            # Keep the error message visible, don't delete immediately
            return # Exit before scheduling deletion

        # --- Schedule Deletion of Success/Generating Message ---
        # Only schedule deletion if successful
        if sessions_created >= 0: # Check if generation process completed (even if 0 created)
            def delete_message():
                try:
                    self.bot.delete_message(call.message.chat.id, generating_msg.message_id)
                except Exception as e:
                    # Ignore deletion errors (e.g., message already deleted)
                    print(f"Error deleting message: {e}")
                    pass

            timer = threading.Timer(7.0, delete_message) # Increased delay slightly
            timer.start()
    def generate_report(self, call, db):
        try:
            generating_msg = self.bot.send_message(
                call.message.chat.id,
                "⏳ در حال تولید گزارش"
            )
        except Exception as e:
            print(f"Error sending 'generating' message: {e}")

            self.bot.answer_callback_query(call.id, "خطا در شروع عملیات ایجاد سانس‌ها.", show_alert=True)
            return
        payments = db.query(models.Payment).all()
        if not payments:
            self.bot.send_message(call.message.chat.id, "No payment history found.")
            return
        payment_data = []
        for payment in payments:
            session = db.query(models.Session).filter_by(id=payment.session_id).first()
            user_db = db.query(models.User).filter_by(user_id=session.booked_user_id)
            payment_date = payment.payment_date.strftime("%Y-%m-%d %H:%M")
            session_date = (
                session.session_date.strftime("%Y-%m-%d") if session else "N/A"
            )

            payment_data.append(
                {
                    "تاریخ سانس":  Gregorian(session_date).persian_string(),
                    "زمان سانس": session.time_slot if session else "N/A",
                    "شناسه پرداخت": payment.id,
                    "قیمت": f"{payment.amount} $",
                    "تاریخ پرداخت": Gregorian(payment_date).persian_string(),
                    "نام": user_db.name if user_db else "N/A",
                    "نام خانوادگی": user_db.surname if user_db else "N/A",
                    "شماره تماس": user_db.phone_number if user_db else "N/A",
                }
            )

        # Create Excel file in memory
        output_excel = BytesIO()
        df = pd.DataFrame(payment_data)
        df.to_excel(output_excel, index=False)
        output_excel.seek(0)
        final_msg = f"✅ گزارش پرداخت ها با موفقیت ایجاد شد."
        self.bot.edit_message_text(
            final_msg,
            call.message.chat.id,
            generating_msg.message_id,
        )
        # Send the Excel file
        self.bot.send_document(
            call.message.chat.id,
            output_excel,
            visible_file_name=f"تاریخچه پرداخت_{call.from_user.id}.xlsx",
            caption="تاریخچه پرداخت",
        )
        def delete_message():
            try:
                self.bot.delete_message(call.message.chat.id, generating_msg.message_id)
            except Exception as e:
                # Ignore deletion errors (e.g., message already deleted)
                print(f"Error deleting message: {e}")
                pass

        timer = threading.Timer(7.0, delete_message) # Increased delay slightly
        timer.start()