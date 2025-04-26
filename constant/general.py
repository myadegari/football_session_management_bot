from dataclasses import dataclass
from typing import Final
from repositories import models

@dataclass(
    frozen=True,
)
class Messagaes:
    """Messages for the application."""

    # General messages
    WELCOME: Final[str] = "Welcome to the application!"
    GOODBYE: Final[str] = "Thank you for using the application! Goodbye!"
    REPITED_REGISTER: Final[str] = ""
    # Error messages
    ERROR: Final[str] = "An error occurred. Please try again."
    INVALID_INPUT: Final[str] = "Invalid input. Please enter a valid value."

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
STATUS = {
        models.VerificationStatus.VERIFIED: "🟢 تایید شده",
        models.VerificationStatus.PENDING: "🟡 در حال بررسی",
        models.VerificationStatus.REJECTED: "🔴 رد شده",
}
ACCOUNT_TYPE = {
    models.UserType.EMPLOYEE: "👨‍💼 کارمندی",
    models.UserType.STUDENT: "👨‍🎓 دانشجویی",
    models.UserType.GENERAL: "🤵 عمومی",
}