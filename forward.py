import os
import re
import json
import time
import hashlib
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

# ============================================================
# KAVIAN X -> TELEGRAM FORWARDER
# No X API
# No RSSHub
# New posts only
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

USERNAME = "KavianCoin"

# We try several public X/Nitter-style sources.
# If one is unavailable, the next one is tried.
RSS_SOURCES = [
    f"https://nitter.poast.org/{USERNAME}/rss",
    f"https://nitter.miningtcup.me/{USERNAME}/rss",
    f"https://nt.vern.cc/{USERNAME}/rss",
    f"https://xcancel.com/{USERNAME}/rss",
]

STATE_FILE = Path("kavian_state.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "application/rss+xml, application/atom+xml, "
        "application/xml, text/xml, text/html;q=0.9, */*;q=0.8"
    ),
}


# ------------------------------------------------------------
# State
# ------------------------------------------------------------

def load_state():
    if not STATE_FILE.exists():
        return {
            "initialized": False,
            "last_id": None,
            "last_link": None,
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "initialized": False,
            "last_id": None,
            "last_link": None,
        }


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ------------------------------------------------------------
# Telegram
# ------------------------------------------------------------

def send_to_telegram(text):
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN secret is missing")

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID secret is missing")

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": False,
    }

    response = requests.post(
        url,
        json=payload,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"Telegram error {response.status_code}: {response.text}"
        )

    print("Telegram message sent successfully.")


# ------------------------------------------------------------
# RSS parsing
# ------------------------------------------------------------

def clean_text(value):
    if not value:
        return ""

    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("&amp;", "&")
    value = value.replace("&lt;", "<")
    value = value.replace("&gt;", ">")
    value = value.replace("&quot;", '"')
    value = value.replace("&#39;", "'")

    return value.strip()


def get_element_text(element, names):
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return found.text.strip()

    return ""


def parse_feed(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise RuntimeError(f"Invalid XML/RSS response: {e}")

    posts = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title = get_element_text(item, ["title"])
        link = get_element_text(item, ["link"])
        guid = get_element_text(item, ["guid"])
        pub_date = get_element_text(
            item,
            ["pubDate", "published", "updated"]
        )
        description = get_element_text(
            item,
            ["description", "summary"]
        )

        post_id = guid or link

        if not post_id:
            post_id = hashlib.sha256(
                (title + description).encode("utf-8")
            ).hexdigest()

        posts.append({
            "id": post_id,
            "title": clean_text(title),
            "link": link.strip(),
            "date": pub_date,
            "description": clean_text(description),
        })

    # Atom
    atom_entries = root.findall(
        ".//{http://www.w3.org/2005/Atom}entry"
    )

    for entry in atom_entries:
        title = get_element_text(
            entry,
            ["{http://www.w3.org/2005/Atom}title"]
        )

        entry_id = get_element_text(
            entry,
            ["{http://www.w3.org/2005/Atom}id"]
        )

        published = get_element_text(
            entry,
            [
                "{http://www.w3.org/2005/Atom}published",
                "{http://www.w3.org/2005/Atom}updated",
            ],
        )

        link = ""

        for link_element in entry.findall(
            "{http://www.w3.org/2005/Atom}link"
        ):
            href = link_element.attrib.get("href")
            rel = link_element.attrib.get("rel", "alternate")

            if href and rel == "alternate":
                link = href
                break

            if href and not link:
                link = href

        description = get_element_text(
            entry,
            [
                "{http://www.w3.org/2005/Atom}summary",
                "{http://www.w3.org/2005/Atom}content",
            ],
        )

        post_id = entry_id or link

        if not post_id:
            post_id = hashlib.sha256(
                (title + description).encode("utf-8")
            ).hexdigest()

        posts.append({
            "id": post_id,
            "title": clean_text(title),
            "link": link.strip(),
            "date": published,
            "description": clean_text(description),
        })

    return posts


# ------------------------------------------------------------
# Find a working source
# ------------------------------------------------------------

def get_posts():
    last_error = None

    for source in RSS_SOURCES:
        print("")
        print("Trying:")
        print(source)

        try:
            response = requests.get(
                source,
                headers=HEADERS,
                timeout=25,
                allow_redirects=True,
            )

            print("HTTP status:", response.status_code)

            if response.status_code != 200:
                print("Source unavailable.")
                continue

            if not response.text.strip():
                print("Empty response.")
                continue

            posts = parse_feed(response.text)

            if not posts:
                print("Feed returned zero posts.")
                continue

            print(f"SUCCESS: found {len(posts)} post(s).")
            return posts

        except Exception as e:
            last_error = e
            print("Source failed:", e)

    raise RuntimeError(
        "No public X feed source is currently available. "
        f"Last error: {last_error}"
    )


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():

    print("==========================================")
    print("KAVIAN X -> TELEGRAM FORWARDER")
    print("==========================================")
    print(f"Checking @{USERNAME}...")
    print("")

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "Missing GitHub secret: TELEGRAM_BOT_TOKEN"
        )

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "Missing GitHub secret: TELEGRAM_CHAT_ID"
        )

    state = load_state()

    posts = get_posts()

    # Newest first
    posts = list(reversed(posts))

    newest = posts[-1]

    print("")
    print("Newest post:")
    print(newest["link"])

    # --------------------------------------------------------
    # FIRST RUN
    #
    # Do NOT send the existing newest post.
    # Save it as the baseline.
    # This guarantees "new posts only".
    # --------------------------------------------------------

    if not state.get("initialized"):
        state["initialized"] = True
        state["last_id"] = newest["id"]
        state["last_link"] = newest["link"]

        save_state(state)

        print("")
        print("FIRST RUN DETECTED.")
        print("Existing post saved as baseline.")
        print("Nothing was sent to Telegram.")
        print("Future new posts will be forwarded.")

        return

    last_id = state.get("last_id")

    # --------------------------------------------------------
    # Find posts newer than the saved post
    # --------------------------------------------------------

    new_posts = []

    found_last = False

    for post in posts:
        if post["id"] == last_id:
            found_last = True
            continue

        if found_last:
            new_posts.append(post)

    # If the previous ID isn't in the feed anymore,
    # don't blindly send everything.
    if not found_last:
        print("")
        print("Previous post is no longer in the feed.")
        print("Updating baseline without sending old posts.")

        state["last_id"] = newest["id"]
        state["last_link"] = newest["link"]

        save_state(state)

        return

    if not new_posts:
        print("")
        print("No new KAVIAN posts.")
        return

    print("")
    print(f"NEW POSTS FOUND: {len(new_posts)}")

    # --------------------------------------------------------
    # Send oldest -> newest
    # --------------------------------------------------------

    for post in new_posts:

        message = (
            "🟣 KAVIAN\n\n"
            f"{post['title']}\n\n"
            f"🔗 {post['link']}"
        )

        print("")
        print("Sending:")
        print(post["link"])

        send_to_telegram(message)

        # Small delay so Telegram isn't hit repeatedly
        time.sleep(2)

    # --------------------------------------------------------
    # Save newest post
    # --------------------------------------------------------

    state["last_id"] = new_posts[-1]["id"]
    state["last_link"] = new_posts[-1]["link"]

    save_state(state)

    print("")
    print("==========================================")
    print("DONE")
    print("==========================================")


if __name__ == "__main__":
    main()
