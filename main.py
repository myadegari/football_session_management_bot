import os
import pathlib

import telebot
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from constant import user as CUSER
from repositories import models
from repositories.database import engine

from repositories.utils import get_db
from utils.dependency import Dependency, inject
from user_flow import admin, user


@inject
def setup_payment_categories(db: Session = Dependency(get_db)):
    existing_categories = db.query(models.PaymentCategory).all()
    if existing_categories:
        return
    categories = {
        models.UserType.EMPLOYEE: 10,
        models.UserType.STUDENT: 8,
        models.UserType.GENERAL: 12,
    }
    for account_type, cost in categories.items():
        category = models.PaymentCategory(account_type=account_type, session_cost=cost)
        db.add(category)
    db.commit()



models.Base.metadata.create_all(bind=engine)
setup_payment_categories()

BASE_DIR = pathlib.Path(__file__).parent.absolute()
load_dotenv(BASE_DIR / ".env")

bot_token = os.getenv("BOT_TOKEN")
if not bot_token:
    raise ValueError("BOT_TOKEN not found in environment variables")

bot = telebot.TeleBot(bot_token)

user_boarding = {}

ADMIN_FLOW = admin.UserFlow(bot)
USER_FLOW = user.UserFlow(bot)


@bot.message_handler(commands=["start"])
@inject
def start_handler(message: telebot.types.Message, db: Session = Dependency(get_db)):
    USER_FLOW.start(message, db, ADMIN_FLOW.start)


@bot.callback_query_handler(func=lambda call: True)
@inject
def callback_center(call, db: Session = Dependency(get_db)):
    if call.data.startswith("ACCOUNT_TYPE"):
        USER_FLOW.acccount_register(call)

    if call.data.startswith("SESSION_DATE_"):
        USER_FLOW.session_date(call, db)
    if call.data == "ADMIN_START":
        ADMIN_FLOW.start(call, bot)
    if call.data.startswith("ADMIN_SESSION_DATE_"):
        ADMIN_FLOW.seesion_date(call, db)
    if call.data.startswith("ADMIN_MANAGE_SESSION_"):
        ADMIN_FLOW.manage_session(call, db)
    if call.data.startswith("ADMIN_SESSION_REFUND_"):
        ADMIN_FLOW.session_refund(call, db)
    if call.data.startswith("ADMIN_DEACTIVATE_SESSION_"):
        ADMIN_FLOW.deactive_session(call, db)
    if call.data.startswith("ADMIN_ACTIVATE_SESSION_"):
        ADMIN_FLOW.active_session(call, db)
    if call.data.startswith("BOOK_"):
        USER_FLOW.book_session(call, db)
    if call.data.startswith("CONFIRM_"):
        USER_FLOW.confirm_session(call, db)
    if call.data == "ADMIN_VIEW_USERS_PAGE_1":
        ADMIN_FLOW.view_users(call, db)
    if call.data == "ADMIN_VIEW_SESSIONS":
        ADMIN_FLOW.view_sessions(call, db)
    if call.data == "ADMIN_GENERATE_SESSIONS":
        ADMIN_FLOW.generate_sessions(call, db)
    if call.data == "REPORT_ALL_PAYMENTS":
        USER_FLOW.report_all_payment(call, db)


@bot.message_handler(func=lambda message: True)
@inject
def message_center(message, db: Session = Dependency(get_db)):
    if message.text == CUSER.Buttons.SHOW_PROFILE:
        USER_FLOW.show_profile(message, db)
    if message.text == CUSER.Buttons.SHOW_SESSIONS:
        USER_FLOW.show_sessions(message, db)
    if message.text == CUSER.Buttons.SHOW_PAYMENT_HISTORY:
        USER_FLOW.payment_history(message, db)


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

bot.polling(none_stop=True, interval=0)
