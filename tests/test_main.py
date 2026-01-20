"""Unit tests for main.py module."""

import pytest
from main import ScrabbleBot, format_response


class TestFormatResponse:
    """Tests for format_response function."""

    def test_format_response_german(self):
        """Test formatting response in German."""
        response = format_response("Hallo", "de")
        assert "HALLO" in response
        assert "Scrabble" in response
        assert "Deutsch" in response

    def test_format_response_english(self):
        """Test formatting response in English."""
        response = format_response("hello", "en")
        assert "HELLO" in response
        assert "Scrabble" in response
        assert "English" in response

    def test_format_response_auto_detect(self):
        """Test formatting response with auto-detection."""
        response = format_response("hello")
        assert "HELLO" in response
        assert "Scrabble" in response


class TestScrabbleBot:
    """Tests for ScrabbleBot class."""

    def test_bot_initialization(self):
        """Test bot initialization with default values."""
        bot = ScrabbleBot()
        assert bot.mastodon_instance == "https://mastodon.social"
        assert bot.reconnect_delay == 30
        assert bot.max_reconnect_attempts == 0
        assert bot.shutdown_requested is False

    def test_strip_html(self):
        """Test HTML stripping."""
        bot = ScrabbleBot()
        text = "<p>Hello <strong>World</strong></p>"
        result = bot.strip_html(text)
        # HTML tags are replaced with spaces, resulting in extra whitespace
        assert "Hello" in result and "World" in result

    def test_strip_html_with_entities(self):
        """Test HTML entity decoding."""
        bot = ScrabbleBot()
        text = "&lt;Hello&gt; &amp; &quot;World&quot;"
        result = bot.strip_html(text)
        assert result == '<Hello> & "World"'

    def test_extract_word_single(self):
        """Test extracting single word from mention."""
        bot = ScrabbleBot()
        word, has_multiple = bot.extract_word("@bot hello")
        assert word == "hello"
        assert has_multiple is False

    def test_extract_word_multiple(self):
        """Test extracting word when multiple words present."""
        bot = ScrabbleBot()
        word, has_multiple = bot.extract_word("@bot hello world")
        assert word == "hello"
        assert has_multiple is True

    def test_extract_word_only_mention(self):
        """Test extraction when only mention present."""
        bot = ScrabbleBot()
        word, has_multiple = bot.extract_word("@bot")
        assert word is None
        assert has_multiple is False

    def test_extract_word_multiple_mentions(self):
        """Test extraction with multiple mentions."""
        bot = ScrabbleBot()
        word, has_multiple = bot.extract_word("@bot @user hello")
        assert word == "hello"
        assert has_multiple is False

    def test_is_single_word_true(self):
        """Test single word detection."""
        bot = ScrabbleBot()
        assert bot.is_single_word("<p>Hello</p>") is True

    def test_is_single_word_false(self):
        """Test multiple words detection."""
        bot = ScrabbleBot()
        assert bot.is_single_word("<p>Hello World</p>") is False

    def test_is_single_word_empty(self):
        """Test empty content."""
        bot = ScrabbleBot()
        assert bot.is_single_word("") is False

    def test_shutdown_sets_flag(self):
        """Test shutdown sets the shutdown_requested flag."""
        bot = ScrabbleBot()
        assert bot.shutdown_requested is False
        bot.shutdown()
        assert bot.shutdown_requested is True


