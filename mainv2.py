import os
import pathlib
from typing import Callable, Optional

import telebot
from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from constant import user as CUSER
from repositories import models
from repositories.database import engine
from repositories.utils import get_db
from utils.dependency import Dependency, inject
from user_flow import admin, user

# Configuration and initialization
BASE_DIR = pathlib.Path(__file__).parent.absolute()
load_dotenv(BASE_DIR / ".env")

# Constants
CALLBACK_PREFIXES = {
    "ACCOUNT_TYPE": "account_register",
    "SESSION_DATE_": "session_date",
    "ADMIN_START": "admin_start",
    "ADMIN_SESSION_DATE_": "admin_session_date",
    "ADMIN_MANAGE_SESSION_": "admin_manage_session",
    "ADMIN_SESSION_REFUND_": "admin_session_refund",
    "ADMIN_DEACTIVATE_SESSION_": "admin_deactivate_session",
    "ADMIN_ACTIVATE_SESSION_": "admin_activate_session",
    "BOOK_": "book_session",
    "CONFIRM_": "confirm_session",
    "ADMIN_VIEW_USERS": "admin_view_users",
    "ADMIN_VIEW_SESSIONS": "admin_view_sessions",
    "ADMIN_GENERATE_SESSIONS": "admin_generate_sessions",
    "REPORT_ALL_PAYMENTS": "report_all_payments"
}


class TelegramBot:
    def __init__(self):
        self._initialize_database()
        self._setup_bot()
        self._setup_flow_handlers()
        self.user_boarding = {}
        
    def _initialize_database(self) -> None:
        """Initialize database tables and setup initial data."""
        models.Base.metadata.create_all(bind=engine)
        self._setup_payment_categories()
        
    def _setup_bot(self) -> None:
        """Configure and initialize the Telegram bot."""
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            raise ValueError("BOT_TOKEN not found in environment variables")
        self.bot = telebot.TeleBot(bot_token)
        
    def _setup_flow_handlers(self) -> None:
        """Initialize user and admin flow handlers."""
        self.admin_flow = admin.UserFlow(self.bot)
        self.user_flow = user.UserFlow(self.bot)
        
    @inject
    def _setup_payment_categories(self, db: Session = Dependency(get_db)) -> None:
        """Setup initial payment categories if they don't exist."""
        try:
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
        except SQLAlchemyError as e:
            db.rollback()
            raise ValueError(f"Failed to setup payment categories: {str(e)}")
            
    def register_handlers(self) -> None:
        """Register all message and callback handlers."""
        # Command handlers
        self.bot.message_handler(commands=["start"])(self.start_handler)
        
        # Callback query handler
        self.bot.callback_query_handler(func=lambda call: True)(self.callback_center)
        
        # Message handler
        self.bot.message_handler(func=lambda message: True)(self.message_center)
        
    def run(self) -> None:
        """Start the bot."""
        self.register_handlers()
        self.bot.polling(none_stop=True)

    @inject
    def start_handler(self, message: telebot.types.Message, db: Session = Dependency(get_db)) -> None:
        """Handle the /start command."""
        self.user_flow.start(message, db, self.admin_flow.start)

    @inject
    def callback_center(self, call, db: Session = Dependency(get_db)) -> None:
        """Central handler for all callback queries."""
        try:
            handler = self._get_callback_handler(call.data)
            if handler:
                handler(call, db)
        except Exception as e:
            self.bot.send_message(call.message.chat.id, f"An error occurred: {str(e)}")
            
    def _get_callback_handler(self, callback_data: str) -> Optional[Callable]:
        """Get the appropriate handler function for a callback query."""
        for prefix, method_name in CALLBACK_PREFIXES.items():
            if callback_data == prefix or callback_data.startswith(prefix):
                if prefix == "ACCOUNT_TYPE":
                    return lambda call, db: self.user_flow.acccount_register(call)
                elif prefix == "SESSION_DATE_":
                    return self.user_flow.session_date
                elif prefix == "ADMIN_START":
                    return lambda call, db: self.admin_flow.start(call, self.bot)
                elif prefix == "ADMIN_SESSION_DATE_":
                    return self.admin_flow.seesion_date
                elif prefix == "ADMIN_MANAGE_SESSION_":
                    return self.admin_flow.manage_session
                elif prefix == "ADMIN_SESSION_REFUND_":
                    return self.admin_flow.session_refund
                elif prefix == "ADMIN_DEACTIVATE_SESSION_":
                    return self.admin_flow.deactive_session
                elif prefix == "ADMIN_ACTIVATE_SESSION_":
                    return self.admin_flow.active_session
                elif prefix == "BOOK_":
                    return self.user_flow.book_session
                elif prefix == "CONFIRM_":
                    return self.user_flow.confirm_session
                elif prefix == "ADMIN_VIEW_USERS":
                    return self.admin_flow.view_users
                elif prefix == "ADMIN_VIEW_SESSIONS":
                    return self.admin_flow.view_sessions
                elif prefix == "ADMIN_GENERATE_SESSIONS":
                    return self.admin_flow.generate_sessions
                elif prefix == "REPORT_ALL_PAYMENTS":
                    return self.user_flow.report_all_payment
        return None

    @inject
    def message_center(self, message, db: Session = Dependency(get_db)) -> None:
        """Central handler for all text messages."""
        try:
            text = message.text
            if text == CUSER.Buttons.SHOW_PROFILE:
                self.user_flow.show_profile(message, db)
            elif text == CUSER.Buttons.SHOW_SESSIONS:
                self.user_flow.show_sessions(message, db)
            elif text == CUSER.Buttons.SHOW_PAYMENT_HISTORY:
                self.user_flow.payment_history(message, db)
        except Exception as e:
            self.bot.send_message(message.chat.id, f"An error occurred: {str(e)}")


if __name__ == "__main__":
    bot = TelegramBot()
    bot.run()