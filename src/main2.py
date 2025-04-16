from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from sqlalchemy.orm import Session
from src.repositories.models import User, UserType  # Replace with your actual imports
from src.utils.dependency  import inject, Dependency  # Replace with your DI setup
from src.repositories.utils import get_db
import logging
from src.repositories.database import engine
from src.repositories import models
import os
import pathlib
from dotenv import load_dotenv

# Enable logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define conversation states
SELECT_USER_TYPE, ENTER_NAME, ENTER_SURNAME, SHARE_CONTACT = range(4)

# Global state to track user onboarding
user_onboarding_state = {}

@inject
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Session = Dependency(get_db)):
    telegram_id = update.effective_user.id
    user = db.query(User).filter_by(telegram_id=telegram_id).first()
    
    if user:
        await update.message.reply_text("You are already registered.")
        return ConversationHandler.END
    
    # Initialize user state
    user_onboarding_state[telegram_id] = {}
    
    # Create inline keyboard
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("University Employee", callback_data="user_type_employee")],
        [InlineKeyboardButton("University Student", callback_data="user_type_student")],
        [InlineKeyboardButton("Other", callback_data="user_type_other")],
    ])
    
    await update.message.reply_text("Welcome! Please select your user type:", reply_markup=markup)
    return SELECT_USER_TYPE

@inject
async def callback_center(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Session = Dependency(get_db)):
    query = update.callback_query
    await query.answer()  # Acknowledge the callback
    
    telegram_id = query.from_user.id
    if telegram_id not in user_onboarding_state:
        await query.message.reply_text("Session expired. Please start again with /start.")
        return ConversationHandler.END
    
    if query.data.startswith("user_type_"):
        user_type = query.data.replace("user_type_", "")
        user_onboarding_state[telegram_id]["user_type"] = user_type
        await query.message.reply_text("Please enter your name:")
        return ENTER_NAME
    
    return SELECT_USER_TYPE

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    if telegram_id not in user_onboarding_state:
        await update.message.reply_text("Session expired. Please start again with /start.")
        return ConversationHandler.END
    
    user_onboarding_state[telegram_id]["name"] = update.message.text.strip()
    await update.message.reply_text("Please enter your surname:")
    return ENTER_SURNAME

async def handle_surname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    if telegram_id not in user_onboarding_state:
        await update.message.reply_text("Session expired. Please start again with /start.")
        return ConversationHandler.END
    
    user_onboarding_state[telegram_id]["surname"] = update.message.text.strip()
    
    # Create contact-sharing button
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("Share phone number", request_contact=True)],
    ])
    
    await update.message.reply_text("Please share your phone number:", reply_markup=markup)
    return SHARE_CONTACT

@inject
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Session = Dependency(get_db)):
    telegram_id = update.effective_user.id
    if telegram_id not in user_onboarding_state:
        await update.message.reply_text("Session expired. Please start again with /start.")
        return ConversationHandler.END
    
    contact = update.message.contact
    user_onboarding_state[telegram_id]["phone_number"] = contact.phone_number
    
    # Save user to database
    data = user_onboarding_state[telegram_id]
    user = User(
        telegram_id=telegram_id,
        name=data["name"],
        surname=data["surname"],
        phone_number=data["phone_number"],
        user_type=UserType[data["user_type"]],
    )
    
    db.add(user)
    db.commit()
    
    await update.message.reply_text(
        "Registration complete! You can now use the bot.",
        reply_markup=None  # Remove keyboard
    )
    
    # Clean up state
    user_onboarding_state.pop(telegram_id, None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user_onboarding_state.pop(telegram_id, None)
    await update.message.reply_text("Registration cancelled.")
    return ConversationHandler.END


models.Base.metadata.create_all(bind=engine)


BASE_DIR = pathlib.Path(__file__).parent.absolute()
load_dotenv(BASE_DIR / ".env")


def main():
    # Replace with your bot token
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise ValueError("BOT_TOKEN not found in environment variables")
    # Create the Application
    application = Application.builder().token(bot_token).build()
    
    # Define the conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_handler)],
        states={
            SELECT_USER_TYPE: [CallbackQueryHandler(callback_center, pattern="^user_type_")],
            ENTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            ENTER_SURNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_surname)],
            SHARE_CONTACT: [MessageHandler(filters.CONTACT, handle_contact)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Add the conversation handler to the application
    application.add_handler(conv_handler)
    
    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()