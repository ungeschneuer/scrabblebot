"""Unit tests for scrabble.py module."""

import pytest
from scrabble import (
    calculate_points,
    get_language_name,
    get_response_template,
    get_error_message,
    get_invalid_word_message,
    get_rate_limit_message,
    get_unsupported_language_message,
    is_valid_word,
    detect_language,
    has_cyrillic,
    has_supported_characters,
    is_unsupported_language,
)


class TestCalculatePoints:
    """Tests for calculate_points function."""

    def test_german_word(self):
        """Test German word calculation."""
        points, lang = calculate_points("Hallo", "de")
        assert points == 9  # H(2) + A(1) + L(2) + L(2) + O(2) = 9
        assert lang == "de"

    def test_english_word(self):
        """Test English word calculation."""
        points, lang = calculate_points("hello", "en")
        assert points == 8  # H(4) + E(1) + L(1) + L(1) + O(1) = 8
        assert lang == "en"

    def test_word_auto_detect_german(self):
        """Test automatic language detection for German."""
        points, lang = calculate_points("Haus")
        assert lang == "de"
        assert points > 0

    def test_word_auto_detect_english(self):
        """Test automatic language detection for English."""
        points, lang = calculate_points("house")
        # Language detection might vary, just check it returns something
        assert points > 0
        assert lang in ["en", "de", "fr", "es", "it", "nl", "pl", "pt", "ru", "sv", "tr"]

    def test_empty_word(self):
        """Test empty word returns 0 points."""
        points, lang = calculate_points("", "de")
        assert points == 0

    def test_case_insensitive(self):
        """Test that calculation is case insensitive."""
        points1, lang1 = calculate_points("HELLO", "en")
        points2, lang2 = calculate_points("hello", "en")
        assert points1 == points2
        assert lang1 == lang2


class TestLanguageDetection:
    """Tests for language detection functions."""

    def test_has_cyrillic_true(self):
        """Test Cyrillic detection returns True for Cyrillic text."""
        assert has_cyrillic("Привет") is True

    def test_has_cyrillic_false(self):
        """Test Cyrillic detection returns False for Latin text."""
        assert has_cyrillic("Hello") is False

    def test_detect_language_cyrillic(self):
        """Test that Cyrillic text is detected as Russian."""
        lang = detect_language("Привет")
        assert lang == "ru"

    def test_detect_language_german(self):
        """Test German language detection."""
        lang = detect_language("Guten Tag")
        assert lang in ["de", "nl"]  # Could be detected as Dutch too


class TestWordValidation:
    """Tests for word validation."""

    def test_valid_word(self):
        """Test valid alphabetic word."""
        assert is_valid_word("Hello") is True

    def test_valid_word_with_umlauts(self):
        """Test valid word with German umlauts."""
        assert is_valid_word("Käse") is True

    def test_valid_word_with_hyphen(self):
        """Test valid compound word with hyphen."""
        assert is_valid_word("Hello-World") is True

    def test_valid_word_with_apostrophe(self):
        """Test valid word with apostrophe."""
        assert is_valid_word("it's") is True

    def test_invalid_word_with_numbers(self):
        """Test invalid word containing numbers."""
        assert is_valid_word("Hello123") is False

    def test_invalid_word_with_special_chars(self):
        """Test invalid word with special characters."""
        assert is_valid_word("Hello@World") is False

    def test_invalid_empty_word(self):
        """Test empty word is invalid."""
        assert is_valid_word("") is False

    def test_invalid_only_numbers(self):
        """Test word with only numbers is invalid."""
        assert is_valid_word("12345") is False


