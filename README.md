# Scrabble Bot for Mastodon

A Mastodon bot that calculates Scrabble points for words in 11 different languages and responds in real time.

## Features

- 🌍 **Multi-language support**: Supports 11 languages with automatic detection
  - German, English, French, Spanish, Italian, Dutch, Polish, Portuguese, Russian, Swedish, Turkish
- ⚡ **Real-time streaming**: Instant responses via Mastodon's streaming API
- 🎯 **Two operating modes**:
  - Responds to direct @mentions
  - Monitors posts from specific accounts (e.g. @bt_first_said)
- 🛡️ **Rate limiting**: Protection against spam with configurable sliding window
- ✅ **Word validation**: Checks for valid Scrabble characters
- 🌏 **Unsupported language detection**: Helpful error messages for non-Latin scripts
- 🔄 **Automatic reconnects**: Reliable operation with reconnect logic
- 💾 **Graceful shutdown**: Clean shutdown with state persistence
- 🧪 **Comprehensive testing**: 66 unit tests with pytest

## Installation

### Requirements

- Python 3.9+
- uv (recommended package manager)
- Mastodon account with API access

### Setup

1. Clone repository:
```bash
git clone <repository-url>
cd scrabblebot.nosync
```

2. Install dependencies:
```bash
uv sync
```

3. Configure environment variables:
```bash
cp .env.example .env
```

4. `.env` Datei mit eigenen Credentials ausfüllen:
```env
# Mastodon API Credentials
MASTODON_BOT_ACCESS_TOKEN=your_access_token_here

# Bot Configuration
MASTODON_INSTANCE=https://mastodon.social
BT_FIRST_SAID_ACCOUNT=bt_first_said

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_MAX_REQUESTS=5
RATE_LIMIT_TIME_WINDOW=3600
```

4. Fill in the `.env` file with your own credentials:
```env
# Mastodon API Credentials
MASTODON_BOT_ACCESS_TOKEN=your_access_token_here

# Bot Configuration
MASTODON_INSTANCE=https://mastodon.social
BT_FIRST_SAID_ACCOUNT=bt_first_said

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_MAX_REQUESTS=5
RATE_LIMIT_TIME_WINDOW=3600
```

## Usage

### Start bot

```bash
uv run python main.py
```

### Stop bot

Graceful shutdown with:
- `Ctrl+C` (SIGINT)
- `kill <pid>` (SIGTERM)

The bot automatically saves its state when it shuts down.

### Running tests

```bash
# All tests
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=. --cov-report=html
```


## Configuration

All settings are controlled via environment variables in the `.env` file:

| Variable | Description | Default |
|----------|--------------|----------|
| `MASTODON_BOT_ACCESS_TOKEN` | API access token (required) | - |
| `MASTODON_INSTANCE` | Mastodon instance URL | `https://mastodon.social` |
| `BT_FIRST_SAID_ACCOUNT` | Account name to monitor | `bt_first_said` |
| `LAST_IDS_FILE` | File for state persistence | `last_ids.json` |
| `DEFAULT_LANGUAGE` | Fallback language | `en` |
| `RECONNECT_DELAY_SECONDS` | Wait time between reconnects | `30` |
| `MAX_RECONNECT_ATTEMPTS` | Max. reconnect attempts (0 = ∞) | `0` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` |
| `RATE_LIMIT_MAX_REQUESTS` | Max. requests per time window | `5` |
| `RATE_LIMIT_TIME_WINDOW` | Time window in seconds | `3600` |

## How it works

### Mention mode

The bot responds to @mentions with a single word:

**Input:**
```
@scrabble_bot Hello
```

**Response:**
```
The word ‘HELLO’ is worth 9 Scrabble points (English).
```

### Monitoring mode

The bot monitors posts from configured accounts (e.g. @bt_first_said) and automatically responds to one-word posts.

### Error handling

The bot sends localised error messages for:
- **Multiple words**: 'Please send me only one word.'
- **Invalid characters**: 'Please send me words with letters only.'
- **Rate limit**: 'You have sent too many requests. Please wait a moment.'
- **Unsupported language**: 'This language is not supported. Supported languages: German, English, French, ...'

### Unsupported languages

Words in unsupported languages (e.g. Japanese, Chinese, Arabic, Hebrew, Korean) are automatically detected and a helpful error message is sent instead of showing "0 points".

**Example:**
```
@scrabble_bot 日本語
→ "This language is not supported. Supported languages: German, English, French, Spanish, Italian, Dutch, Polish, Portuguese, Russian, Swedish, Turkish."
```

## Scrabble scoring system

Each language uses its own official Scrabble scoring system:

| Language | Example | Points |
|---------|----------|--------|
| German | HALLO | 9 |
| English | HELLO | 8 |
| French | BONJOUR | 16 |
| Spanish | HOLA | 5 |
| Russian | ПРИВЕТ | 12 |

## Architecture

```
scrabblebot.nosync/
├── main.py              # Bot logic, streaming, API integration
├── scrabble.py          # Point calculation, language recognition
├── test_bt_reply.py     # Manual tests
├── tests/               # Unit tests
│   ├── test_main.py
│   ├── test_scrabble.py
│   └── test_rate_limiting.py
├── .env                 # Configuration (not in repo)
├── .env.example         # Configuration template
├── pyproject.toml       # Dependencies
└── README.md            # This file
```

### Components

**RateLimiter**: Sliding window rate limiting per user
- Prevents spam
- Automatic cleanup of old entries
- Can be disabled for testing

**ScrabbleBot**: Main class with:
- Mastodon API integration
- Real-time streaming
- State persistence
- Retry logic for transient errors
- Graceful shutdown

**Scrabble module**: Score calculation with:
- Automatic language recognition
- 11 language dictionaries
- Localised response templates
- Word validation

## Deployment

### With systemd (recommended)

1. Create service file:
```bash
sudo nano /etc/systemd/system/scrabble-bot.service
```

2. Configuration:
```ini
[Unit]
Description=Mastodon Scrabble Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/scrabblebot.nosync
ExecStart=/usr/local/bin/uv run python main.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

3. Enable service:
```bash
sudo systemctl enable scrabble-bot
sudo systemctl start scrabble-bot
```

## Development

### Adding dependencies

```bash
uv add <package-name>
```

### Writing tests

Tests are located in `tests/` and use pytest:

```python
def test_example():
    ‘’‘Test description.’‘’
    assert True
```

### Code style

The project follows Python conventions:
- Type hints where appropriate
- Docstrings for all public functions
- Clear, descriptive variable names

## Troubleshooting

### Bot not responding

1. Check access token in `.env`
2. Check logs: set `LOG_LEVEL=DEBUG` in `.env`
3. Disable rate limiting for testing: `RATE_LIMIT_ENABLED=false`

### Reconnect issues

- Increase `RECONNECT_DELAY_SECONDS`
- `MAX_RECONNECT_ATTEMPTS=10` for debugging

### State issues

Reset last IDs:
```bash
rm last_ids.json
```

## Licence

The project is licensed under the [GNU General Public Licence 3](https://www.gnu.org/licenses/gpl-3.0.de.html).  