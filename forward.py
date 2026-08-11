import os
import json
import subprocess
import feedparser
import requests

# ============================================================
# KAVIAN X -> TELEGRAM FORWARDER
# ============================================================

RSS_URL = (
    "https://rsshub.app/twitter/user/KavianCoin/"
    "excludeReplies=1&includeRts=0&forceWebApi=1"
)

STATE_FILE = "last_post.json"

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


# ============================================================
# STATE
# ============================================================

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


# ============================================================
# RSS
# ============================================================

def get_posts():
    print("Checking Kavian X feed...")
    print(RSS_URL)

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

        description = entry.get("description", "").strip()

        # RSSHub normally puts the tweet text in title/description.
        text = title

        if not text and description:
            text = description

        if not post_id or not link:
            continue

        posts.append({
            "id": post_id,
            "text": text,
            "link": link
        })

    return posts


# ============================================================
# TELEGRAM
# ============================================================

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

    if not response.ok:
        print("Telegram response:")
        print(response.text)

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram API error: {result}"
        )

    print("Successfully sent to Telegram.")
    print(post["link"])


# ============================================================
# SAVE STATE TO GITHUB
# ============================================================

def save_state_to_github():

    try:

        subprocess.run(
            [
                "git",
                "config",
                "user.name",
                "github-actions[bot]"
            ],
            check=True
        )

        subprocess.run(
            [
                "git",
                "config",
                "user.email",
                "41898282+github-actions[bot]"
                "@users.noreply.github.com"
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

        if result.returncode != 0:
            print("No state changes to commit.")
            return

        subprocess.run(
            ["git", "push"],
            check=True
        )

        print("Forwarding state saved.")

    except Exception as e:
        print(f"Warning: could not save state: {e}")


# ============================================================
# MAIN
# ============================================================

def main():

    posts = get_posts()

    if not posts:
        print("No posts found.")
        return

    print(f"Found {len(posts)} post(s).")

    # RSS feeds normally return newest first.
    # Reverse so oldest -> newest.
    posts.reverse()

    last_id = get_last_id()

    # --------------------------------------------------------
    # FIRST RUN
    # --------------------------------------------------------

    if last_id is None:

        newest = posts[-1]

        print("First run detected.")
        print(f"Sending newest post:")
        print(newest["link"])

        send_to_telegram(newest)

        save_last_id(newest["id"])
        save_state_to_github()

        return

    # --------------------------------------------------------
    # FIND NEW POSTS
    # --------------------------------------------------------

    found_last = False
    new_posts = []

    for post in posts:

        if post["id"] == last_id:
            found_last = True
            continue

        if found_last:
            new_posts.append(post)

    # --------------------------------------------------------
    # OLD POST NO LONGER IN FEED
    # --------------------------------------------------------

    if not found_last:

        newest = posts[-1]

        if newest["id"] != last_id:

            print(
                "Previous post is no longer in the feed."
            )

            print(
                f"Sending newest post: {newest['link']}"
            )

            send_to_telegram(newest)

            save_last_id(newest["id"])
            save_state_to_github()

        else:

            print("No new post.")

        return

    # --------------------------------------------------------
    # NO NEW POSTS
    # --------------------------------------------------------

    if not new_posts:

        print("No new Kavian posts.")
        return

    # --------------------------------------------------------
    # SEND NEW POSTS
    # --------------------------------------------------------

    print(
        f"Found {len(new_posts)} new post(s)."
    )

    for post in new_posts:

        send_to_telegram(post)

    # Save newest forwarded post.
    save_last_id(new_posts[-1]["id"])

    save_state_to_github()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
