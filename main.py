"""Mastodon Scrabble Bot - replies with Scrabble points in real-time."""

import os
import re
import json
import time
import logging
import signal
import sys
from html import unescape
from collections import defaultdict
from typing import Dict, List

from dotenv import load_dotenv
from mastodon import Mastodon, StreamListener, MastodonMalformedEventError
from mastodon.errors import MastodonAPIError, MastodonNetworkError, MastodonRatelimitError

from scrabble import (
    calculate_points,
    get_language_name,
    get_response_template,
    get_error_message,
    get_invalid_word_message,
    get_rate_limit_message,
    get_unsupported_language_message,
    is_valid_word,
    is_unsupported_language
)

load_dotenv()

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("ScrabbleBot")


class RateLimiter:
    """Rate limiter using sliding window algorithm."""

    def __init__(self, max_requests: int, time_window: int, enabled: bool = True):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in time window
            time_window: Time window in seconds
            enabled: Whether rate limiting is enabled
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.enabled = enabled
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, user_id: str) -> bool:
        """
        Check if a request from user is allowed.

        Args:
            user_id: The user ID to check

        Returns:
            bool: True if allowed, False if rate limited
        """
        if not self.enabled:
            return True

        current_time = time.time()

        # Clean up old requests outside the time window
        self.requests[user_id] = [
            timestamp for timestamp in self.requests[user_id]
            if current_time - timestamp < self.time_window
        ]

        # Check if user is within rate limit
        if len(self.requests[user_id]) >= self.max_requests:
            logger.warning(f"Rate limit exceeded for user {user_id}: {len(self.requests[user_id])}/{self.max_requests}")
            return False

        # Add current request
        self.requests[user_id].append(current_time)
        return True

    def cleanup_old_entries(self):
        """Remove entries for users who haven't made requests recently."""
        current_time = time.time()
        users_to_remove = []

        for user_id, timestamps in self.requests.items():
            # Remove old timestamps
            self.requests[user_id] = [
                ts for ts in timestamps
                if current_time - ts < self.time_window
            ]

            # Mark empty entries for removal
            if not self.requests[user_id]:
                users_to_remove.append(user_id)

        # Remove empty entries
        for user_id in users_to_remove:
            del self.requests[user_id]

        if users_to_remove:
            logger.debug(f"Cleaned up {len(users_to_remove)} user entries from rate limiter")


