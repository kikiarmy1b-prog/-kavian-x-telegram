import os
import json
import subprocess
import feedparser
import requests

RSS_URL = "https://xcancel.com/KavianCoin/rss"
STATE_FILE = "last_post.json"

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def get_last_id():
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("last_id")
    except Exception:
        return None


def save_last_id(post_id):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_id": post_id}, f)


def get_posts():
    print("Checking Kavian RSS feed...")

    feed = feedparser.parse(RSS_URL)

    if feed.bozo and not feed.entries:
        raise RuntimeError(
            f"RSS feed could not be read: {feed.bozo_exception}"
        )

    posts = []

    for entry in feed.entries:
        post_id = (
            entry.get("id")
            or entry.get("guid")
            or entry.get("link")
        )

        link = entry.get("link", "")

        title = entry.get("title", "").strip()

        if not post_id or not link:
            continue

        posts.append({
            "id": post_id,
            "text": title,
            "link": link
        })

    return posts


def send_to_telegram(post):
    text = post["text"]

    if not text:
        text = "New post from @KavianCoin"

    message = (
        "🟣 KAVIAN\n\n"
        f"{text}\n\n"
        f"🔗 {post['link']}"
    )

    response = requests.post(
        TELEGRAM_URL,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False
        },
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram error: {result}"
        )

    print(f"Sent to Telegram: {post['link']}")


def save_state_and_push():
    try:
        subprocess.run(
            ["git", "config", "user.name", "github-actions[bot]"],
            check=True
        )

        subprocess.run(
            [
                "git",
                "config",
                "user.email",
                "41898282+github-actions[bot]@users.noreply.github.com"
            ],
            check=True
        )

        subprocess.run(
            ["git", "add", STATE_FILE],
            check=True
        )

        result = subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "Update Kavian forwarder state"
            ],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            subprocess.run(
                ["git", "push"],
                check=True
            )

            print("Saved forwarding state.")

        else:
            print("No state changes to commit.")

    except Exception as e:
        print(f"Warning: Could not save state to GitHub: {e}")


def main():
    posts = get_posts()

    if not posts:
        print("No posts found in RSS feed.")
        return

    print(f"Found {len(posts)} RSS post(s).")

    # RSS feeds normally return newest first.
    # Reverse so we process old -> new.
    posts.reverse()

    last_id = get_last_id()

    # First run:
    # Send only the newest post so we don't flood Telegram
    # with old posts.
    if last_id is None:
        newest = posts[-1]

        print("First run detected.")
        print(f"Sending newest post: {newest['link']}")

        send_to_telegram(newest)

        save_last_id(newest["id"])
        save_state_and_push()

        return

    # Find posts after the last forwarded post.
    new_posts = []
    found_last = False

    for post in posts:
        if post["id"] == last_id:
            found_last = True
            continue

        if found_last:
            new_posts.append(post)

    # If the previous post is no longer in the RSS feed,
    # don't send the entire feed again.
    if not found_last:
        newest = posts[-1]

        if newest["id"] != last_id:
            print("Previous post is no longer in RSS.")
            print(f"Sending newest post: {newest['link']}")

            send_to_telegram(newest)

            save_last_id(newest["id"])
            save_state_and_push()
        else:
            print("No new post.")

        return

    if not new_posts:
        print("No new Kavian posts.")
        return

    print(f"Found {len(new_posts)} new post(s).")

    for post in new_posts:
        send_to_telegram(post)

    # Save the newest forwarded post.
    save_last_id(new_posts[-1]["id"])

    # Persist the state in the GitHub repository.
    save_state_and_push()


if __name__ == "__main__":
    main()
