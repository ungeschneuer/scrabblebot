"""Mastodon Scrabble Bot - replies with Scrabble points in real-time."""

import os
import re
import json
import time
import logging
import signal
import sys
import atexit
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
    is_unsupported_language,
    SUPPORTED_LANGUAGES
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
        """Handle new notifications (mentions, including filtered and direct)."""
        if notification['type'] == 'mention':
            status = notification['status']
            account_id = str(status['account']['id'])

            # Ignore own notifications (e.g. from own replies)
            if account_id == self.bot.my_id:
                return

            # Check if this mention should be ignored (citations, conversations, etc.)
            should_ignore, reason = self.bot.should_ignore_mention(status)
            if should_ignore:
                logger.info(f"Ignoring mention from {status['account']['acct']}: {reason}")
                return

            visibility = status.get('visibility', 'public')
            is_filtered = notification.get('filtered') is not None

            # Log the type of mention
            if visibility == 'direct':
                logger.info(f"Notification received: Direct mention from {status['account']['acct']}")
            elif is_filtered:
                logger.info(f"Notification received: Filtered mention from {status['account']['acct']}")
            else:
                logger.info(f"Notification received: Mention from {status['account']['acct']}")

            self.bot.process_status(status, is_mention=True)

    def _dispatch(self, event):
        """Override _dispatch to ignore empty events (heartbeats)."""
        if not event:
            return
        super()._dispatch(event)

    def on_update(self, status):
        """Handle new statuses in home timeline (followed accounts)."""
        # Only process if monitoring is enabled
        if not self.bot.bt_account_name:
            return

        # Check if the status is from the targeted account
        if status['account']['acct'] == self.bot.bt_account_name:
            logger.info(f"Update received: Post from @{self.bot.bt_account_name}")
            self.bot.process_status(status, is_mention=False)


