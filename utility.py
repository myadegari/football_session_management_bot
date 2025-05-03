import json
import zlib
import base64


def convert_persian_numbers(input_text):
    persian_to_english = {
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }

    cleaned = input_text
    for persian, english in persian_to_english.items():
        cleaned = cleaned.replace(persian, english)
    return cleaned

def convert_english_numbers(input_text):
    english_to_persian = {
        "0": "۰",
        "1": "۱",
        "2": "۲",
        "3": "۳",
        "4": "۴",
        "5": "۵",
        "6": "۶",
        "7": "۷",
        "8": "۸",
        "9": "۹",
    }
    cleaned = str(input_text)
    for english, persian in english_to_persian.items():
        cleaned = cleaned.replace(english, persian)
    return cleaned

# Encode: JSON → string → bytes → compressed → base64
def encode_json(data):
    json_str = json.dumps(data)
    compressed = zlib.compress(json_str.encode('utf-8'))
    encoded = base64.urlsafe_b64encode(compressed).decode('utf-8')
    return encoded

# Decode: base64 → compressed → bytes → string → JSON
def decode_json(encoded_str):
    compressed = base64.urlsafe_b64decode(encoded_str.encode('utf-8'))
    json_str = zlib.decompress(compressed).decode('utf-8')
    return json.loads(json_str)