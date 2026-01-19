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
