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
from math import ceil # Add this import

# Define constants for pagination
USERS_PER_PAGE = 10

class UserFlow:
    def __init__(self,bot):
        self.bot = bot
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

    def start(self, call, message=None, first_time=False):
        markup = InlineKeyboardMarkup(row_width=2) # Adjust row width if needed
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
        )
        # Translate: "Admin Panel:"
        text = "پنل مدیریت:"
        if first_time and message:
            self.bot.send_message(message.chat.id, text, reply_markup=markup)
        elif call:
            try:
                self.bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup,
                )
            except Exception as e:
                print(f"Error editing message: {e}") # Handle potential API errors (e.g., message not modified)
        else:
             print("Error: 'start' called without 'call' or 'message'.") # Log error case


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
            # Translate: "توسط ... گرفته شده است." and "توسط کاربر نامشخص گرفته شده است."
            user_info = f"توسط {booked_user.name} {booked_user.surname} رزرو شده است." if booked_user else "توسط کاربر نامشخص رزرو شده است."
            msg = f"{session_info}\n{user_info}"
            markup.add(
                # Translate: "لغو و استرداد وجه"
                InlineKeyboardButton(
                    "لغو رزرو و استرداد وجه", callback_data=f"ADMIN_SESSION_REFUND_{session_id}"
                )
            )
        else:
            msg = session_info
            # Translate: "غیر فعال سازی" and "فعال سازی"
            action_text = "غیرفعال‌سازی" if session.available else "فعال‌سازی"
            action_callback = (
                f"ADMIN_DEACTIVATE_SESSION_{session_id}"
                if session.available
                else f"ADMIN_ACTIVATE_SESSION_{session_id}"
            )
            markup.add(
                InlineKeyboardButton(action_text, callback_data=action_callback)
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

        # Translate: "فعال" and "غیرفعال"
        status_text = "فعال" if available_status else "غیرفعال"
        try:
            # Translate: "سانس با موفقیت ... شد ✅"
            self.bot.edit_message_text(
                f"سانس با موفقیت {status_text} شد ✅",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=InlineKeyboardMarkup().add(
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
        msg = f"*کاربران (صفحه {page}/{total_pages}):*\n\n"
        if not users_page:
            # Translate: "No users found."
            msg += "کاربری یافت نشد."
        else:
            for u in users_page:
                 # Added default values for potentially missing attributes
                 acc_type = getattr(u.account_type, 'value', 'نامشخص') # Translate 'N/A'
                 verified_status = getattr(u.is_verified, 'value', 'نامشخص') # Translate 'N/A'
                 # Translate labels
                 msg += f"👤 نام: {u.name or ''} {u.surname or ''}\n" \
                        f"📞 شماره تماس: {u.phone_number or 'ثبت نشده'}\n" \
                        f"🏷️ نوع حساب: {acc_type}\n" \
                        f"✅ وضعیت تایید: {verified_status}\n" \
                        f"--------------------\n"


        markup = InlineKeyboardMarkup()
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
             try:
                 self.bot.answer_callback_query(call.id)
             except Exception: pass # Ignore errors here


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
            final_msg = f"✅ با موفقیت {sessions_created} سانس جدید برای ۳۰ روز آینده ایجاد شد."
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
                    # print(f"Error deleting message: {e}")
                    pass

            timer = threading.Timer(7.0, delete_message) # Increased delay slightly
            timer.start()