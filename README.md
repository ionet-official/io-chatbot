# IO Chat Bot

A sophisticated multi-platform conversational bot (Discord & Telegram) powered by LLM with advanced message processing and shared conversation context management.

## Features

- 🤖 **LLM Integration**: Uses `meta-llama/Llama-3.3-70B-Instruct` via OpenAI-compatible API
- 🔄 **Multi-Platform**: Discord and Telegram support with shared conversation context
- 💬 **Context Awareness**: Maintains conversation history per channel/chat
- ⚡ **Async Processing**: Queue-based message processing with flow control
- 🔧 **Flexible Deployment**: Run Discord only, Telegram only, or both simultaneously
- 🛡️ **Robust**: Error handling, rate limiting, and automatic cleanup

## Quick Start

### 1. Clone and Setup

```bash
git clone <your-repo>
cd io-chat-bot
```

### 2. Configure Environment

Copy the example environment file and edit with your credentials:

```bash
cp .env.example .env
# Edit .env with your tokens
```

Required variables:
```bash
# At least one platform token is required
API_KEY=your_intelligence_io_api_key_here

# Platform tokens (provide one or both)
DISCORD_TOKEN=your_discord_bot_token_here
TELEGRAM_TOKEN=your_telegram_bot_token_here
```

### 3. Run with Docker (Recommended)

```bash
# Build the image
docker build -t io-chat-bot .

# Run the container with environment file
docker run --env-file .env io-chat-bot
```

### 4. Alternative: Run with Python

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python io_chat_bot.py
```

## Getting Your Tokens

### Discord Bot Token (Optional)

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to `Bot` section
4. Create a bot and copy the token
5. Enable `Message Content Intent` in Bot settings
6. Invite bot to your server with appropriate permissions

### Telegram Bot Token (Optional)

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the bot token provided
5. Optionally set bot commands with `/setcommands`

### Intelligence.io API Key (Required)

1. Visit [IO Intelligence](https://ai.io.net/)
2. Sign up/login to your account
3. Generate an API key for `Llama-3.3-70B-Instruct` access

## Bot Usage

### Discord Bot

The Discord bot responds to:
- **Mentions**: `@IO Chat hello there!`
- **Direct Messages**: Send DM to the bot
- **Replies**: Reply to any bot message

**Commands:**
- `!io help` - Show help information
- `!io status` - Display bot status and uptime
- `!io clear` - Clear conversation context for current channel

### Telegram Bot

The Telegram bot responds to:
- **All Messages**: Send any message directly to the bot
- **Group Chats**: Add the bot to a group and interact normally

**Commands:**
- `/help` - Show help information
- `/status` - Display bot status and uptime
- `/clear` - Clear conversation context for current chat

### Cross-Platform Features

- **Shared Context**: Conversations are managed independently per platform
- **Same LLM Backend**: Consistent AI responses across platforms
- **Unified Processing**: Same message processing pipeline for both platforms

## Configuration Options

You can customize bot behavior by adding these to your `.env` file:

```bash
# Context and Processing
MAX_CONTEXT_MESSAGES=20        # Messages to keep in context
MESSAGE_BATCH_SIZE=5           # Messages processed per batch
PROCESSING_TIMEOUT=25.0        # Max seconds to wait for response
RATE_LIMIT_DELAY=0.5          # Delay between API calls
MAX_RESPONSE_LENGTH=2000       # Max characters in bot response

# Cleanup
CONTEXT_CLEANUP_INTERVAL=300   # Seconds between context cleanup
```

## Architecture

### Core Components

- **LLMClient**: Handles API communication with Intelligence.io
- **MessageProcessor**: Manages queues, locks, and batch processing (shared between platforms)
- **ConversationContext**: Maintains chat history per channel/chat
- **DiscordBot**: Discord bot implementation with command handling
- **TelegramBot**: Telegram bot implementation with command handling
- **BotManager**: Coordinates both platforms with shared components

### Message Flow

1. User sends message → Bot detects mention/DM/reply
2. Message added to channel-specific queue
3. Batch processor collects messages
4. Context prepared with conversation history
5. LLM generates response
6. Response sent to Discord channel

## Development

### Project Structure

```
io-chat-bot/
├── io_chat_bot.py        # Main bot file
├── requirements.txt      # Python dependencies
├── Dockerfile           # Docker container config
├── .dockerignore        # Docker ignore rules
├── .env.example         # Environment template
├── .env                 # Your configuration (create this)
├── logs/                # Log files directory
└── README.md            # This file
```

### Extending the Bot

The bot is designed for easy extension:

- **Tool Integration**: Add tool calling in `LLMClient.generate_response()`
- **New Platforms**: Extend `MessageProcessor` for Telegram support
- **Custom Commands**: Add methods with `@commands.command()` decorator

### Logging

Logs are written to both console and `io_chat_bot.log` file. Set log level in the code:

```python
logging.basicConfig(level=logging.INFO)  # or DEBUG for verbose
```

## Troubleshooting

### Common Issues

**Bot doesn't respond:**
- Check Discord permissions (`Read Messages`, `Send Messages`)
- Verify `Message Content Intent` is enabled
- Check logs for API errors

**API errors:**
- Verify `API_KEY` is correct
- Check `API_BASE_URL` endpoint
- Ensure sufficient API credits

**Installation issues:**
- Python 3.8+ required
- Install with: `pip install -r requirements.txt`

**Docker issues:**
- Ensure Docker is installed
- Check `.env` file exists and has correct tokens
- View logs: `docker logs <container_id>`

### Debug Mode

Set logging to `DEBUG` for detailed information about message processing:

```python
# In io_chat_bot.py, change line 31 from:
logging.basicConfig(
    level=logging.INFO,
    # ... rest of config
)

# To:
logging.basicConfig(
    level=logging.DEBUG,
    # ... rest of config
)
```

**Debug logs include:**
- Message queue operations and sizes
- Processing task lifecycle
- LLM API requests and responses
- Context management and cleanup
- Message flow and timing
- Response generation details

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

For issues and questions:
- Check the troubleshooting section
- Review logs in `io_chat_bot.log`
- Open an issue on GitHub

---

**Powered by IO Intelligence** 🚀