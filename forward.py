import os
import json
import requests
import xml.etree.ElementTree as ET

RSS_URL = "https://xcancel.com/KavianCoin/rss"
STATE_FILE = "last_post.json"

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def get_last_id():
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            return data.get("last_id")
    except Exception:
        return None


def save_last_id(post_id):
    with open(STATE_FILE, "w") as f:
        json.dump({"last_id": post_id}, f)


def get_posts():
    response = requests.get(
        RSS_URL,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)

    posts = []

    for item in root.findall(".//item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        guid = item.findtext("guid", "") or link
        description = item.findtext("description", "")

        text = title.strip()

        if not text and description:
            text = description.strip()

        if guid and link:
            posts.append({
                "id": guid,
                "text": text,
                "link": link
            })

    return posts


def send_to_telegram(text, link):
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


def main():
    posts = get_posts()

    if not posts:
        print("No posts found.")
        return

    # RSS normally returns newest first
    posts = list(reversed(posts))

    last_id = get_last_id()

    if last_id is None:
        # First run: send only the newest post
        post = posts[-1]

        print(f"First run. Sending: {post['link']}")
        send_to_telegram(post["text"], post["link"])
        save_last_id(post["id"])
        return

    new_posts = []

    found_last = False

    for post in posts:
        if post["id"] == last_id:
            found_last = True
            continue

        if found_last:
            new_posts.append(post)

    # If the saved post disappeared from the RSS feed,
    # use the newest post only to avoid flooding Telegram.
    if not found_last:
        newest = posts[-1]

        if newest["id"] != last_id:
            print(f"Previous post not found. Sending newest: {newest['link']}")
            send_to_telegram(newest["text"], newest["link"])
            save_last_id(newest["id"])

        return

    for post in new_posts:
        print(f"Forwarding: {post['link']}")
        send_to_telegram(post["text"], post["link"])

    if new_posts:
        save_last_id(new_posts[-1]["id"])
        print(f"Forwarded {len(new_posts)} new post(s).")
    else:
        print("No new posts.")


if __name__ == "__main__":
    main()
