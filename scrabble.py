"""Multi-language Scrabble point calculation with language detection."""

from langdetect import detect, DetectorFactory, LangDetectException

# Make language detection deterministic
DetectorFactory.seed = 0

# Letter point values by language
LETTER_POINTS = {
    # German
    'de': {
        'E': 1, 'N': 1, 'S': 1, 'I': 1, 'R': 1, 'T': 1, 'U': 1, 'A': 1, 'D': 1,
        'H': 2, 'G': 2, 'L': 2, 'O': 2,
        'M': 3, 'B': 3, 'W': 3, 'Z': 3,
        'C': 4, 'F': 4, 'K': 4, 'P': 4,
        'Ä': 6, 'J': 6, 'Ü': 6, 'V': 6,
        'Ö': 8, 'X': 8,
        'Q': 10, 'Y': 10,
    },
    # English
    'en': {
        'E': 1, 'A': 1, 'I': 1, 'O': 1, 'N': 1, 'R': 1, 'T': 1, 'L': 1, 'S': 1, 'U': 1,
        'D': 2, 'G': 2,
        'B': 3, 'C': 3, 'M': 3, 'P': 3,
        'F': 4, 'H': 4, 'V': 4, 'W': 4, 'Y': 4,
        'K': 5,
        'J': 8, 'X': 8,
        'Q': 10, 'Z': 10,
    },
    # French
    'fr': {
        'E': 1, 'A': 1, 'I': 1, 'N': 1, 'O': 1, 'R': 1, 'S': 1, 'T': 1, 'U': 1, 'L': 1,
        'D': 2, 'M': 2, 'G': 2,
        'B': 3, 'C': 3, 'P': 3,
        'F': 4, 'H': 4, 'V': 4,
        'J': 8, 'Q': 8,
        'K': 10, 'W': 10, 'X': 10, 'Y': 10, 'Z': 10,
    },
    # Spanish
    'es': {
        'A': 1, 'E': 1, 'O': 1, 'I': 1, 'S': 1, 'N': 1, 'R': 1, 'U': 1, 'L': 1, 'T': 1,
        'D': 2, 'G': 2,
        'C': 3, 'B': 3, 'M': 3, 'P': 3,
        'H': 4, 'F': 4, 'V': 4, 'Y': 4,
        'Q': 5,
        'J': 8, 'Ñ': 8, 'X': 8,
        'Z': 10,
    },
    # Italian
    'it': {
        'O': 1, 'A': 1, 'I': 1, 'E': 1,
        'C': 2, 'R': 2, 'S': 2, 'T': 2,
        'L': 3, 'M': 3, 'N': 3, 'U': 3,
        'B': 5, 'D': 5, 'F': 5, 'P': 5, 'V': 5,
        'G': 8, 'H': 8, 'Z': 8,
        'Q': 10,
    },
    # Dutch
    'nl': {
        'E': 1, 'N': 1, 'A': 1, 'O': 1, 'I': 1,
        'D': 2, 'R': 2, 'S': 2, 'T': 2,
        'G': 3, 'K': 3, 'L': 3, 'M': 3, 'B': 3, 'P': 3,
        'U': 4, 'F': 4, 'H': 4, 'J': 4, 'V': 4, 'Z': 4,
        'C': 5, 'W': 5,
        'X': 8, 'Y': 8,
        'Q': 10,
    },
    # Polish
    'pl': {
        'A': 1, 'I': 1, 'E': 1, 'O': 1, 'N': 1, 'Z': 1, 'R': 1, 'S': 1, 'W': 1,
        'Y': 2, 'C': 2, 'D': 2, 'K': 2, 'L': 2, 'M': 2, 'P': 2, 'T': 2,
        'B': 3, 'G': 3, 'H': 3, 'J': 3, 'Ł': 3, 'U': 3,
        'Ą': 5, 'Ę': 5, 'F': 5, 'Ó': 5, 'Ś': 5, 'Ż': 5,
        'Ć': 6,
        'Ń': 7,
        'Ź': 9,
    },
    # Portuguese
    'pt': {
        'A': 1, 'E': 1, 'I': 1, 'O': 1, 'S': 1, 'U': 1, 'M': 1, 'R': 1, 'T': 1,
        'D': 2, 'L': 2, 'C': 2, 'P': 2,
        'N': 3, 'B': 3, 'Ç': 3,
        'F': 4, 'G': 4, 'H': 4, 'V': 4,
        'J': 5,
        'Q': 6,
        'X': 8, 'Z': 8,
    },
    # Russian
    'ru': {
        'О': 1, 'А': 1, 'Е': 1, 'И': 1, 'Н': 1, 'Р': 1, 'С': 1, 'Т': 1, 'В': 1,
        'Д': 2, 'К': 2, 'Л': 2, 'П': 2, 'У': 2, 'М': 2,
        'Б': 3, 'Г': 3, 'Ь': 3, 'Я': 3, 'Ё': 3,
        'Ы': 4, 'Й': 4,
        'З': 5, 'Ж': 5, 'Х': 5, 'Ц': 5, 'Ч': 5,
        'Ш': 8, 'Э': 8, 'Ю': 8,
        'Ф': 10, 'Щ': 10, 'Ъ': 10,
    },
    # Swedish
    'sv': {
        'A': 1, 'R': 1, 'S': 1, 'T': 1, 'E': 1, 'N': 1, 'D': 1, 'I': 1, 'L': 1,
        'O': 2, 'G': 2, 'K': 2, 'H': 2, 'M': 2,
        'F': 3, 'V': 3, 'Ä': 3, 'B': 3, 'P': 3, 'U': 3, 'Å': 3,
        'Ö': 4, 'J': 4,
        'Y': 7, 'C': 7, 'X': 7,
        'Z': 8, 'Q': 8, 'W': 8,
    },
    # Turkish
    'tr': {
        'A': 1, 'E': 1, 'I': 1, 'K': 1, 'L': 1, 'R': 1, 'N': 1, 'İ': 1, 'T': 1,
        'M': 2, 'S': 2, 'U': 2, 'O': 2, 'D': 2, 'B': 2, 'Y': 2,
        'Ü': 3, 'Ş': 3, 'C': 3, 'Z': 3, 'Ç': 3, 'H': 3, 'P': 3, 'G': 3,
        'V': 4, 'Ö': 4, 'F': 4,
        'Ğ': 5, 'J': 5,
        'Ş': 7,
        'J': 10,
    },
}

