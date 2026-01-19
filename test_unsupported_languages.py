"""Demo script to test unsupported language detection."""

from scrabble import calculate_points, is_unsupported_language, get_unsupported_language_message

# Test words in different languages
test_cases = [
    # Supported languages
    ("Hello", "en", "English - should work"),
    ("Bonjour", "fr", "French - should work"),
    ("Привет", "ru", "Russian - should work"),
    
    # Unsupported languages
    ("こんにちは", None, "Japanese - should be flagged as unsupported"),
    ("你好", None, "Chinese - should be flagged as unsupported"),
    ("مرحبا", None, "Arabic - should be flagged as unsupported"),
    ("שלום", None, "Hebrew - should be flagged as unsupported"),
    ("안녕하세요", None, "Korean - should be flagged as unsupported"),
    ("😀🎉", None, "Emoji - should be flagged as unsupported"),
]

print("Testing Unsupported Language Detection\n" + "="*50 + "\n")

for word, lang_hint, description in test_cases:
    print(f"Testing: {word} ({description})")
    
    # Calculate points
    points, detected_lang = calculate_points(word, lang_hint)
    
    # Check if unsupported
    is_unsupported = is_unsupported_language(word, points)
    
    if is_unsupported:
        error_msg = get_unsupported_language_message(detected_lang)
        print(f"  ❌ UNSUPPORTED: {points} points")
        print(f"  📝 Error message: {error_msg[:80]}...")
    else:
        print(f"  ✅ SUPPORTED: {points} points (detected as {detected_lang})")
    
    print()
