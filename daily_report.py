"""Send one daily job-monitor health summary via Telegram."""
import os
from health import load_health, summarize
from monitor import send

def main():
    token=os.environ.get("TELEGRAM_BOT_TOKEN")
    chat=os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise SystemExit("Missing Telegram GitHub Actions secrets")
    send(token,chat,summarize(load_health()))
    print("Daily report delivered.")

if __name__ == "__main__":
    main()