# Language names for responses
LANGUAGE_NAMES = {
    'de': 'Deutsch',
    'en': 'Englisch',
    'fr': 'Französisch',
    'es': 'Spanisch',
    'it': 'Italienisch',
    'nl': 'Niederländisch',
    'pl': 'Polnisch',
    'pt': 'Portugiesisch',
    'ru': 'Russisch',
    'sv': 'Schwedisch',
    'tr': 'Türkisch',
}

DEFAULT_LANGUAGE = 'de'

# Map similar languages to supported ones
LANGUAGE_FALLBACKS = {
    'bg': 'ru',  # Bulgarian -> Russian (Cyrillic)
    'uk': 'ru',  # Ukrainian -> Russian (Cyrillic)
    'mk': 'ru',  # Macedonian -> Russian (Cyrillic)
    'sr': 'ru',  # Serbian -> Russian (Cyrillic)
    'ca': 'es',  # Catalan -> Spanish
    'gl': 'pt',  # Galician -> Portuguese
    'da': 'sv',  # Danish -> Swedish
    'no': 'sv',  # Norwegian -> Swedish
    'af': 'nl',  # Afrikaans -> Dutch
    'cs': 'pl',  # Czech -> Polish
    'sk': 'pl',  # Slovak -> Polish
    'ro': 'it',  # Romanian -> Italian
}


def has_cyrillic(text: str) -> bool:
    """Check if text contains Cyrillic characters."""
    return any('\u0400' <= char <= '\u04FF' for char in text)


def detect_language(text: str) -> str:
    """Detect the language of a text, defaulting to German."""
    # Script-based detection for Cyrillic
    if has_cyrillic(text):
        return 'ru'

    try:
        lang = detect(text)
        if lang in LETTER_POINTS:
            return lang
        # Try fallback mapping
        if lang in LANGUAGE_FALLBACKS:
            return LANGUAGE_FALLBACKS[lang]
        return DEFAULT_LANGUAGE
    except LangDetectException:
        return DEFAULT_LANGUAGE


def calculate_points(word: str, language: str | None = None) -> tuple[int, str]:
    """
    Calculate Scrabble points for a word.

    Returns a tuple of (points, language_code).
    If language is not specified, it will be detected.
    """
    if language is None:
        language = detect_language(word)

    if language not in LETTER_POINTS:
        language = DEFAULT_LANGUAGE

    points_map = LETTER_POINTS[language]
    total = 0
    for char in word.upper():
        total += points_map.get(char, 0)

    return total, language


def get_language_name(lang_code: str) -> str:
    """Get the German name for a language code."""
    return LANGUAGE_NAMES.get(lang_code, lang_code)
