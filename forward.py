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


# ============================================================
# STATE
# ============================================================

def load_state():

    if not STATE_FILE.exists():
        return {
            "initialized": False,
            "last_id": None
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return {
            "initialized": False,
            "last_id": None
        }


def save_state(state):

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ============================================================
# DOWNLOAD X PROFILE
# ============================================================

def download_profile():

    print("")
    print("Downloading:")
    print(X_URL)
    print("")

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


# ============================================================
# HTML CLEANING
# ============================================================

def clean_text(value):

    if not value:
        return ""

    value = html.unescape(value)

    # Remove HTML
    value = re.sub(
        r"<[^>]+>",
        "",
        value
    )

    # Normalize whitespace
    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


# ============================================================
# EXTRACT TWEETS
# ============================================================

def extract_posts(page):

    posts = []

    # X currently renders tweets as:
    #
    # <article ... data-tweet-id="123">
    #
    # We capture each article separately.

    articles = re.findall(
        r'<article\b[^>]*data-tweet-id="(\d+)"[^>]*>(.*?)</article>',
        page,
        flags=re.IGNORECASE | re.DOTALL
    )

    print("")
    print("Tweet articles found:", len(articles))

    for tweet_id, article in articles:

        # ----------------------------------------------------
        # Date
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # URL
        # ----------------------------------------------------

        url_match = re.search(
            r'itemProp="url"\s+content="https://x\.com/[^"]+/status/\d+"',
            article,
            flags=re.IGNORECASE
        )

        if url_match:

            url = re.search(
                r'https://x\.com/[^"]+/status/\d+',
                url_match.group(0)
            ).group(0)

        else:

            url = (
                f"https://x.com/{USERNAME}/status/"
                f"{tweet_id}"
            )

        # ----------------------------------------------------
        # Tweet text
        # ----------------------------------------------------

        text = ""

        # Schema.org articleBody is preferred.
        body_match = re.search(
            r'itemProp="articleBody"[^>]*>(.*?)</div>',
            article,
            flags=re.IGNORECASE | re.DOTALL
        )

        if body_match:
            text = clean_text(
                body_match.group(1)
            )

        # Try meta content if articleBody wasn't found.
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

        # ----------------------------------------------------
        # Detect replies
        # ----------------------------------------------------

        is_reply = False

        if re.search(
            r'Replying to',
            article,
            flags=re.IGNORECASE
        ):
            is_reply = True

        # ----------------------------------------------------
        # Detect retweets
        # ----------------------------------------------------

        is_retweet = False

        if re.search(
            r'Reposted by|Retweeted by|reposted',
            article,
            flags=re.IGNORECASE
        ):
            is_retweet = True

        # ----------------------------------------------------
        # Save
        # ----------------------------------------------------

        posts.append({
            "id": tweet_id,
            "url": url,
            "text": text,
            "published": published,
            "is_reply": is_reply,
            "is_retweet": is_retweet
        })

    return posts


# ============================================================
# SORT POSTS
# ============================================================

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

            # Snowflake IDs generally increase with time.
            return int(post["id"])

    return sorted(
        posts,
        key=sort_key
    )


# ============================================================
# TELEGRAM
# ============================================================

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

    telegram_url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        telegram_url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": False
        },
        timeout=30
    )

    if response.status_code != 200:

        raise RuntimeError(
            "Telegram error: "
            f"{response.status_code} "
            f"{response.text}"
        )

    print(
        "Telegram sent:",
        post["id"]
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("==========================================")
    print("KAVIAN X → TELEGRAM")
    print("==========================================")
    print("")
    print(
        f"Monitoring @{USERNAME}"
    )

    state = load_state()

    page = download_profile()

    posts = extract_posts(page)

    if not posts:

        raise RuntimeError(
            "No tweet articles found."
        )

    # --------------------------------------------------------
    # Remove duplicates
    # --------------------------------------------------------

    unique = {}

    for post in posts:
        unique[post["id"]] = post

    posts = list(
        unique.values()
    )

    # --------------------------------------------------------
    # Sort oldest → newest
    # --------------------------------------------------------

    posts = sort_posts(posts)

    print("")
    print(
        "Unique posts:",
        len(posts)
    )

    for post in posts:

        print(
            post["id"],
            post["published"],
            post["url"]
        )

    newest = posts[-1]

    # --------------------------------------------------------
    # FIRST RUN
    #
    # Don't send existing posts.
    # Save newest as baseline.
    # --------------------------------------------------------

    if not state.get("initialized"):

        state = {
            "initialized": True,
            "last_id": newest["id"]
        }

        save_state(state)

        print("")
        print("FIRST RUN")
        print(
            "Baseline saved:",
            newest["id"]
        )

        print(
            "No Telegram message sent."
        )

        return

    last_id = state.get(
        "last_id"
    )

    # --------------------------------------------------------
    # Find last known post
    # --------------------------------------------------------

    last_index = None

    for index, post in enumerate(posts):

        if post["id"] == last_id:

            last_index = index

            break

    # --------------------------------------------------------
    # Safety mode
    #
    # If X no longer shows the old post,
    # don't send everything.
    # --------------------------------------------------------

    if last_index is None:

        print("")
        print(
            "Previous post not found "
            "in current X page."
        )

        print(
            "SAFETY MODE:"
            " updating baseline only."
        )

        state["last_id"] = newest["id"]

        save_state(state)

        return

    # --------------------------------------------------------
    # New posts
    # --------------------------------------------------------

    new_posts = posts[
        last_index + 1:
    ]

    # --------------------------------------------------------
    # Filter replies and retweets
    # --------------------------------------------------------

    new_posts = [
        post
        for post in new_posts
        if not post["is_reply"]
        and not post["is_retweet"]
    ]

    if not new_posts:

        print("")
        print(
            "No new original KAVIAN posts."
        )

        return

    print("")
    print(
        "NEW ORIGINAL POSTS:",
        len(new_posts)
    )

    # --------------------------------------------------------
    # Send oldest → newest
    # --------------------------------------------------------

    for post in new_posts:

        print("")
        print(
            "Sending:",
            post["url"]
        )

        send_telegram(post)

    # --------------------------------------------------------
    # Save newest post
    # --------------------------------------------------------

    state["last_id"] = new_posts[-1]["id"]

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
