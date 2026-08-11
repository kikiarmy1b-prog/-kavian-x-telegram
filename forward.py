import os
import re
import json
import html
import requests
from pathlib import Path
from datetime import datetime

USERNAME = "KavianCoin"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

STATE_FILE = Path("kavian_state.json")

X_URL = f"https://x.com/{USERNAME}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def load_state():
    if not STATE_FILE.exists():
        return {
            "initialized": False,
            "sent_ids": []
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        # Convert old state format if necessary
        if "sent_ids" not in state:
            old_id = state.get("last_id")
            state["sent_ids"] = [old_id] if old_id else []

        return state

    except Exception:
        return {
            "initialized": False,
            "sent_ids": []
        }


def save_state(state):
    # Keep only the most recent 100 IDs
    state["sent_ids"] = state.get("sent_ids", [])[-100:]

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def download_profile():
    print("")
    print("Downloading:")
    print(X_URL)

    response = requests.get(
        X_URL,
        headers=HEADERS,
        timeout=30
    )

    print("HTTP status:", response.status_code)
    print("Downloaded:", len(response.content), "bytes")

    if response.status_code != 200:
        raise RuntimeError(
            f"X returned HTTP {response.status_code}"
        )

    return response.text


def clean_text(value):
    if not value:
        return ""

    value = html.unescape(value)

    value = re.sub(
        r"<[^>]+>",
        "",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def extract_posts(page):
    posts = []

    articles = re.findall(
        r'<article\b[^>]*data-tweet-id="(\d+)"[^>]*>(.*?)</article>',
        page,
        flags=re.IGNORECASE | re.DOTALL
    )

    print("")
    print("Tweet articles found:", len(articles))

    for tweet_id, article in articles:

        date_match = re.search(
            r'itemProp="datePublished"\s+content="([^"]+)"',
            article,
            flags=re.IGNORECASE
        )

        published = (
            date_match.group(1)
            if date_match
            else ""
        )

        url_match = re.search(
            r'https://x\.com/[^"]+/status/\d+',
            article,
            flags=re.IGNORECASE
        )

        url = (
            url_match.group(0)
            if url_match
            else f"https://x.com/{USERNAME}/status/{tweet_id}"
        )

        text = ""

        # Look for articleBody content
        body_match = re.search(
            r'itemProp="articleBody"[^>]*>(.*?)</div>',
            article,
            flags=re.IGNORECASE | re.DOTALL
        )

        if body_match:
            text = clean_text(
                body_match.group(1)
            )

        # Alternative format
        if not text:
            body_match = re.search(
                r'itemProp="articleBody"\s+content="([^"]*)"',
                article,
                flags=re.IGNORECASE
            )

            if body_match:
                text = clean_text(
                    body_match.group(1)
                )

        is_reply = bool(
            re.search(
                r"Replying to",
                article,
                flags=re.IGNORECASE
            )
        )

        is_retweet = bool(
            re.search(
                r"Reposted by|Retweeted by",
                article,
                flags=re.IGNORECASE
            )
        )

        posts.append({
            "id": tweet_id,
            "url": url,
            "text": text,
            "published": published,
            "is_reply": is_reply,
            "is_retweet": is_retweet
        })

    return posts


def sort_posts(posts):

    def sort_key(post):
        try:
            return datetime.fromisoformat(
                post["published"].replace(
                    "Z",
                    "+00:00"
                )
            )
        except Exception:
            return int(post["id"])

    return sorted(
        posts,
        key=sort_key
    )


def send_telegram(post):

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is missing"
        )

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID is missing"
        )

    text = post["text"]

    if not text:
        text = "New KAVIAN post"

    message = (
        "🟣 KAVIAN\n\n"
        f"{text}\n\n"
        f"🔗 {post['url']}"
    )

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": False
        },
        timeout=30
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Telegram error {response.status_code}: "
            f"{response.text}"
        )

    print(
        "Telegram sent:",
        post["id"]
    )


def main():

    print("")
    print("==========================================")
    print("KAVIAN X -> TELEGRAM")
    print("==========================================")

    state = load_state()

    sent_ids = set(
        state.get("sent_ids", [])
    )

    print("")
    print(
        "Previously sent IDs:",
        len(sent_ids)
    )

    page = download_profile()

    posts = extract_posts(page)

    if not posts:
        raise RuntimeError(
            "No tweet articles found."
        )

    unique = {}

    for post in posts:
        unique[post["id"]] = post

    posts = sort_posts(
        list(unique.values())
    )

    print("")
    print(
        "Unique posts found:",
        len(posts)
    )

    # --------------------------------------------------------
    # FIRST RUN
    #
    # Save ALL currently visible posts as already seen.
    # This prevents old posts from being forwarded.
    # --------------------------------------------------------

    if not state.get("initialized"):

        state["initialized"] = True

        state["sent_ids"] = [
            post["id"]
            for post in posts
        ]

        save_state(state)

        print("")
        print("FIRST RUN")
        print(
            "Saved",
            len(posts),
            "existing posts as baseline."
        )

        print(
            "Nothing sent to Telegram."
        )

        return

    # --------------------------------------------------------
    # Find posts we have never sent
    # --------------------------------------------------------

    new_posts = []

    for post in posts:

        if post["id"] in sent_ids:
            continue

        # Ignore replies
        if post["is_reply"]:
            print(
                "Ignoring reply:",
                post["id"]
            )
            sent_ids.add(post["id"])
            continue

        # Ignore retweets
        if post["is_retweet"]:
            print(
                "Ignoring repost:",
                post["id"]
            )
            sent_ids.add(post["id"])
            continue

        new_posts.append(post)

    # --------------------------------------------------------
    # No new posts
    # --------------------------------------------------------

    if not new_posts:

        print("")
        print(
            "No new KAVIAN posts."
        )

        state["sent_ids"] = list(sent_ids)

        save_state(state)

        return

    # --------------------------------------------------------
    # Send new posts oldest -> newest
    # --------------------------------------------------------

    print("")
    print(
        "NEW POSTS FOUND:",
        len(new_posts)
    )

    for post in new_posts:

        print("")
        print(
            "Sending:",
            post["url"]
        )

        send_telegram(post)

        sent_ids.add(
            post["id"]
        )

    # --------------------------------------------------------
    # Save state ONLY after successful sends
    # --------------------------------------------------------

    state["sent_ids"] = list(
        sent_ids
    )

    save_state(state)

    print("")
    print("==========================================")
    print("SUCCESS")
    print("==========================================")
    print(
        "Forwarded:",
        len(new_posts)
    )


if __name__ == "__main__":
    main()
