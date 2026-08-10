import os
import json
import feedparser
import requests

RSS_URL = "https://xcancel.com/KavianCoin/rss"
STATE_FILE = "last_post.json"

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

headers = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

print("Checking X RSS...")
response = requests.get(RSS_URL, headers=headers, timeout=30)

print("HTTP status:", response.status_code)
print("Content length:", len(response.content))

if response.status_code != 200:
    raise RuntimeError(
        f"XCancel returned HTTP {response.status_code}"
    )

feed = feedparser.parse(response.content)

print("RSS entries:", len(feed.entries))

if not feed.entries:
    raise RuntimeError("RSS feed returned no posts.")

# Load previous state
try:
    with open(STATE_FILE, "r") as f:
        state = json.load(f)
        last_id = state.get("last_id")
except FileNotFoundError:
    last_id = None

entries = list(reversed(feed.entries))

new_posts = []

for entry in entries:
    post_id = entry.get("id") or entry.get("link")

    if not post_id:
        continue

    if post_id == last_id:
        continue

    new_posts.append(entry)

# First run: don't flood Telegram with old posts.
if last_id is None:
    newest = entries[-1]

    post_id = newest.get("id") or newest.get("link")
    text = newest.get("title", "").strip()
    link = newest.get("link", "").strip()

    message = f"🟣 KAVIAN\n\n{text}\n\n🔗 {link}"

    telegram_url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    )

    r = requests.post(
        telegram_url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    print("Telegram status:", r.status_code)
    print(r.text)

    r.raise_for_status()

    with open(STATE_FILE, "w") as f:
        json.dump({"last_id": post_id}, f)

    print("First post forwarded.")
    exit(0)

# Forward new posts oldest → newest
for entry in new_posts:
    post_id = entry.get("id") or entry.get("link")
    text = entry.get("title", "").strip()
    link = entry.get("link", "").strip()

    message = f"🟣 KAVIAN\n\n{text}\n\n🔗 {link}"

    telegram_url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    )

    r = requests.post(
        telegram_url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    print("Telegram status:", r.status_code)
    print(r.text)

    r.raise_for_status()

    with open(STATE_FILE, "w") as f:
        json.dump({"last_id": post_id}, f)

    print("Forwarded:", link)

print("Done.")
