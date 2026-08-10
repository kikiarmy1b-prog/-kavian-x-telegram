import os
import json
import hashlib
import feedparser
import requests

RSS_URL = "https://xcancel.com/KavianCoin/rss"
STATE_FILE = "last_post.json"

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def load_last():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f).get("id")
    except FileNotFoundError:
        return None

def save_last(post_id):
    with open(STATE_FILE, "w") as f:
        json.dump({"id": post_id}, f)

feed = feedparser.parse(RSS_URL)

if not feed.entries:
    print("No X posts found.")
    exit()

# Process oldest → newest
entries = list(reversed(feed.entries))

last_id = load_last()

for entry in entries:
    post_id = entry.get("id") or entry.get("link")

    if not post_id:
        continue

    if post_id == last_id:
        continue

    text = entry.get("title", "").strip()
    link = entry.get("link", "").strip()

    message = f"🟣 KAVIAN\n\n{text}\n\n🔗 {link}"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False
        },
        timeout=30
    )

    response.raise_for_status()

    save_last(post_id)

    print(f"Forwarded: {link}")