class ScrabbleBot:
    """Core logic and state for the Scrabble Bot."""

    def __init__(self):
        # Configuration from environment variables
        self.mastodon_instance = os.getenv("MASTODON_INSTANCE", "https://mastodon.social")
        self.bt_account_name = os.getenv("BT_FIRST_SAID_ACCOUNT")  # Optional: None if not set
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
        self.my_id = None  # Bot's own account ID
        self.last_mention_id = None
        self.last_bt_id = None
        self.reconnect_count = 0
        self.shutdown_requested = False
        self.rate_limiter = RateLimiter(rate_limit_max, rate_limit_window, rate_limit_enabled)

        # In-memory cache of recently processed status IDs to prevent duplicates
        self.processed_status_ids = set()
        self.max_processed_cache = 100  # Keep last 100 IDs in memory

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
                reply_status = self.mastodon.status_reply(
                    to_status=status,
                    status=message,
                    visibility=status["visibility"],
                )

                # Add our own reply to processed cache to avoid processing it
                if reply_status and 'id' in reply_status:
                    self.processed_status_ids.add(reply_status['id'])

                return True
            except MastodonRatelimitError as e:
                # Rate limited - wait and retry
                logger.warning(f"Rate limited, waiting before retry (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(f"Rate limit reached after {max_retries} attempts: {e}")
                    return False
            except MastodonNetworkError as e:
                # Network error - retry
                logger.warning(f"Network error, retrying (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    logger.error(f"Network error after {max_retries} attempts: {e}")
                    return False
            except MastodonAPIError as e:
                # API error - likely not transient, don't retry
                logger.error(f"API error sending reply: {e}")
                return False
            except Exception as e:
                # Unknown error
                logger.error(f"Unknown error sending reply: {e}")
                return False

        return False

    def send_error_response(self, status, error_type: str, context: str = "", override_lang: str = None) -> bool:
        """
        Send localized error response based on status language.

        Args:
            status: The status to reply to
            error_type: Type of error ('multiple_words', 'invalid_word', 'rate_limited', 'unsupported_language')
            context: Optional context for logging (e.g., word that caused error)
            override_lang: Optional language override (for unsupported language detection)

        Returns:
            bool: True if successful, False otherwise
        """
        # Get and validate post language
        if override_lang:
            post_lang = override_lang
        else:
            post_lang = status.get("language", "de")
            if post_lang not in SUPPORTED_LANGUAGES:
                post_lang = "de"

        # Get appropriate error message function
        error_msg_functions = {
            'multiple_words': get_error_message,
            'invalid_word': get_invalid_word_message,
            'rate_limited': get_rate_limit_message,
            'unsupported_language': get_unsupported_language_message
        }

        if error_type not in error_msg_functions:
            logger.error(f"Unknown error type: {error_type}")
            return False

        error_msg = error_msg_functions[error_type](post_lang)

        # Send error message
        if self.send_reply_with_retry(status, error_msg):
            log_msg = f"{error_type} error sent"
            if context:
                log_msg += f": {context}"
            logger.info(log_msg)
            return True
        else:
            logger.error(f"Could not send {error_type} error message")
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
            logger.error("Error: MASTODON_BOT_ACCESS_TOKEN not found in .env")
            return False

        self.mastodon = Mastodon(
            access_token=self.access_token,
            api_base_url=self.mastodon_instance,
        )

        # Get bot's own account ID
        try:
            my_account = self.mastodon.account_verify_credentials()
            self.my_id = str(my_account["id"])
            logger.info(f"Bot running as @{my_account['username']} (ID: {self.my_id})")
        except Exception as e:
            logger.error(f"Error fetching bot credentials: {e}")
            return False

        # Get the account ID of the target using public lookup (optional)
        # (access token has limited scopes, so we use unauthenticated lookup)
        if self.bt_account_name:
            try:
                public_mastodon = Mastodon(api_base_url=self.mastodon_instance)
                target_account = public_mastodon.account_lookup(self.bt_account_name)
                self.bt_account_id = target_account["id"]
                logger.info(f"Account @{self.bt_account_name} found (ID: {self.bt_account_id}) - Monitoring enabled")
            except Exception as e:
                logger.error(f"Error: Account @{self.bt_account_name} not found: {e}")
                return False
        else:
            logger.info("No account configured for monitoring - mention-only mode active")

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
                logger.warning("Could not load last IDs, using default values")

    def save_state(self):
        """Save last processed IDs."""
        try:
            with open(self.last_ids_file, 'w') as f:
                json.dump({
                    "mentions": self.last_mention_id,
                    "bt_posts": self.last_bt_id
                }, f)
        except IOError as e:
            logger.error(f"Error saving IDs: {e}")

    def strip_html(self, text: str) -> str:
        """Remove HTML tags and decode entities."""
        text = re.sub(r'<[^>]+>', ' ', text)
        text = unescape(text)
        return text.strip()

    def should_ignore_mention(self, status) -> tuple[bool, str]:
        """
        Determine if a mention should be ignored based on context.

        Returns:
            tuple: (should_ignore, reason)
                - should_ignore: True if the mention should be ignored
                - reason: Human-readable reason for ignoring
        """
        # Check if this is a quote/citation of the bot's own post
        if 'quote' in status and status['quote']:
            quoted_account_id = str(status['quote']['account']['id'])
            if quoted_account_id == self.my_id:
                return True, "quoting bot's own post"

        # Check if status has a reblog field (boosting bot's post with comment)
        if 'reblog' in status and status['reblog']:
            reblog_account_id = str(status['reblog']['account']['id'])
            if reblog_account_id == self.my_id:
                return True, "reblogging/boosting bot's post"

        # Check if this is a reply to someone else (not the bot or original post)
        reply_to_account = status.get('in_reply_to_account_id')
        if reply_to_account:
            reply_to_account_id = str(reply_to_account)
            # If replying to someone else, check if this is conversational
            if reply_to_account_id != self.my_id:
                # This is a reply in a thread with someone else
                content = self.strip_html(status['content']).lower()

                # If the post has conversational indicators, likely not a score request
                conversational_patterns = [
                    r'\?',  # Question marks (asking about the bot)
                    r'\bwarum\b', r'\bweshalb\b', r'\bwieso\b',  # German: why
                    r'\bwhy\b', r'\bhow\b', r'\bwhat\b',  # English: question words
                    r'\bpourquoi\b', r'\bcomment\b',  # French: why, how
                    r'\bbot\b.*\b(ist|does|macht|is|fait)',  # Talking about the bot
                    r'\b(danke|thanks|merci)\b',  # Thanking someone
                ]

                for pattern in conversational_patterns:
                    if re.search(pattern, content):
                        return True, "conversational reply in thread"

        # Check for meta-discussion patterns (talking about the bot, not to it)
        content = self.strip_html(status['content'])
        content_lower = content.lower()

        # Count mentions - if multiple bots/people are mentioned, likely a discussion
        mention_count = len(re.findall(r'@\s*\w+', content))
        if mention_count > 2:  # More than 2 mentions suggests group discussion
            return True, "group discussion with multiple mentions"

        # Check for phrases indicating discussion about the bot
        meta_patterns = [
            r'\b(der|die|das)\s+bot\b',  # German: the bot (talking about)
            r'\b(dieser|diese|dieses)\s+bot\b',  # German: this bot
            r'\bthe\s+bot\b',  # English: the bot
            r'\bthis\s+bot\b',  # English: this bot
            r'\ble\s+bot\b',  # French: the bot
            r'\bce\s+bot\b',  # French: this bot
            r'\bbot\s+(ist|is|kann|can|macht|does|hat|has)\b',  # Bot capabilities discussion
        ]

        for pattern in meta_patterns:
            if re.search(pattern, content_lower):
                # Double-check: if there's ONLY the mention and a single word, it's likely a score request
                text_without_mentions = re.sub(r'@\s*\w+(@[\w.]+)?', '', content)
                words = text_without_mentions.split()
                clean_words = [w for w in words if w and not w.startswith('#')]

                # If after removing mentions there's exactly 1 word, it's a score request
                if len(clean_words) == 1:
                    return False, ""

                return True, "meta-discussion about the bot"

        return False, ""

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

        # Check if we already processed this status (in-memory cache)
        if status_id in self.processed_status_ids:
            logger.debug(f"Status {status_id} already processed (in cache), skipping")
            return

        # Avoid processing older items if we have a state (safety check for stream glitches)
        if is_mention and self.last_mention_id and status_id <= self.last_mention_id:
            logger.debug(f"Status {status_id} older than last_mention_id {self.last_mention_id}, skipping")
            return
        if not is_mention and self.last_bt_id and status_id <= self.last_bt_id:
            logger.debug(f"Status {status_id} older than last_bt_id {self.last_bt_id}, skipping")
            return

        content = status["content"]
        word = None
        has_multiple_words = False
        user_id = str(status["account"]["id"])

        if is_mention:
            word, has_multiple_words = self.extract_word(content)

            # Mark as processed BEFORE doing anything else
            self.last_mention_id = status_id
            self.processed_status_ids.add(status_id)
            self.save_state()  # Save immediately to prevent reprocessing

            # Trim cache if it gets too large
            if len(self.processed_status_ids) > self.max_processed_cache:
                # Remove oldest entries (convert to sorted list, remove first half)
                sorted_ids = sorted(self.processed_status_ids)
                self.processed_status_ids = set(sorted_ids[self.max_processed_cache // 2:])

            # Check rate limit for mentions (only rate limit mentions, not bt_first_said posts)
            if not self.rate_limiter.is_allowed(user_id):
                self.send_error_response(status, 'rate_limited', f"user {user_id}")
                return

        elif self.is_single_word(content):
            word = self.strip_html(content).strip()

            # Mark as processed BEFORE doing anything else
            self.last_bt_id = status_id
            self.processed_status_ids.add(status_id)
            self.save_state()  # Save immediately to prevent reprocessing

            # Trim cache if it gets too large
            if len(self.processed_status_ids) > self.max_processed_cache:
                sorted_ids = sorted(self.processed_status_ids)
                self.processed_status_ids = set(sorted_ids[self.max_processed_cache // 2:])

        # Handle multiple words error for mentions
        if is_mention and has_multiple_words:
            self.send_error_response(status, 'multiple_words')
            return

        if word:
            # Validate word contains only letters
            if not is_valid_word(word):
                self.send_error_response(status, 'invalid_word', f"word '{word}'")
                return

            # Word is valid, calculate points and respond
            post_lang = status.get("language")
            points, detected_lang = calculate_points(word, post_lang)

            # Check if word is in an unsupported language (0 points + unsupported chars)
            if is_unsupported_language(word, points):
                # Use post language if available, otherwise use detected language
                error_lang = post_lang if post_lang and post_lang in SUPPORTED_LANGUAGES else detected_lang
                self.send_error_response(status, 'unsupported_language', f"word '{word}'", override_lang=error_lang)
                return

            # Format and send normal response (reuse already calculated points and language)
            response = format_response(word, post_lang, points, detected_lang)

            if self.send_reply_with_retry(status, response):
                logger.info(f"Response sent: {word} -> {response}")
            else:
                logger.error(f"Could not send response for word: {word}")

    def shutdown(self):
        """Gracefully shutdown the bot."""
        logger.info("Graceful shutdown initiated...")
        self.shutdown_requested = True
        self.save_state()
        logger.info("Bot shutdown successfully")

    def run(self):
        """Start the streaming loop with reconnection logic."""
        if not self.setup():
            return

        logger.info("Bot started. Switching to real-time streaming...")
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
                logger.info("KeyboardInterrupt received, shutting down bot...")
                break
            except MastodonMalformedEventError as e:
                if self.shutdown_requested:
                    break
                
                consecutive_malformed_errors += 1
                delay = self.get_backoff_delay(consecutive_malformed_errors, is_malformed=True)
                
                logger.warning(f"Malformed event in stream (attempt {consecutive_malformed_errors}): {e}")
                logger.info(f"Reconnecting in {delay} seconds...")
                time.sleep(delay)
                continue
            except Exception as e:
                if self.shutdown_requested:
                    break

                self.reconnect_count += 1
                consecutive_malformed_errors = 0 # Reset this as it's a different type of error
                
                delay = self.get_backoff_delay(self.reconnect_count, is_malformed=False)
                
                logger.error(f"Stream connection closed: {e} (attempt {self.reconnect_count})")
                logger.info(f"Reconnecting in {delay} seconds...")
                time.sleep(delay)

        self.shutdown()


def check_single_instance():
    """Ensure only one instance of the bot is running."""
    pid_file = "/tmp/scrabble-bot.pid"

    # Check if PID file exists
    if os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                old_pid = int(f.read().strip())

            # Check if process is still running
            try:
                os.kill(old_pid, 0)  # Signal 0 checks if process exists
                logger.error(f"Bot is already running (PID: {old_pid})")
                sys.exit(1)
            except OSError:
                # Process doesn't exist, remove stale PID file
                logger.warning(f"Stale PID file found, removing it")
                os.remove(pid_file)
        except (ValueError, IOError) as e:
            logger.warning(f"Could not read PID file: {e}")
            os.remove(pid_file)

    # Write our PID
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))

    # Register cleanup
    def cleanup_pid():
        try:
            if os.path.exists(pid_file):
                with open(pid_file, 'r') as f:
                    stored_pid = int(f.read().strip())
                if stored_pid == os.getpid():
                    os.remove(pid_file)
        except:
            pass

    atexit.register(cleanup_pid)


if __name__ == "__main__":
    # Ensure only one instance is running
    check_single_instance()

    bot = ScrabbleBot()

    # PID file path (must match check_single_instance)
    pid_file = "/tmp/scrabble-bot.pid"

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Signal {sig} received, shutting down bot gracefully...")
        bot.shutdown_requested = True

        # Clean up PID file immediately to allow new instance to start
        try:
            if os.path.exists(pid_file):
                with open(pid_file, 'r') as f:
                    stored_pid = int(f.read().strip())
                if stored_pid == os.getpid():
                    os.remove(pid_file)
                    logger.info("PID file removed")
        except Exception as e:
            logger.warning(f"Could not remove PID file: {e}")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    bot.run()
