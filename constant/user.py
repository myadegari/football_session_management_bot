from dataclasses import dataclass
from typing import Dict, Final


@dataclass(
    frozen=True,
)
class Buttons:
    EMPLOYEE = {
        "TEXT": "کارمند",
        "CALLBACK_DATA": "ACCOUNT_TYPE_EMPLOYEE",
    }
    STUDENT = {
        "TEXT": "دانشجو",
        "CALLBACK_DATA": "ACCOUNT_TYPE_STUDENT",
    }
    GENERAL = {
        "TEXT": "عمومی",
        "CALLBACK_DATA": "ACCOUNT_TYPE_GENERAL",
    }
    SHEAR = "اشتراک گذاری شماره تلفن"
    SHOW_SESSIONS = "مشاهده سانس ها"
    SHOW_PAYMENT_HISTORY = "مشاهده تاریخچه پرداخت ها"
    SHOW_PROFILE = "مشاهده پروفایل"


@dataclass(
    frozen=True,
)
class Messages:
    SELECT_ACCOUNT_TYPE = "لطفا نوع حساب خود را انتخاب کنید."
    ENTER_PERSONNEL_NUMBER = "لطفا شماره پرسنلی خود را وارد کنید."
    ENTER_STUDENT_NUMBER = "لطفا شماره دانشجویی خود را وارد"
    ENTER_YOUR_NAME = "لطفا نام خود را وارد کنید."
    ENTER_YOUR_SURNAME = "لطفا نام خانوادگی خود را وارد کنید."
    SHEAR_YOUR_NUMBER = "شماره خود را با کلیک بر روی دکمه زیر به اشتراک بگذارید."
    SUCCESSFUL_REGISTRATION = "ثبت نام با موفقیت انجام شد."
    WELLCOME_BACK = "خوش آمدید!"