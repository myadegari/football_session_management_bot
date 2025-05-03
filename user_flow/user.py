import datetime
import re
import threading
from calendar import day_name
from io import BytesIO
from tkinter import E

import pandas as pd
from sqlalchemy.orm import Session
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    ReplyKeyboardMarkup,
)

from constant import user as CUSER
from constant.general import PERSIAN_DAY_NAMES, TIMESLOTS
from repositories import models
from repositories.utils import get_db
from utility import (
    convert_english_numbers,
    convert_persian_numbers,
    decode_json,
    encode_json,
)
from utils.dependency import Dependency, inject
from utils.jalali import Gregorian


class UserFlow:
    def __init__(self, bot):
        self.bot = bot
        self.bot.register_message_handler(
            self.handle_phone_number, content_types=["contact"]
        )
        self.bot.register_message_handler(
            self.verify_payment, content_types=["successful_payment"]
        )
        self.bot.register_pre_checkout_query_handler(
            func=lambda query: True,
            callback=lambda query: self.pre_checkout_query(query),
        )
        self.user_boarding = {}

    def start(self, message, db, admin_start):
        user_id = message.from_user.id
        user_db = db.query(models.User).filter_by(user_id=user_id).first()
        if user_db:
            if user_db.role == models.UserRole.ADMIN:
                admin_start(None, message, first_time=True)

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
                self.bot.send_message(
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
        self.user_boarding[user_id] = {
            "first_message": message.message_id,
        }
        for key in keys:
            markup.row(key)
        self.bot.send_message(
            message.chat.id, CUSER.Messages.SELECT_ACCOUNT_TYPE, reply_markup=markup
        )

    @inject
    def acccount_register(self, call, db: Session = Dependency(get_db)):
        user_id = call.from_user.id
        user_type = call.data.split(":")[-1]
        db_user = models.User(
            user_id=user_id,
            account_type=models.UserType[user_type],
        )

        match user_type:
            case "EMPLOYEE":
                msg = self.bot.reply_to(
                    call.message, CUSER.Messages.ENTER_PERSONNEL_NUMBER
                )
                self.bot.register_next_step_handler(
                    msg, self.handle_veryfication_token, db_user
                )
            case "STUDENT":
                msg = self.bot.reply_to(
                    call.message, CUSER.Messages.ENTER_STUDENT_NUMBER
                )
                self.bot.register_next_step_handler(
                    msg, self.handle_veryfication_token, db_user
                )
            case "GENERAL":
                db_user.veryfication_token = None
                db_user.is_verified = models.VerificationStatus.VERIFIED
                msg = self.bot.reply_to(call.message, CUSER.Messages.ENTER_YOUR_NAME)
                self.bot.register_next_step_handler(msg, self.handle_name, db_user)
            case _:
                self.start(call.message, db, None)

    def handle_veryfication_token(self, message, db_user: models.User):
        if db_user.user_id == message.from_user.id:
            try:
                input_text = message.text.strip()
                # Convert Persian/Arabic numerals to ASCII digits
                cleaned = convert_persian_numbers(input_text)
                cleaned = re.sub(r"\D+", "", cleaned.strip(), flags=re.UNICODE)
                if not cleaned:
                    msg = self.bot.reply_to(message, CUSER.Messages.INVALID_NUMBER)
                    self.bot.register_next_step_handler(
                        msg, self.handle_veryfication_token
                    )
                    return

                db_user.veryfication_token = cleaned
                msg = self.bot.reply_to(message, CUSER.Messages.ENTER_YOUR_NAME)
                self.bot.register_next_step_handler(msg, self.handle_name, db_user)
            except:
                self.acccount_register(message)
        return

    def handle_name(self, message, db_user: models.User):
        if db_user.user_id == message.from_user.id:
            try:
                cleaned = re.sub(
                    r"[0-9\W_]+", " ", message.text.strip(), flags=re.UNICODE
                )
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                if not cleaned:
                    msg = self.bot.reply_to(message, CUSER.Messages.INVALID_NAME)
                    self.bot.register_next_step_handler(msg, self.handle_name, db_user)
                    return
                db_user.name = cleaned
                msg = self.bot.reply_to(message, CUSER.Messages.ENTER_YOUR_SURNAME)
                self.bot.register_next_step_handler(msg, self.handle_surname, db_user)
            except:
                # raise ValueError("Invalid input. Please enter a valid name.")
                self.acccount_register(message)
        return

    @inject
    def handle_surname(
        self, message, db_user: models.User, db: Session = Dependency(get_db)
    ):
        if db_user.user_id == message.from_user.id:
            try:
                cleaned = re.sub(
                    r"[0-9\W_]+", " ", message.text.strip(), flags=re.UNICODE
                )
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                if not cleaned:
                    msg = self.bot.reply_to(message, CUSER.Messages.INVALID_SURNAME)
                    self.bot.register_next_step_handler(
                        msg, self.handle_surname, db_user
                    )
                    return
                db_user.surname = cleaned
                msg = self.bot.reply_to(message, CUSER.Messages.ENTER_CARD_NUMBER)
                self.bot.register_next_step_handler(msg, self.handle_card_number, db_user)

            except:
                self.acccount_register(message)
                # raise ValueError("Invalid input. Please enter a valid surname.")
        return

        # self.bot.register_next_step_handler(msg, handle_phone_number)
    @inject
    def handle_card_number(self,message, db_user: models.User,db: Session = Dependency(get_db)):
        if db_user.user_id == message.from_user.id:
            try:
                cleaned = re.sub(r"\D+", "", message.text.strip(),flags=re.UNICODE)
                cleaned = convert_persian_numbers(cleaned)
                if not cleaned or len(cleaned) != 16:
                    msg = self.bot.reply_to(message, CUSER.Messages.INVALID_CARD_NUMBER)
                    self.bot.register_next_step_handler(msg, self.handle_card_number, db_user)
                    return
                db_user.card_number = cleaned
                db.add(db_user)
                db.commit()
                keyboard = ReplyKeyboardMarkup(
                    resize_keyboard=True, one_time_keyboard=True
                ).add(KeyboardButton(CUSER.Buttons.SHEAR, request_contact=True))
                msg = self.bot.reply_to(
                    message, CUSER.Messages.SHEAR_YOUR_NUMBER, reply_markup=keyboard
                )
            except Exception as e:
              raise Exception(f"Error in handle_card_number: {e}")  
        return

    @inject
    def handle_phone_number(self, message, db=Dependency(get_db)):
        user_db = db.query(models.User).filter_by(user_id=message.from_user.id).first()
        if not user_db:
            self.bot.send_message(
                message.chat.id,
                "You need to register first. Use /start.",
            )
            return
        elif user_db.phone_number:
            return
        elif all(user_db.name and user_db.surname) and not user_db.phone_number:
            user_db.phone_number = message.contact.phone_number
            user_db.is_active = True
            if user_db.account_type == models.UserType.GENERAL:
                user_db.is_verified = models.VerificationStatus.VERIFIED
            else:
                user_db.is_verified = models.VerificationStatus.PENDING
           
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
            self.bot.send_message(
                message.from_user.id, CUSER.Messages.SUCCESSFUL_REGISTRATION
            )
            self.bot.send_message(
                message.from_user.id,
                CUSER.Messages.WELLCOME_BACK,
                reply_markup=keyboard,
            )
            first_message_data = self.user_boarding.get(message.from_user.id)
            if first_message_data:
                first_message = first_message_data["first_message"]
                for i in range(first_message, message.message_id + 1):
                    self.bot.delete_message(message.chat.id, i)
                self.user_boarding.pop(message.from_user.id, None)

    def session_date(self, call, db):
        date_str = call.data.split(":")[-1]
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
                callback_data = encode_json({
                    "session_id": s.id,
                    "session_date": date_str,
                })
                keyboard.add(
                    InlineKeyboardButton(
                        btn_text, callback_data=f"BOOK:{callback_data}"
                    )
                )
        keyboard.add(InlineKeyboardButton("بازگشت", callback_data="SHOW_SESSIONS"))
        self.bot.edit_message_text(
            msg,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard,
        )

    def book_session(self, call, db):
        recive_data = call.data.split(":")[-1]
        decoded_data = decode_json(recive_data)
        
        session = db.query(models.Session).filter_by(id=decoded_data.get("session_id")).first()
        if not session:
            self.bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )
            return
        # Show cost and ask for confirmation
        user = db.query(models.User).filter_by(user_id=call.from_user.id).first()
        if user.is_verified == models.VerificationStatus.VERIFIED:
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
                "تایید و پرداخت", callback_data=f"PAYMENT:{decoded_data.get('session_id')}"
            ),
            InlineKeyboardButton(
                "بازگشت به پنل سانس ها", callback_data=f"SESSION_DATE:{decoded_data.get('session_date')}"
            ),
        )
        day_name_en = day_name[session.session_date.weekday()]
        day_name_fa = PERSIAN_DAY_NAMES.get(day_name_en, day_name_en)
        self.bot.edit_message_text(
            f"اطلاعات سانس انتخابی روز {day_name_fa}:\n{Gregorian(session.session_date).persian_string()} {session.time_slot}\nمبلغ: {cost}تومان\nمی‌خواهید این سانس را رزرو کنید؟",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
        )

    def start_payment(self, call, db):
        session_id = int(call.data.split(":")[-1])
        session = db.query(models.Session).filter_by(id=session_id).first()
        if session and session.available:
            # Check if the user is verified
            user = db.query(models.User).filter_by(user_id=call.from_user.id).first()
            if user.is_verified == models.VerificationStatus.VERIFIED:
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

            # Send invoice to the user (this is a placeholder, actual implementation may vary)
            admin_card_number = db.query(models.User).filter_by(role=models.UserRole.ADMIN).first().card_number
            self.bot.send_invoice(
                call.from_user.id,
                title="پرداخت هزینه سانس",
                description=f"سانس: {Gregorian(session.session_date).persian_string()} {session.time_slot}",
                provider_token=admin_card_number,
                prices=[
                    LabeledPrice(label="هزینه سانس", amount=cost * 10)  # Amount in IRR
                ],
                currency="IRR",
                invoice_payload=str(payment.id),
            )
        else:
            self.bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )

    @inject
    def pre_checkout_query(self, pre_checkout_query, db: Session = Dependency(get_db)):
        # Always accept pre-checkout queries for now
        # You can add validation logic here if needed
        try:
            # Get payment details from payload
            payment_id = pre_checkout_query.invoice_payload
            payment = db.query(models.Payment).filter_by(id=payment_id).first()

            if payment:
                # Accept the pre-checkout query
                payment.verified = models.VerificationStatus.PENDING
                db.commit()
                db.refresh(payment)
                self.bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
            else:
                # Reject if payment not found
                self.bot.answer_pre_checkout_query(
                    pre_checkout_query.id,
                    ok=False,
                    error_message="Payment record not found. Please try again.",
                )
        except Exception as e:
            # Log the error and reject the query
            print(f"Error in pre_checkout_query: {e}")
            self.bot.answer_pre_checkout_query(
                pre_checkout_query.id,
                ok=False,
                error_message="An error occurred during payment processing. Please try again.",
            )

    @inject
    def verify_payment(self, message, db: Session = Dependency(get_db)):
        # Get payment details from payload
        payment_id = message.successful_payment.invoice_payload
        payment = db.query(models.Payment).filter_by(id=payment_id).first()
        if payment:
            # Update payment status
            payment.verified = models.VerificationStatus.VERIFIED
            payment.shipping_option_id = message.successful_payment.shipping_option_id

            db.commit()
            db.refresh(payment)
            self.bot.send_message(
                payment.user_id, "پرداخت با موفقیت انجام و سانس با موفقیت رزرو شد."
            )

    def report_all_payment(self, call, db):
        generating_msg = self.bot.send_message(
                call.message.chat.id,
                "⏳ در حال ایجاد سانس‌ها برای ۳۰ روز آینده...",
            )
        # get user all payment and send him pdf version of exel file
        payments = db.query(models.Payment).filter_by(user_id=call.from_user.id).all()
        if not payments:
            self.bot.send_message(call.message.chat.id, "No payment history found.")
            return
        # Create a DataFrame from payment data
        payment_data = []
        for payment in payments:
            # Get session details for this payment
            session = db.query(models.Session).filter_by(id=payment.session_id).first()

            # Format date for better readability
            payment_date = payment.payment_date.date()
            persian_amount = convert_english_numbers(payment.amount)
            payment_data.append(
                {
                    "شماره پیگیری": payment.shipping_option_id,
                    "تاریخ پرداخت": Gregorian(payment_date).persian_string(),
                    "تاریخ سانس": Gregorian(session.session_date).persian_string(),
                    "زمان سانس": session.time_slot if session else "N/A",
                    "مبلغ پرداختی": f"{persian_amount}تومان",
                }
            )

        # Create Excel file in memory
        output_excel = BytesIO()
        df = pd.DataFrame(payment_data)
        df.to_excel(output_excel, index=False)
        output_excel.seek(0)

        # Send the Excel file
        file_date = Gregorian(datetime.datetime.now().date()).persian_string()
        final_msg = f"✅ گزارش با موفقیت ایجاد شد"
        self.bot.edit_message_text(
            final_msg,
            call.message.chat.id,
            generating_msg.message_id,
        )
        self.bot.send_document(
            call.message.chat.id,
            output_excel,
            visible_file_name=f"تاریخچه پرداخت [{file_date}].xlsx",
            caption="تاریخچه پرداخت های شما",
        )
        def delete_message():
                try:
                    self.bot.delete_message(
                        call.message.chat.id, generating_msg.message_id
                    )
                except Exception as e:
                    # Ignore deletion errors (e.g., message already deleted)
                    print(f"Error deleting message: {e}")
                    pass

        timer = threading.Timer(7.0, delete_message)  # Increased delay slightly
        timer.start()

    def resent_payments(self, call, db):
        # get user three resent payment
        payments = (
            db.query(models.Payment)
            .filter_by(user_id=call.from_user.id)
            .order_by(models.Payment.payment_date.desc())
            .limit(3)
            .all()
        )
        msg = "سه پرداخت اخیر شما\n"
        buttons = InlineKeyboardMarkup()
        if payments:
            for payment in payments:
                buttons.add(
                    InlineKeyboardButton(
                        f"شماره پیگیری: {payment.shipping_option_id}",
                        callback_data=f"RESENT_PAYMENT:{payment.id}",
                    )
                )
        else:
            msg += "پرداختی یافت نشد"
        buttons.add(InlineKeyboardButton("بازگشت", callback_data="PAYMENT_HISTORY"))
        self.bot.edit_message_text(
            msg,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=buttons,
        )
        return
    def payment_details(self,call,db):
        payment_id = call.data.split(":")[-1]
        payment = db.query(models.Payment).filter_by(id=payment_id).first()
        if not payment:
            self.bot.answer_callback_query(
                call.id, "This payment is no longer available.", show_alert=True
            )
            return
        session = db.query(models.Session).filter_by(id=payment.session_id).first()
        if not session:
            self.bot.answer_callback_query(
                call.id, "This session is no longer available.", show_alert=True
            )
            return
        # print(type(payment.payment_date))
        payment_date =Gregorian(payment.payment_date.date()).persian_string()
        session_date = Gregorian(session.session_date).persian_string()
        amount = convert_english_numbers(payment.amount)
        msg = "جزئیات پرداخت\n"
        msg += f"شماره پیگیری: {payment.shipping_option_id}\n"
        msg += f"تاریخ پرداخت: {payment_date}\n"
        msg += f"تاریخ سانس: {session_date}\n"
        msg += f"زمان سانس: {session.time_slot}\n"
        msg += f"مبلغ پرداختی: {amount} تومان"
        buttons = InlineKeyboardMarkup()
        buttons.add(
            InlineKeyboardButton(
                "بازگشت", callback_data="REPORT_RECENT_PAYMENTS"
            )
        )
        self.bot.edit_message_text(
            msg,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=buttons
            )
   

    def show_sessions(self, message, db, call=None):
        user_id = call.from_user.id if call else message.from_user.id
        user_db = db.query(models.User).filter_by(user_id=user_id).first()
        if not user_db:
            if call:
                self.bot.edit_message_text(
                    "برای استفاده از ربات باید ابتدا ثبت نام کنید. برای ثبت نام از دستور /start استفاده کنید.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )
            else:
                self.bot.send_message(
                    message.chat.id,
                    "برای استفاده از ربات باید ابتدا ثبت نام کنید. برای ثبت نام از دستور /start استفاده کنید.",
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
            if call:
                self.bot.edit_message_text(
                    "برای سه روز آینده سانسی برای زمین وجود ندارد",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )
            else:
                self.bot.send_message(
                    message.chat.id, "برای سه روز آینده سانسی برای زمین وجود ندارد"
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
                    f"{day_name_fa}", callback_data=f"SESSION_DATE:{date}"
                )
            )
        keyboard.add(
            InlineKeyboardButton(
                "🔃 بازنشانی", callback_data="SHOW_SESSIONS"
            )
        )
        if call:
            self.bot.edit_message_text(
                msg,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=keyboard,
            )
        else:
            self.bot.send_message(message.chat.id, msg, reply_markup=keyboard)
        return

    def show_profile(self, message, db):
        user_db = db.query(models.User).filter_by(user_id=message.from_user.id).first()
        if not user_db:
            self.bot.send_message(
                message.chat.id,
                "You need to register first. Use /start.",
            )
            return
        status = {
            models.VerificationStatus.VERIFIED: "🟢 تایید شده",
            models.VerificationStatus.PENDING: "🟡 در حال بررسی",
            models.VerificationStatus.REJECTED: "🔴 رد شده",
        }
        account_type = {
            models.UserType.EMPLOYEE: "👨‍💼 کارمندی",
            models.UserType.STUDENT: "👨‍🎓 دانشجویی",
            models.UserType.GENERAL: "🤵 عمومی",
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
        self.bot.send_message(message.chat.id, msg, parse_mode="Markdown")
        return

    def payment_history(self, message, db,call=None):
        if call:
            user_id = call.from_user.id
            message_id = call.message.message_id
            chat_id = call.message.chat.id
        else:
            user_id = message.from_user.id
            message_id = message.message_id
            chat_id = message.chat.id
        user_db = db.query(models.User).filter_by(user_id=user_id).first()
        if not user_db:
            self.bot.send_message(
                chat_id, "You need to register first. Use /start."
            )
            return
        payments = db.query(models.Payment).filter_by(user_id=user_id).first()
        if not payments:
            self.bot.send_message(chat_id, "تاریخچه پرداختی برای شما وجود ندارد")
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
        if call:
            self.bot.edit_message_text(
                msg,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=keyboard,
            )
        else:
            self.bot.send_message(chat_id, msg, reply_markup=keyboard)
        return
