# Safe Telegram Cookie Parser Bot

This bot accepts `.txt` files via Telegram and replies with normalized cookie outputs. It does **not** contact any third-party services.

## ✅ What It Does
- Accepts text files containing cookie strings (one per line)
- Parses and formats each valid cookie into JSON
- Sends a new `.txt` file back for each valid entry

## 🚫 What It Doesn't Do
- No HTTP requests to Netflix or any website
- No credential validation or login attempts

## 🔧 Setup Instructions

1. Install Python 3.9+
2. Clone this repo and run:
```bash
pip install -r requirements.txt
```
3. Copy `.env.example` to `.env` and add your Telegram bot token.
4. Run the bot:
```bash
python bot.py
```

## ✉️ Usage
- Start the bot with `/start`
- Upload a `.txt` file with cookies (e.g., `a=1; b=2` or EditThisCookie format)
- You'll receive one `normalized<N>.txt` file for each valid line

## 📁 File Structure
- `bot.py` - main Telegram bot logic
- `.env.example` - template for environment variables
- `requirements.txt` - dependencies
- `.gitignore` - ignore local secrets and cache files

## License
MIT — do whatever you want, just don't misuse it.