class TestSmartMentionDetection:
    """Tests for should_ignore_mention method."""

    def test_ignore_quote_of_bot_post(self):
        """Test ignoring quotes/citations of bot's own posts."""
        bot = ScrabbleBot()
        bot.my_id = "12345"

        status = {
            'content': '<p>@bot check this out</p>',
            'quote': {
                'account': {'id': '12345'},  # Bot's own post
                'content': 'Some quoted content'
            }
        }

        should_ignore, reason = bot.should_ignore_mention(status)
        assert should_ignore is True
        assert "quoting" in reason.lower()

    def test_ignore_reblog_of_bot_post(self):
        """Test ignoring reblogs/boosts of bot's own posts."""
        bot = ScrabbleBot()
        bot.my_id = "12345"

        status = {
            'content': '<p>@bot this is interesting</p>',
            'reblog': {
                'account': {'id': '12345'},  # Bot's own post
                'content': 'Some reblogged content'
            }
        }

        should_ignore, reason = bot.should_ignore_mention(status)
        assert should_ignore is True
        assert "reblog" in reason.lower()

    def test_ignore_conversational_reply_with_question(self):
        """Test ignoring conversational replies with questions."""
        bot = ScrabbleBot()
        bot.my_id = "12345"

        status = {
            'content': '<p>@someone Why is @bot not working?</p>',
            'in_reply_to_account_id': '99999'  # Replying to someone else
        }

        should_ignore, reason = bot.should_ignore_mention(status)
        assert should_ignore is True
        assert "conversational" in reason.lower()

    def test_ignore_meta_discussion_about_bot(self):
        """Test ignoring meta-discussions about the bot."""
        bot = ScrabbleBot()
        bot.my_id = "12345"

        status = {
            'content': '<p>@user1 @user2 The bot is really helpful!</p>'
        }

        should_ignore, reason = bot.should_ignore_mention(status)
        assert should_ignore is True
        assert "meta-discussion" in reason.lower()

    def test_ignore_group_discussion_multiple_mentions(self):
        """Test ignoring group discussions with multiple mentions."""
        bot = ScrabbleBot()
        bot.my_id = "12345"

        status = {
            'content': '<p>@user1 @user2 @bot @user3 Let\'s all play Scrabble!</p>'
        }

        should_ignore, reason = bot.should_ignore_mention(status)
        assert should_ignore is True
        assert "group discussion" in reason.lower()

    def test_ignore_thanks_in_thread(self):
        """Test ignoring thank you messages in threads."""
        bot = ScrabbleBot()
        bot.my_id = "12345"

        status = {
            'content': '<p>@someone Thanks for telling me about @bot!</p>',
            'in_reply_to_account_id': '99999'  # Replying to someone else
        }

        should_ignore, reason = bot.should_ignore_mention(status)
        assert should_ignore is True
        assert "conversational" in reason.lower()

    def test_ignore_bot_capability_discussion(self):
        """Test ignoring discussions about bot capabilities."""
        bot = ScrabbleBot()
        bot.my_id = "12345"

        status = {
            'content': '<p>@user Der Bot kann Scrabble-Punkte berechnen</p>'
        }

        should_ignore, reason = bot.should_ignore_mention(status)
        assert should_ignore is True
        assert "meta-discussion" in reason.lower()

    def test_allow_normal_score_request(self):
        """Test allowing normal score requests."""
        bot = ScrabbleBot()
        bot.my_id = "12345"

        status = {
            'content': '<p>@bot hello</p>'
        }

        should_ignore, reason = bot.should_ignore_mention(status)
        assert should_ignore is False
        assert reason == ""

    def test_allow_single_word_with_meta_phrase(self):
        """Test allowing single word requests even with meta phrases."""
        bot = ScrabbleBot()
        bot.my_id = "12345"

        # "The bot" phrase but with a single word - should still process
        status = {
            'content': '<p>@bot hello</p>'  # Just a mention and a word
        }

        should_ignore, reason = bot.should_ignore_mention(status)
        assert should_ignore is False

    def test_allow_reply_to_bot(self):
        """Test allowing replies directly to the bot."""
        bot = ScrabbleBot()
        bot.my_id = "12345"

        status = {
            'content': '<p>@bot world</p>',
            'in_reply_to_account_id': '12345'  # Replying to bot itself
        }

        should_ignore, reason = bot.should_ignore_mention(status)
        assert should_ignore is False

    def test_no_quote_field(self):
        """Test handling status without quote field."""
        bot = ScrabbleBot()
        bot.my_id = "12345"

        status = {
            'content': '<p>@bot test</p>'
        }

        should_ignore, reason = bot.should_ignore_mention(status)
        assert should_ignore is False

    def test_quote_from_different_user(self):
        """Test not ignoring quotes from other users."""
        bot = ScrabbleBot()
        bot.my_id = "12345"

        status = {
            'content': '<p>@bot test</p>',
            'quote': {
                'account': {'id': '99999'},  # Different user's post
                'content': 'Some quoted content'
            }
        }

        should_ignore, reason = bot.should_ignore_mention(status)
        assert should_ignore is False


class TestStateManagement:
    """Tests for state persistence."""

    def test_save_state(self, tmp_path):
        """Test saving state to file."""
        bot = ScrabbleBot()
        bot.last_ids_file = str(tmp_path / "test_state.json")
        bot.last_mention_id = 12345
        bot.last_bt_id = 67890

        bot.save_state()

        # Read the file and check contents
        import json
        with open(bot.last_ids_file) as f:
            data = json.load(f)

        assert data["mentions"] == 12345
        assert data["bt_posts"] == 67890

    def test_load_state(self, tmp_path):
        """Test loading state from file."""
        import json

        state_file = tmp_path / "test_state.json"
        with open(state_file, "w") as f:
            json.dump({"mentions": 11111, "bt_posts": 22222}, f)

        bot = ScrabbleBot()
        bot.last_ids_file = str(state_file)
        bot.load_state()

        assert bot.last_mention_id == 11111
        assert bot.last_bt_id == 22222

    def test_load_state_missing_file(self):
        """Test loading state when file doesn't exist."""
        bot = ScrabbleBot()
        bot.last_ids_file = "/nonexistent/file.json"
        bot.load_state()

        # Should not raise exception, values remain None
        assert bot.last_mention_id is None
        assert bot.last_bt_id is None
