"""Mastodon Scrabble Bot - replies with Scrabble points in real-time."""

import os
import re
import json
import time
import logging
from html import unescape

from dotenv import load_dotenv
from mastodon import Mastodon, StreamListener

from scrabble import calculate_points, get_language_name, get_response_template

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("ScrabbleBot")

load_dotenv()


class ScrabbleListener(StreamListener):
    """Mastodon Stream Listener for real-time Scrabble point replies."""

    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    def on_notification(self, notification):
        """Handle new notifications (mentions)."""
        if notification['type'] == 'mention':
            status = notification['status']
            logger.info(f"Notification received: Mention from {status['account']['acct']}")
            self.bot.process_status(status, is_mention=True)

    def on_update(self, status):
        """Handle new statuses in home timeline (followed accounts)."""
        # Check if the status is from the targeted account
        if status['account']['acct'] == self.bot.bt_account_name:
            logger.info(f"Update received: Post from @{self.bot.bt_account_name}")
            self.bot.process_status(status, is_mention=False)


class ScrabbleBot:
    """Core logic and state for the Scrabble Bot."""

    def __init__(self):
        # Configuration from environment variables
        self.mastodon_instance = os.getenv("MASTODON_INSTANCE", "https://mastodon.social")
        self.bt_account_name = os.getenv("BT_FIRST_SAID_ACCOUNT", "bt_first_said")
        self.last_ids_file = os.getenv("LAST_IDS_FILE", "last_ids.json")
        self.access_token = os.getenv("MASTODON_BOT_ACCESS_TOKEN")
        
        # Internal state
        self.mastodon = None
        self.bt_account_id = None
        self.last_mention_id = None
        self.last_bt_id = None

    def setup(self):
        """Initialize Mastodon API and account state."""
        if not self.access_token:
            logger.error("Fehler: MASTODON_BOT_ACCESS_TOKEN nicht in .env gefunden.")
            return False

        self.mastodon = Mastodon(
            access_token=self.access_token,
            api_base_url=self.mastodon_instance,
        )

        # Get the account ID of the target
        results = self.mastodon.account_search(self.bt_account_name, limit=1)
        if not results:
            logger.error(f"Fehler: Account @{self.bt_account_name} nicht gefunden.")
            return False
        
        target_account = results[0]
        self.bt_account_id = target_account["id"]

        # Load persistence state
        self.load_state()
        return True

    def load_state(self):
        """Load last processed IDs."""
        if os.path.exists(self.last_ids_file):
            try:
                with open(self.last_ids_file, 'r') as f:
                    state = json.load(f)
                    self.last_mention_id = state.get("mentions")
                    self.last_bt_id = state.get("bt_posts")
            except (json.JSONDecodeError, IOError):
                logger.warning("Letzte IDs konnten nicht geladen werden, verwende Standardwerte.")

    def save_state(self):
        """Save last processed IDs."""
        try:
            with open(self.last_ids_file, 'w') as f:
                json.dump({
                    "mentions": self.last_mention_id,
                    "bt_posts": self.last_bt_id
                }, f)
        except IOError as e:
            logger.error(f"Fehler beim Speichern der IDs: {e}")

    def strip_html(self, text: str) -> str:
        """Remove HTML tags and decode entities."""
        text = re.sub(r'<[^>]+>', ' ', text)
        text = unescape(text)
        return text.strip()

    def extract_word(self, content: str) -> str | None:
        """Extract a single word from a mention, ignoring @handles."""
        text = self.strip_html(content)
        # Remove @mentions
        text = re.sub(r'@\w+(@[\w.]+)?', '', text)
        words = text.split()
        if words:
            return words[0]
        return None

    def is_single_word(self, content: str) -> bool:
        """Check if the content is exactly one word."""
        text = self.strip_html(content)
        words = text.split()
        return len(words) == 1

    def process_status(self, status, is_mention=False):
        """Process a status and reply if it contains a word."""
        status_id = status["id"]
        
        # Avoid processing older items if we have a state (safety check for stream glitches)
        if is_mention and self.last_mention_id and status_id <= self.last_mention_id:
            return
        if not is_mention and self.last_bt_id and status_id <= self.last_bt_id:
            return

        content = status["content"]
        word = None

        if is_mention:
            word = self.extract_word(content)
            self.last_mention_id = status_id
        elif self.is_single_word(content):
            word = self.strip_html(content).strip()
            self.last_bt_id = status_id

        if word:
            try:
                post_lang = status.get("language")
                points, lang = calculate_points(word, post_lang)
                lang_name = get_language_name(lang, localized=True)
                template = get_response_template(lang, points)
                
                response = template.format(word=word.upper(), points=points, lang=lang_name)
                
                self.mastodon.status_reply(
                    to_status=status,
                    status=response,
                    visibility=status["visibility"],
                )
                logger.info(f"Antwort gesendet: {word} -> {response}")
            except Exception as e:
                logger.error(f"Fehler beim Senden der Antwort: {e}")

        self.save_state()

    def run(self):
        """Start the streaming loop with reconnection logic."""
        if not self.setup():
            return

        logger.info("Bot gestartet. Wechsel zu Real-time Streaming...")
        listener = ScrabbleListener(self)

        while True:
            try:
                # This call blocks while the stream is open
                self.mastodon.stream_user(listener)
            except Exception as e:
                logger.error(f"Stream-Verbindung abgebrochen: {e}")
                logger.info("Versuche Reconnect in 30 Sekunden...")
                time.sleep(30)


if __name__ == "__main__":
    bot = ScrabbleBot()
    bot.run()
