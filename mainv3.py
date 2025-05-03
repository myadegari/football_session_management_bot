"""
Football Session Management Bot - Main Application

This module initializes and runs the Telegram bot for managing football sessions,
handling user registration, session booking, and administrative functions.
"""

import os
import pathlib
from typing import Callable, Dict, Optional

import telebot
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from constant import user as CUSER
from repositories import models
from repositories.database import engine
from repositories.utils import get_db
from user_flow import admin, user
from utils.dependency import Dependency, inject


class CallbackHandler:
    """Handles callback queries from Telegram inline buttons."""

    def __init__(self, user_flow: user.UserFlow, admin_flow: admin.UserFlow):
        self.user_flow = user_flow
        self.admin_flow = admin_flow
        self.handlers: Dict[str, Callable] = self._register_handlers()

    def _register_handlers(self) -> Dict[str, Callable]:
        """Register all callback handlers with their corresponding prefixes."""
        return {
            "ACCOUNT_TYPE:": lambda call, db: self.user_flow.acccount_register(call),
            "SESSION_DATE:": lambda call, db: self.user_flow.session_date(call, db),
            "ADMIN_START": lambda call, db: self.admin_flow.start(call),
            "SHOW_SESSIONS": lambda call, db: self.user_flow.show_sessions(message=None,db=db,call=call),
            "ADMIN_CHANGE_BASED_COST": lambda call, db: self.admin_flow.change_based_cost(
                call, db
            ),
            "ADMIN_GENERATE_REPORT": lambda call, db: self.admin_flow.generate_report(
                call, db
            ),
            "ADMIN_SESSION_DATE:": lambda call, db: self.admin_flow.seesion_date(
                call, db
            ),
            "ADMIN_MANAGE_SESSION:": lambda call, db: self.admin_flow.manage_session(
                call, db
            ),
            "ADMIN_SESSION_REFUND:": lambda call, db: self.admin_flow.session_refund(
                call, db
            ),
            "ADMIN_DEACTIVATE_SESSION:": lambda call, db: self.admin_flow.deactive_session(
                call, db
            ),
            "ADMIN_ACTIVATE_SESSION:": lambda call, db: self.admin_flow.active_session(
                call, db
            ),
            "BOOK:": lambda call, db: self.user_flow.book_session(call, db),
            "PAYMENT_HISTORY": lambda call, db: self.user_flow.payment_history(
                None, db, call
            ),
            "PAYMENT:": lambda call, db: self.user_flow.start_payment(call, db),
            "REPORT_RECENT_PAYMENTS": lambda call, db: self.user_flow.resent_payments(
                call, db
            ),
            "RESENT_PAYMENT:": lambda call, db: self.user_flow.payment_details(
                call, db
            ),
            # "CONFIRM_": lambda call, db: self.user_flow.confirm_session(call, db),
            "ADMIN_VIEW_USER_BOOKINGS:": lambda call, db: self.admin_flow.view_user_bookings(
                call, db
            ),
            "ADMIN_VIEW_USER_PAYMENTS:": lambda call, db: self.admin_flow.view_user_payments(
                call, db
            ),
            "ADMIN_VIEW_USER_VERIFICATION:": lambda call, db: self.admin_flow.user_verification(call, db),
            "ADMIN_VIEW_USER:": lambda call, db: self.admin_flow.view_user_details(
                call, db
            ),
            "ADMIN_VIEW_USERS_PAGE:": lambda call, db: self.admin_flow.view_users(
                call, db
            ),
            "ADMIN_VIEW_SESSIONS": lambda call, db: self.admin_flow.view_sessions(
                call, db
            ),
            "ADMIN_GENERATE_SESSIONS": lambda call, db: self.admin_flow.generate_sessions(
                call, db
            ),
            "REPORT_ALL_PAYMENTS": lambda call, db: self.user_flow.report_all_payment(
                call, db
            ),
            "ADMIN_CHANGE_BASED_COST:": lambda call, db: self.admin_flow.change_cost(
                call, db
            ),
        }

    def handle(self, call: telebot.types.CallbackQuery, db: Session) -> bool:
        """
        Process a callback query by finding and executing the appropriate handler.

        Args:
            call: The callback query from Telegram
            db: Database session

        Returns:
            bool: True if a handler was found and executed, False otherwise
        """
        for prefix, handler in self.handlers.items():
            if call.data == prefix or (
                prefix.endswith(":") and call.data.startswith(prefix)
            ):
                handler(call, db)
                return True
        return False


