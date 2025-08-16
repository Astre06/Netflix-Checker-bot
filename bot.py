import os
import io
import json
import certifi
import requests
import asyncio
from itertools import count
from concurrent.futures import ThreadPoolExecutor

from http.cookies import SimpleCookie
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ----- Config via env -----
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # e.g. https://your-service.onrender.com/webhook
PORT = int(os.environ.get("PORT", "10000"))

# Match your original script’s Requests CA bundle behavior
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# --- thread-safe counter for workingN.txt filenames ---
_file_counter = count(1)
executor = ThreadPoolExecutor(max_workers=8)

SECURE_HTTPONLY_NAMES = {"NetflixId", "SecureNetflixId"}

# ---------- utils (ported from your file) ----------
def _parse_cookie_header_format(cookie_str: str):
    cookie = SimpleCookie()
    cookie.load(cookie_str)
    return {key: morsel.value for key, morsel in cookie.items()}

def parse_cookie(cookie_str: str):
    """
    Accept either:
      1) Single-line Cookie header: "a=1; b=2"
      2) JSON array (EditThisCookie-like) with objects having name/value
    Returns dict {name: value}
    """
    cookie_str = cookie_str.strip()
    if cookie_str.startswith('[') or cookie_str.startswith('{'):
        try:
            data = json.loads(cookie_str)
            if isinstance(data, dict):
                data = [data]
            if isinstance(data, list):
                out = {}
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
        r = requests.get('https://www.netflix.com/browse',
                         headers=headers, cookies=cookie_dict, timeout=7)
        # Valid if not seeing login page / redirected to login
        return not ('Sign In' in r.text or 'login' in r.url.lower())
    except Exception:
        return False

def _cookie_dict_to_json_style(cookie_dict):
    """
    Convert {name:value} -> JSON-array style like your original,
    with secure/httpOnly=True for NetflixId/SecureNetflixId.
    """
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

def make_working_file_bytes(cookie_dict, idx: int) -> bytes:
    payload = _cookie_dict_to_json_style(cookie_dict)
    content = json.dumps(payload, ensure_ascii=False, separators=(',', ': ')) + "\n"
    # Return bytes so we can send without writing to disk
    return content.encode("utf-8")

# ---------- Telegram bot handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send me a .txt file where each line is a cookie string.\n"
        "I’ll test each cookie and send you a separate working<N>.txt for each valid one."
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return

    # Only accept text/plain or .txt names
    if doc.mime_type != "text/plain" and not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text("Please send a .txt file.")
        return

    await update.message.reply_text("Received file. Checking cookies… This may take a bit depending on the file size.")

    tg_file = await doc.get_file()
    file_bytes = await tg_file.download_as_bytearray()
    text = file_bytes.decode("utf-8", errors="ignore")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    total = len(lines)
    if total == 0:
        await update.message.reply_text("The file was empty.")
        return

    valid_count = 0
    idx_local = count(1)  # fresh counter per upload, for the file names we return

    # Process in threads to keep responsiveness
    loop = asyncio.get_running_loop()

    async def process_one(cookie_str: str):
        cookie_dict = await loop.run_in_executor(executor, parse_cookie, cookie_str)
        ok = await loop.run_in_executor(executor, is_valid_cookie, cookie_dict)
        if not ok:
            return None
        n = next(idx_local)
        content_bytes = await loop.run_in_executor(executor, make_working_file_bytes, cookie_dict, n)
        return n, content_bytes

    # Run with limited concurrency to be polite
    SEM = asyncio.Semaphore(10)
    async def sem_task(s):
        async with SEM:
            return await process_one(s)

    tasks = [sem_task(s) for s in lines]
    for fut in asyncio.as_completed(tasks):
        result = await fut
        if result is None:
            continue
        n, content_bytes = result
        valid_count += 1

        # Send as a Telegram document (working<n>.txt)
        f = io.BytesIO(content_bytes)
        f.name = f"working{n}.txt"
        await update.message.reply_document(document=InputFile(f))

    await update.message.reply_text(f"Done. Valid cookies: {valid_count}/{total}")

def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN env var is required")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    if WEBHOOK_URL:
        # webhook mode for Render
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=f"{WEBHOOK_URL}/webhook",
            drop_pending_updates=True
        )
    else:
        # local dev (polling)
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