def format_response(word: str, language: str | None = None, points: int | None = None, detected_lang: str | None = None) -> str:
    """
    Format the localized response with Scrabble points using post language.

    Args:
        word: The word to format
        language: The language code (optional, will be detected if not provided)
        points: Pre-calculated points (optional, will be calculated if not provided)
        detected_lang: Pre-detected language (optional, will be detected if not provided)

    Returns:
        Formatted response string
    """
    # Calculate points if not provided
    if points is None or detected_lang is None:
        points, detected_lang = calculate_points(word, language)

    clean_word = word.upper()
    lang_name = get_language_name(detected_lang, localized=True)
    template = get_response_template(detected_lang, points)
    return template.format(word=clean_word, points=points, lang=lang_name)


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

    def _dispatch(self, event):
        """Override _dispatch to ignore empty events (heartbeats)."""
        if not event:
            return
        super()._dispatch(event)

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
        self.reconnect_delay = int(os.getenv("RECONNECT_DELAY_SECONDS", "30"))
        self.max_reconnect_attempts = int(os.getenv("MAX_RECONNECT_ATTEMPTS", "0"))

        # Rate limiting configuration
        rate_limit_enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
        rate_limit_max = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "5"))
        rate_limit_window = int(os.getenv("RATE_LIMIT_TIME_WINDOW", "3600"))

        # Internal state
        self.mastodon = None
        self.bt_account_id = None
        self.last_mention_id = None
        self.last_bt_id = None
        self.reconnect_count = 0
        self.shutdown_requested = False
        self.rate_limiter = RateLimiter(rate_limit_max, rate_limit_window, rate_limit_enabled)

    def send_reply_with_retry(self, status, message, max_retries=3):
        """
        Send a reply with retry logic for transient errors.

        Args:
            status: The status to reply to
            message: The message to send
            max_retries: Maximum number of retry attempts

        Returns:
            bool: True if successful, False otherwise
        """
        for attempt in range(max_retries):
            try:
                self.mastodon.status_reply(
                    to_status=status,
                    status=message,
                    visibility=status["visibility"],
                )
                return True
            except MastodonRatelimitError as e:
                # Rate limited - wait and retry
                logger.warning(f"Rate limited, warte vor Retry (Versuch {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(f"Rate limit erreicht nach {max_retries} Versuchen: {e}")
                    return False
            except MastodonNetworkError as e:
                # Network error - retry
                logger.warning(f"Netzwerkfehler, versuche erneut (Versuch {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    logger.error(f"Netzwerkfehler nach {max_retries} Versuchen: {e}")
                    return False
            except MastodonAPIError as e:
                # API error - likely not transient, don't retry
                logger.error(f"API Fehler beim Senden der Antwort: {e}")
                return False
            except Exception as e:
                # Unknown error
                logger.error(f"Unbekannter Fehler beim Senden der Antwort: {e}")
                return False

        return False

    def get_backoff_delay(self, count: int, is_malformed: bool = False) -> int:
        """
        Calculate reconnect delay with exponential backoff.
        
        Sequence for malformed events: 2s -> 30s -> 60s -> 300s (5min)
        Sequence for generic errors: 30s -> 60s -> 300s
        """
        if is_malformed and count == 1:
            return 2
        
        # Adjust count for malformed events since index 1 was 2s
        adj_count = count - 1 if is_malformed else count
        
        if adj_count <= 1:
            return self.reconnect_delay  # Default 30s
        elif adj_count == 2:
            return 60  # 1 minute
        else:
            return 300  # 5 minutes

    def setup(self):
        """Initialize Mastodon API and account state."""
        if not self.access_token:
            logger.error("Fehler: MASTODON_BOT_ACCESS_TOKEN nicht in .env gefunden.")
            return False

        self.mastodon = Mastodon(
            access_token=self.access_token,
            api_base_url=self.mastodon_instance,
        )

        # Get the account ID of the target using public lookup
        # (access token has limited scopes, so we use unauthenticated lookup)
        try:
            public_mastodon = Mastodon(api_base_url=self.mastodon_instance)
            target_account = public_mastodon.account_lookup(self.bt_account_name)
            self.bt_account_id = target_account["id"]
            logger.info(f"Account @{self.bt_account_name} gefunden (ID: {self.bt_account_id})")
        except Exception as e:
            logger.error(f"Fehler: Account @{self.bt_account_name} nicht gefunden: {e}")
            return False

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

    def extract_word(self, content: str) -> tuple[str | None, bool]:
        """
        Extract a single word from a mention, ignoring @handles.

        Returns:
            tuple: (word, has_multiple_words)
                - word: First word found or None
                - has_multiple_words: True if more than one word was found
        """
        text = self.strip_html(content)
        # Remove @mentions (allow whitespace because strip_html might put spaces between @ and name)
        text = re.sub(r'@\s*\w+(@[\w.]+)?', '', text)
        tokens = text.split()

        if not tokens:
            return None, False

        # Separate normal words and hashtags
        hashtags = [t for t in tokens if t.startswith('#')]
        words = [t for t in tokens if not t.startswith('#')]

        # "In parsing, always ignore hashtags if there is one valid word."
        if words:
            return words[0], len(words) > 1

        # "If the hashtag is the only word, remove the hashtag character and process it like a normal word."
        if hashtags:
            cleaned_hashtag = hashtags[0].lstrip('#')
            return cleaned_hashtag, len(hashtags) > 1

        return None, False

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
        has_multiple_words = False
        user_id = str(status["account"]["id"])

        if is_mention:
            word, has_multiple_words = self.extract_word(content)
            self.last_mention_id = status_id

            # Check rate limit for mentions (only rate limit mentions, not bt_first_said posts)
            if not self.rate_limiter.is_allowed(user_id):
                post_lang = status.get("language", "de")
                if post_lang not in ['de', 'en', 'fr', 'es', 'it', 'nl', 'pl', 'pt', 'ru', 'sv', 'tr']:
                    post_lang = "de"
                error_msg = get_rate_limit_message(post_lang)

                if self.send_reply_with_retry(status, error_msg):
                    logger.info(f"Rate limit Fehler gesendet an User {user_id}")
                else:
                    logger.error("Rate limit Fehlermeldung konnte nicht gesendet werden")
                self.save_state()
                return

        elif self.is_single_word(content):
            word = self.strip_html(content).strip()
            self.last_bt_id = status_id

        # Handle multiple words error for mentions
        if is_mention and has_multiple_words:
            post_lang = status.get("language", "de")
            if post_lang not in ['de', 'en', 'fr', 'es', 'it', 'nl', 'pl', 'pt', 'ru', 'sv', 'tr']:
                post_lang = "de"
            error_msg = get_error_message(post_lang)

            if self.send_reply_with_retry(status, error_msg):
                logger.info(f"Fehler gesendet: Mehrere Wörter erkannt")
            else:
                logger.error("Fehlermeldung konnte nicht gesendet werden")
        elif word:
            # Validate word contains only letters
            if not is_valid_word(word):
                post_lang = status.get("language", "de")
                if post_lang not in ['de', 'en', 'fr', 'es', 'it', 'nl', 'pl', 'pt', 'ru', 'sv', 'tr']:
                    post_lang = "de"
                error_msg = get_invalid_word_message(post_lang)

                if self.send_reply_with_retry(status, error_msg):
                    logger.info(f"Fehler gesendet: Ungültiges Wort '{word}'")
                else:
                    logger.error("Fehlermeldung konnte nicht gesendet werden")
                self.save_state()
                return

            # Word is valid, calculate points and respond
            post_lang = status.get("language")
            points, detected_lang = calculate_points(word, post_lang)

            # Check if word is in an unsupported language (0 points + unsupported chars)
            if is_unsupported_language(word, points):
                # Use post language if available, otherwise use detected language
                error_lang = post_lang if post_lang and post_lang in ['de', 'en', 'fr', 'es', 'it', 'nl', 'pl', 'pt', 'ru', 'sv', 'tr'] else detected_lang
                error_msg = get_unsupported_language_message(error_lang)

                if self.send_reply_with_retry(status, error_msg):
                    logger.info(f"Unsupported language Fehler gesendet für Wort '{word}'")
                else:
                    logger.error("Unsupported language Fehlermeldung konnte nicht gesendet werden")
                self.save_state()
                return

            # Format and send normal response (reuse already calculated points and language)
            response = format_response(word, post_lang, points, detected_lang)

            if self.send_reply_with_retry(status, response):
                logger.info(f"Antwort gesendet: {word} -> {response}")
            else:
                logger.error(f"Antwort konnte nicht gesendet werden für Wort: {word}")

        self.save_state()

    def shutdown(self):
        """Gracefully shutdown the bot."""
        logger.info("Graceful shutdown initiiert...")
        self.shutdown_requested = True
        self.save_state()
        logger.info("Bot erfolgreich heruntergefahren.")

    def run(self):
        """Start the streaming loop with reconnection logic."""
        if not self.setup():
            return

        logger.info("Bot gestartet. Wechsel zu Real-time Streaming...")
        listener = ScrabbleListener(self)

        # Track last cleanup time for rate limiter
        last_cleanup = time.time()
        cleanup_interval = 3600  # Cleanup every hour

        # Track consecutive errors for specialized backoff
        consecutive_malformed_errors = 0

        while not self.shutdown_requested:
            # Periodic cleanup of rate limiter
            if time.time() - last_cleanup > cleanup_interval:
                self.rate_limiter.cleanup_old_entries()
                last_cleanup = time.time()

            try:
                # This call blocks while the stream is open
                self.mastodon.stream_user(listener)
                
                # If the stream closes normally or after success, reset counters
                consecutive_malformed_errors = 0
                self.reconnect_count = 0
            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt empfangen, beende Bot...")
                break
            except MastodonMalformedEventError as e:
                if self.shutdown_requested:
                    break
                
                consecutive_malformed_errors += 1
                delay = self.get_backoff_delay(consecutive_malformed_errors, is_malformed=True)
                
                logger.warning(f"Malformed event im Stream (Versuch {consecutive_malformed_errors}): {e}")
                logger.info(f"Reconnect in {delay} Sekunden...")
                time.sleep(delay)
                continue
            except Exception as e:
                if self.shutdown_requested:
                    break

                self.reconnect_count += 1
                consecutive_malformed_errors = 0 # Reset this as it's a different type of error
                
                delay = self.get_backoff_delay(self.reconnect_count, is_malformed=False)
                
                logger.error(f"Stream-Verbindung abgebrochen: {e} (Versuch {self.reconnect_count})")
                logger.info(f"Reconnect in {delay} Sekunden...")
                time.sleep(delay)

        self.shutdown()


if __name__ == "__main__":
    bot = ScrabbleBot()

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Signal {sig} empfangen, beende Bot gracefully...")
        bot.shutdown_requested = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    bot.run()
