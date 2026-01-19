# Scrabble Bot for Mastodon

A Mastodon bot that calculates Scrabble points for words in 11 different languages and responds in real time.

## Features

- **Multi-language support**: Supports 11 languages with automatic detection
  - German, English, French, Spanish, Italian, Dutch, Polish, Portuguese, Russian, Swedish, Turkish
- **Real-time streaming**: Instant responses via Mastodon's streaming API
- **Multiple operating modes**:
  - Responds to direct @mentions (public, unlisted, private)
  - Handles filtered mentions
  - Monitors posts from specific accounts (e.g. @bt_first_said)
- **Rate limiting**: Protection against spam with configurable sliding window
- **Word validation**: Checks for valid Scrabble characters
- **Unsupported language detection**: Helpful error messages for non-Latin scripts
- **Automatic reconnects**: Reliable operation with reconnect logic
- **Graceful shutdown**: Clean shutdown with state persistence
- **Duplicate prevention**: Multi-layer protection against duplicate responses
- **Comprehensive testing**: 66 unit tests with pytest

## Installation

### Requirements

- Python 3.12+
- uv (recommended package manager)
- Mastodon account with API access

### Setup

1. Clone repository:
```bash
git clone https://github.com/ungeschneuer/scrabblebot.git
cd scrabblebot
```

2. Install dependencies:
```bash
uv sync
```

3. Configure environment variables:
```bash
cp .env.example .env
```

4. Fill in the `.env` file with your own credentials:
```env
# Mastodon API Credentials
MASTODON_BOT_CLIENT_ID=your_client_id_here
MASTODON_BOT_CLIENT_SECRET=your_client_secret_here
MASTODON_BOT_ACCESS_TOKEN=your_access_token_here

# Bot Configuration
MASTODON_INSTANCE=https://mastodon.social
BT_FIRST_SAID_ACCOUNT=bt_first_said
LAST_IDS_FILE=last_ids.json

# Bot Behavior
DEFAULT_LANGUAGE=de
RECONNECT_DELAY_SECONDS=30
MAX_RECONNECT_ATTEMPTS=0
LOG_LEVEL=INFO

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
| `MASTODON_BOT_CLIENT_ID` | API client ID | - |
| `MASTODON_BOT_CLIENT_SECRET` | API client secret | - |
| `MASTODON_BOT_ACCESS_TOKEN` | API access token (required) | - |
| `MASTODON_INSTANCE` | Mastodon instance URL | `https://mastodon.social` |
| `BT_FIRST_SAID_ACCOUNT` | Account to monitor (optional) | None (mention-only mode) |
| `LAST_IDS_FILE` | File for state persistence | `last_ids.json` |
| `DEFAULT_LANGUAGE` | Fallback language | `de` |
| `RECONNECT_DELAY_SECONDS` | Wait time between reconnects | `30` |
| `MAX_RECONNECT_ATTEMPTS` | Max reconnect attempts (0 = infinite) | `0` |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` |
| `RATE_LIMIT_MAX_REQUESTS` | Max requests per time window | `5` |
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
Das Wort "HELLO" ist 8 Scrabble-Punkte wert (Englisch).
```

### Direct/Private mentions

The bot responds to direct mentions as direct messages:

**Input (direct message):**
```
@scrabble_bot Secret
```

**Response (direct message):**
```
Das Wort "SECRET" ist 8 Scrabble-Punkte wert (Englisch).
```

### Filtered mentions

The bot processes filtered mentions just like regular mentions, ensuring no mentions are missed.

### Monitoring mode (optional)

The bot can optionally monitor posts from specific accounts (e.g. @bt_first_said) and automatically respond to single-word posts. This feature is enabled by setting `BT_FIRST_SAID_ACCOUNT` in `.env`. If not configured, the bot operates in mention-only mode.

### Error handling

The bot sends localized error messages for:
- **Multiple words**: "Bitte sende mir nur ein Wort."
- **Invalid characters**: "Bitte sende mir nur Wörter mit Buchstaben."
- **Rate limit**: "Du hast zu viele Anfragen gesendet. Bitte warte einen Moment."
- **Unsupported language**: "Diese Sprache wird nicht unterstützt. Unterstützte Sprachen: Deutsch, Englisch, Französisch, ..."

### Unsupported languages

Words in unsupported languages (e.g. Japanese, Chinese, Arabic, Hebrew, Korean) are automatically detected and a helpful error message is sent instead of showing "0 points".

**Example:**
```
@scrabble_bot 日本語
Response: "Diese Sprache wird nicht unterstützt. Unterstützte Sprachen: Deutsch, Englisch, Französisch, Spanisch, Italienisch, Niederländisch, Polnisch, Portugiesisch, Russisch, Schwedisch, Türkisch."
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
scrabblebot/
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
- State persistence (last processed IDs)
- In-memory duplicate prevention cache
- Retry logic for transient errors
- Graceful shutdown with signal handlers
- Single instance enforcement via PID file

**ScrabbleListener**: Stream listener that handles:
- Regular mentions (public, unlisted)
- Direct/private mentions
- Filtered mentions
- Posts from monitored accounts

**Scrabble module**: Score calculation with:
- Automatic language recognition
- 11 language dictionaries
- Localized response templates
- Word validation

### Duplicate Prevention

The bot uses multiple layers to prevent duplicate responses:
1. **In-memory cache**: Recently processed status IDs
2. **Persistent state**: Last processed mention/post IDs saved to disk
3. **Immediate state saving**: State saved before processing to handle crashes
4. **Reply tracking**: Bot's own replies are added to cache
5. **PID file**: Prevents multiple bot instances from running

## Deployment

### With supervisord (Uberspace)

1. Create supervisord config:
```bash
nano ~/etc/services.d/scrabble-bot.ini
```

2. Configuration:
```ini
[program:scrabble-bot]
command=%(ENV_HOME)s/.local/bin/uv run python3 main.py
directory=%(ENV_HOME)s/bots/scrabblebot
autostart=yes
autorestart=yes
startsecs=30
startretries=3
```

3. Reload and start:
```bash
supervisorctl reread
supervisorctl update
supervisorctl start scrabble-bot
```

4. Monitor:
```bash
supervisorctl status
tail -f ~/logs/scrabble-bot.log
```

### With systemd

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
WorkingDirectory=/path/to/scrabblebot
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
sudo systemctl status scrabble-bot
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
    """Test description."""
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
4. Verify bot is running: `ps aux | grep "python.*main.py"`

### Multiple instances running

Check for multiple processes:
```bash
ps aux | grep "python.*main.py" | grep -v grep
```

Stop all and restart:
```bash
supervisorctl stop scrabble-bot
pkill -9 -f "python.*main.py"
rm -f /tmp/scrabble-bot.pid
supervisorctl start scrabble-bot
```

### Reconnect issues

- Increase `RECONNECT_DELAY_SECONDS`
- Set `MAX_RECONNECT_ATTEMPTS=10` for debugging
- Check logs for specific error messages

### State issues

Reset last processed IDs:
```bash
rm last_ids.json
```

Note: This will cause the bot to reprocess recent mentions.

## License

The project is licensed under the [GNU General Public License 3](https://www.gnu.org/licenses/gpl-3.0.en.html).
