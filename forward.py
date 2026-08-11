import os
import re
import json
import time
import html
import hashlib
import requests
import xml.etree.ElementTree as ET
from pathlib import Path

# ============================================================
# KAVIAN X -> TELEGRAM
# No X API
# No RSSHub
# New posts only
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

USERNAME = "KavianCoin"

# Public Nitter-style RSS sources.
# We try them in order.
RSS_SOURCES = [
    f"https://nitter.miningtcup.me/{USERNAME}/rss",
    f"https://nitter.poast.org/{USERNAME}/rss",
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
        "application/xml, text/xml, text/html, */*"
    ),
}


# ============================================================
# STATE
# ============================================================

def load_state():
    if not STATE_FILE.exists():
        return {
            "initialized": False,
            "last_id": None,
            "last_link": None
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "initialized": False,
            "last_id": None,
            "last_link": None
        }


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ============================================================
# TELEGRAM
# ============================================================

def send_to_telegram(text):

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "Missing secret: TELEGRAM_BOT_TOKEN"
        )

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "Missing secret: TELEGRAM_CHAT_ID"
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": False
    }

    response = requests.post(
        url,
        json=payload,
        timeout=30
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Telegram error {response.status_code}: "
            f"{response.text}"
        )

    print("Telegram message sent successfully.")


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(value):

    if not value:
        return ""

    value = html.unescape(value)

    # Remove HTML tags
    value = re.sub(
        r"<[^>]*>",
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
# EXTRACT RSS ITEMS WITH REGEX
#
# This is deliberately more tolerant than XML parsing.
# Some public Nitter instances return imperfect XML.
# ============================================================

def parse_feed_lenient(xml_text):

    posts = []

    # --------------------------------------------------------
    # First try normal XML.
    # --------------------------------------------------------

    try:

        root = ET.fromstring(xml_text)

        for item in root.findall(".//item"):

            title = ""
            link = ""
            guid = ""
            description = ""

            title_node = item.find("title")
            if title_node is not None and title_node.text:
                title = title_node.text

            link_node = item.find("link")
            if link_node is not None and link_node.text:
                link = link_node.text

            guid_node = item.find("guid")
            if guid_node is not None and guid_node.text:
                guid = guid_node.text

            desc_node = item.find("description")
            if desc_node is not None:
                description = "".join(
                    desc_node.itertext()
                )

            post_id = (
                guid.strip()
                if guid
                else link.strip()
            )

            if not post_id:
                post_id = hashlib.sha256(
                    (
                        title +
                        description
                    ).encode("utf-8")
                ).hexdigest()

            posts.append({
                "id": post_id,
                "title": clean_text(title),
                "link": link.strip(),
                "description": clean_text(description)
            })

        if posts:
            print(
                f"Normal XML parser found "
                f"{len(posts)} post(s)."
            )

            return posts

    except ET.ParseError as e:

        print(
            "Normal XML parser failed."
        )

        print(
            f"XML error: {e}"
        )

        print(
            "Trying tolerant parser..."
        )

    # --------------------------------------------------------
    # TOLERANT REGEX PARSER
    # --------------------------------------------------------

    item_matches = re.findall(
        r"<item\b[^>]*>(.*?)</item\s*>",
        xml_text,
        flags=re.IGNORECASE | re.DOTALL
    )

    print(
        f"Tolerant parser found "
        f"{len(item_matches)} item block(s)."
    )

    for item in item_matches:

        def extract_tag(tag):

            match = re.search(
                rf"<{tag}\b[^>]*>(.*?)</{tag}\s*>",
                item,
                flags=re.IGNORECASE | re.DOTALL
            )

            if not match:
                return ""

            return match.group(1).strip()

        title = extract_tag("title")

        link = extract_tag("link")

        guid = extract_tag("guid")

        description = extract_tag(
            "description"
        )

        # Sometimes the link is wrapped in CDATA
        link = re.sub(
            r"<!\[CDATA\[(.*?)\]\]>",
            r"\1",
            link,
            flags=re.DOTALL
        )

        title = re.sub(
            r"<!\[CDATA\[(.*?)\]\]>",
            r"\1",
            title,
            flags=re.DOTALL
        )

        description = re.sub(
            r"<!\[CDATA\[(.*?)\]\]>",
            r"\1",
            description,
            flags=re.DOTALL
        )

        link = html.unescape(link).strip()

        title = clean_text(title)

        description = clean_text(
            description
        )

        guid = clean_text(guid)

        post_id = (
            guid
            or link
        )

        if not post_id:
            post_id = hashlib.sha256(
                (
                    title +
                    description
                ).encode("utf-8")
            ).hexdigest()

        if not link:
            continue

        posts.append({
            "id": post_id,
            "title": title,
            "link": link,
            "description": description
        })

    return posts


# ============================================================
# GET POSTS
# ============================================================

def get_posts():

    last_error = None

    for source in RSS_SOURCES:

        print("")
        print("------------------------------------------")
        print("Trying:")
        print(source)
        print("------------------------------------------")

        try:

            response = requests.get(
                source,
                headers=HEADERS,
                timeout=30,
                allow_redirects=True
            )

            print(
                "HTTP status:",
                response.status_code
            )

            if response.status_code != 200:

                print(
                    "Source unavailable."
                )

                continue

            if not response.text.strip():

                print(
                    "Empty response."
                )

                continue

            posts = parse_feed_lenient(
                response.text
            )

            if not posts:

                print(
                    "No posts could be extracted."
                )

                continue

            print("")
            print(
                f"SUCCESS: {len(posts)} "
                f"post(s) extracted."
            )

            return posts

        except Exception as e:

            last_error = e

            print(
                "Source failed:",
                e
            )

    raise RuntimeError(
        "No usable X feed source is available. "
        f"Last error: {last_error}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("==========================================")
    print("KAVIAN X -> TELEGRAM FORWARDER")
    print("==========================================")
    print("")
    print(
        f"Checking @{USERNAME}..."
    )
    print("")

    # --------------------------------------------------------
    # Check secrets
    # --------------------------------------------------------

    if not TELEGRAM_BOT_TOKEN:

        raise RuntimeError(
            "Missing GitHub secret "
            "TELEGRAM_BOT_TOKEN"
        )

    if not TELEGRAM_CHAT_ID:

        raise RuntimeError(
            "Missing GitHub secret "
            "TELEGRAM_CHAT_ID"
        )

    # --------------------------------------------------------
    # Load state
    # --------------------------------------------------------

    state = load_state()

    # --------------------------------------------------------
    # Get X posts
    # --------------------------------------------------------

    posts = get_posts()

    if not posts:

        print(
            "No posts found."
        )

        return

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
    # Newest first
    # --------------------------------------------------------

    print("")
    print(
        f"Total unique posts: {len(posts)}"
    )

    newest = posts[-1]

    print("")
    print("Newest post:")
    print(
        newest["link"]
    )

    # --------------------------------------------------------
    # FIRST RUN
    #
    # Existing newest post becomes baseline.
    # Nothing gets sent.
    # --------------------------------------------------------

    if not state.get(
        "initialized",
        False
    ):

        state["initialized"] = True

        state["last_id"] = (
            newest["id"]
        )

        state["last_link"] = (
            newest["link"]
        )

        save_state(state)

        print("")
        print(
            "FIRST RUN."
        )

        print(
            "Existing post saved "
            "as baseline."
        )

        print(
            "Nothing sent to Telegram."
        )

        print(
            "Waiting for the next "
            "new KAVIAN post."
        )

        return

    # --------------------------------------------------------
    # Find last known post
    # --------------------------------------------------------

    last_id = state.get(
        "last_id"
    )

    found_last = False

    new_posts = []

    for post in posts:

        if post["id"] == last_id:

            found_last = True

            continue

        if found_last:

            new_posts.append(
                post
            )

    # --------------------------------------------------------
    # Safety:
    # If old post disappeared from feed,
    # DON'T send the whole feed.
    # --------------------------------------------------------

    if not found_last:

        print("")
        print(
            "Previous post is no longer "
            "visible in the feed."
        )

        print(
            "Safety mode:"
            " updating baseline only."
        )

        state["last_id"] = (
            newest["id"]
        )

        state["last_link"] = (
            newest["link"]
        )

        save_state(state)

        return

    # --------------------------------------------------------
    # Nothing new
    # --------------------------------------------------------

    if not new_posts:

        print("")
        print(
            "No new KAVIAN posts."
        )

        return

    # --------------------------------------------------------
    # Send new posts
    # --------------------------------------------------------

    print("")
    print(
        f"NEW POSTS FOUND: "
        f"{len(new_posts)}"
    )

    for post in new_posts:

        title = post["title"]

        if not title:

            title = "New KAVIAN post"

        message = (
            "🟣 KAVIAN\n\n"
            f"{title}\n\n"
            f"🔗 {post['link']}"
        )

        print("")
        print(
            "Sending to Telegram:"
        )

        print(
            post["link"]
        )

        send_to_telegram(
            message
        )

        time.sleep(2)

    # --------------------------------------------------------
    # Save newest successfully sent post
    # --------------------------------------------------------

    state["last_id"] = (
        new_posts[-1]["id"]
    )

    state["last_link"] = (
        new_posts[-1]["link"]
    )

    save_state(state)

    print("")
    print("==========================================")
    print("SUCCESS")
    print("==========================================")
    print(
        f"Sent {len(new_posts)} "
        f"new post(s)."
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