class MessageHandler:
    """Handles text messages from users."""

    def __init__(self, user_flow: user.UserFlow):
        self.user_flow = user_flow
        self.handlers = {
            CUSER.Buttons.SHOW_PROFILE: self.user_flow.show_profile,
            CUSER.Buttons.SHOW_SESSIONS: self.user_flow.show_sessions,
            CUSER.Buttons.SHOW_PAYMENT_HISTORY: self.user_flow.payment_history,
        }

    def handle(self, message: telebot.types.Message, db: Session) -> None:
        """
        Process a text message by finding and executing the appropriate handler.

        Args:
            message: The message from Telegram
            db: Database session
        """
        handler = self.handlers.get(message.text)
        if handler:
            handler(message, db)


class FootballSessionBot:
    """Main bot class that initializes and runs the Telegram bot."""

    def __init__(self):
        self.setup_environment()
        self.setup_database()
        self.bot = self.create_bot()
        self.user_flow = user.UserFlow(self.bot)
        self.admin_flow = admin.UserFlow(self.bot)
        self.callback_handler = CallbackHandler(self.user_flow, self.admin_flow)
        self.message_handler = MessageHandler(self.user_flow)
        self.register_handlers()

    @staticmethod
    def setup_environment() -> None:
        """Load environment variables from .env file."""
        base_dir = pathlib.Path(__file__).parent.absolute()
        load_dotenv(base_dir / ".env")

    @staticmethod
    def setup_database() -> None:
        """Initialize database and set up initial data if needed."""
        models.Base.metadata.create_all(bind=engine)
        setup_payment_categories()

    @staticmethod
    def create_bot() -> telebot.TeleBot:
        """Create and configure the Telegram bot instance."""
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            raise ValueError("BOT_TOKEN not found in environment variables")
        return telebot.TeleBot(bot_token)

    def register_handlers(self) -> None:
        """Register message and callback handlers with the bot."""

        @self.bot.message_handler(commands=["start"])
        @inject
        def start_handler(
            message: telebot.types.Message, db: Session = Dependency(get_db)
        ):
            self.user_flow.start(message, db, self.admin_flow.start)

        @self.bot.callback_query_handler(func=lambda call: True)
        @inject
        def callback_center(
            call: telebot.types.CallbackQuery, db: Session = Dependency(get_db)
        ):
            self.callback_handler.handle(call, db)

        @self.bot.message_handler(func=lambda message: True)
        @inject
        def message_center(
            message: telebot.types.Message, db: Session = Dependency(get_db)
        ):
            self.message_handler.handle(message, db)

    def run(self) -> None:
        """Start the bot and keep it running."""
        self.bot.polling(none_stop=True, interval=0)


@inject
def setup_payment_categories(db: Session = Dependency(get_db)) -> None:
    """
    Initialize payment categories in the database if they don't exist.

    Args:
        db: Database session
    """
    existing_categories = db.query(models.PaymentCategory).all()
    if existing_categories:
        return

    categories = {
        models.UserType.EMPLOYEE: 10000,
        models.UserType.STUDENT: 8000,
        models.UserType.GENERAL: 12000,
    }

    for account_type, cost in categories.items():
        category = models.PaymentCategory(account_type=account_type, session_cost=cost)
        db.add(category)

    db.commit()


if __name__ == "__main__":
    football_bot = FootballSessionBot()
    football_bot.run()
