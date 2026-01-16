"""Mastodon Scrabble Bot - replies with German Scrabble points."""

import os
import re
import time
from html import unescape

from dotenv import load_dotenv
from mastodon import Mastodon

from scrabble import calculate_points, get_language_name

load_dotenv()

MASTODON_INSTANCE = "https://mastodon.social"
BT_FIRST_SAID_ACCOUNT = "bt_first_said"
POLL_INTERVAL = 60  # seconds


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = unescape(text)
    return text.strip()


def extract_word_from_mention(content: str) -> str | None:
    """Extract a single word from a mention, ignoring @handles."""
    text = strip_html(content)
    # Remove @mentions
    text = re.sub(r'@\w+(@[\w.]+)?', '', text)
    words = text.split()
    # Return the first word if exactly one word remains
    if len(words) == 1:
        return words[0]
    # If multiple words, return the first non-empty word
    if words:
        return words[0]
    return None


def is_single_word(content: str) -> bool:
    """Check if the content is exactly one word."""
    text = strip_html(content)
    words = text.split()
    return len(words) == 1


def format_response(word: str, language: str | None = None) -> str:
    """Format the German response with Scrabble points using post language."""
    points, lang = calculate_points(word, language)
    clean_word = word.upper()
    lang_name = get_language_name(lang)
    if points == 1:
        return f'Das Wort "{clean_word}" ist 1 Scrabble-Punkt wert ({lang_name}).'
    return f'Das Wort "{clean_word}" ist {points} Scrabble-Punkte wert ({lang_name}).'


def main():
    access_token = os.getenv("MASTODON_BOT_ACCESS_TOKEN")
    if not access_token:
        print("Fehler: MASTODON_BOT_ACCESS_TOKEN nicht in .env gefunden.")
        return

    mastodon = Mastodon(
        access_token=access_token,
        api_base_url=MASTODON_INSTANCE,
    )

    # Get the account ID of @bt_first_said
    bt_first_said = mastodon.account_search(BT_FIRST_SAID_ACCOUNT, limit=1)
    if not bt_first_said:
        print(f"Fehler: Account @{BT_FIRST_SAID_ACCOUNT} nicht gefunden.")
        return
    bt_first_said_id = bt_first_said[0]["id"]

    processed_mentions: set[str] = set()
    processed_bt_posts: set[str] = set()

    # Get initial state to avoid replying to old posts
    notifications = mastodon.notifications(types=["mention"], limit=40)
    for n in notifications:
        processed_mentions.add(n["status"]["id"])

    bt_statuses = mastodon.account_statuses(bt_first_said_id, limit=40)
    for status in bt_statuses:
        processed_bt_posts.add(status["id"])

    print(f"Bot gestartet. Überwache Erwähnungen und @{BT_FIRST_SAID_ACCOUNT}...")

    while True:
        try:
            # Check for new mentions
            notifications = mastodon.notifications(types=["mention"], limit=20)
            for notification in notifications:
                status = notification["status"]
                status_id = status["id"]

                if status_id in processed_mentions:
                    continue

                processed_mentions.add(status_id)
                word = extract_word_from_mention(status["content"])

                if word:
                    post_lang = status.get("language")
                    response = format_response(word, post_lang)
                    mastodon.status_reply(
                        to_status=status,
                        status=response,
                        visibility=status["visibility"],
                    )
                    print(f"Antwort auf Erwähnung: {word} -> {response}")

            # Check @bt_first_said for new single-word posts
            bt_statuses = mastodon.account_statuses(bt_first_said_id, limit=10)
            for status in bt_statuses:
                status_id = status["id"]

                if status_id in processed_bt_posts:
                    continue

                processed_bt_posts.add(status_id)
                content = status["content"]

                if is_single_word(content):
                    word = strip_html(content).strip()
                    post_lang = status.get("language")
                    response = format_response(word, post_lang)
                    mastodon.status_reply(
                        to_status=status,
                        status=response,
                        visibility=status["visibility"],
                    )
                    print(f"Antwort auf @{BT_FIRST_SAID_ACCOUNT}: {word} -> {response}")

        except Exception as e:
            print(f"Fehler: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