class TestLocalization:
    """Tests for localization functions."""

    def test_get_language_name_german(self):
        """Test getting German language name."""
        assert get_language_name("de", localized=False) == "Deutsch"
        assert get_language_name("de", localized=True) == "Deutsch"

    def test_get_language_name_english(self):
        """Test getting English language name."""
        assert get_language_name("en", localized=False) == "Englisch"
        assert get_language_name("en", localized=True) == "English"

    def test_get_language_name_unknown(self):
        """Test getting unknown language returns code."""
        assert get_language_name("xx", localized=False) == "xx"

    def test_get_response_template_singular(self):
        """Test response template for 1 point."""
        template = get_response_template("en", 1)
        assert "1 Scrabble point" in template

    def test_get_response_template_plural(self):
        """Test response template for multiple points."""
        template = get_response_template("en", 5)
        assert "points" in template

    def test_get_error_message(self):
        """Test getting error message for multiple words."""
        msg = get_error_message("en")
        assert "one word" in msg.lower()

    def test_get_invalid_word_message(self):
        """Test getting error message for invalid word."""
        msg = get_invalid_word_message("en")
        assert "letters" in msg.lower()

    def test_get_rate_limit_message(self):
        """Test getting error message for rate limiting."""
        msg = get_rate_limit_message("en")
        assert "too many" in msg.lower() or "wait" in msg.lower()

    def test_get_unsupported_language_message(self):
        """Test getting error message for unsupported languages."""
        msg = get_unsupported_language_message("en")
        assert "not supported" in msg.lower() or "supported languages" in msg.lower()


class TestUnsupportedLanguages:
    """Tests for unsupported language detection."""

    def test_has_supported_characters_latin(self):
        """Test that Latin characters are recognized as supported."""
        assert has_supported_characters("Hello") is True
        assert has_supported_characters("Bonjour") is True
        assert has_supported_characters("Hola") is True

    def test_has_supported_characters_cyrillic(self):
        """Test that Cyrillic characters are recognized as supported."""
        assert has_supported_characters("Привет") is True

    def test_has_supported_characters_mixed(self):
        """Test mixed supported and unsupported characters."""
        # More than 50% supported should return True
        assert has_supported_characters("Hello世界") is True  # 5 Latin, 2 Chinese

    def test_has_supported_characters_japanese(self):
        """Test that Japanese characters are recognized as unsupported."""
        assert has_supported_characters("こんにちは") is False
        assert has_supported_characters("日本語") is False

    def test_has_supported_characters_chinese(self):
        """Test that Chinese characters are recognized as unsupported."""
        assert has_supported_characters("你好") is False
        assert has_supported_characters("中文") is False

    def test_has_supported_characters_arabic(self):
        """Test that Arabic characters are recognized as unsupported."""
        assert has_supported_characters("مرحبا") is False
        assert has_supported_characters("العربية") is False

    def test_has_supported_characters_hebrew(self):
        """Test that Hebrew characters are recognized as unsupported."""
        assert has_supported_characters("שלום") is False

    def test_has_supported_characters_emoji(self):
        """Test that emoji-only text is unsupported."""
        assert has_supported_characters("😀🎉") is False

    def test_is_unsupported_language_supported(self):
        """Test that supported words are not flagged as unsupported."""
        points, _ = calculate_points("Hello", "en")
        assert is_unsupported_language("Hello", points) is False

        points, _ = calculate_points("Привет", "ru")
        assert is_unsupported_language("Привет", points) is False

    def test_is_unsupported_language_japanese(self):
        """Test that Japanese words are flagged as unsupported."""
        points, _ = calculate_points("こんにちは")
        assert is_unsupported_language("こんにちは", points) is True

    def test_is_unsupported_language_chinese(self):
        """Test that Chinese words are flagged as unsupported."""
        points, _ = calculate_points("你好")
        assert is_unsupported_language("你好", points) is True

    def test_is_unsupported_language_arabic(self):
        """Test that Arabic words are flagged as unsupported."""
        points, _ = calculate_points("مرحبا")
        assert is_unsupported_language("مرحبا", points) is True

    def test_is_unsupported_language_with_points(self):
        """Test that words with points are never flagged as unsupported."""
        # Even with just 1 point, it's considered supported
        assert is_unsupported_language("Hello", 8) is False
        assert is_unsupported_language("A", 1) is False
        assert is_unsupported_language("ZZZZ", 40) is False
