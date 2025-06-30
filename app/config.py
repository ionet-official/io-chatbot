import os
from dotenv import load_dotenv
import logging
logger = logging.getLogger(__name__)
load_dotenv()

# Required API configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.intelligence.io.solutions/api/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")
API_KEY = os.getenv("API_KEY")

# Validate required variables
if not API_KEY:
    raise ValueError("API_KEY environment variable is required")
if not DISCORD_TOKEN and not TELEGRAM_TOKEN:
    raise ValueError("Either DISCORD_TOKEN or TELEGRAM_TOKEN (or both) must be provided")

# Optional configuration with defaults
MAX_CONTEXT_MESSAGES = int(os.getenv("MAX_CONTEXT_MESSAGES", "20"))
MESSAGE_BATCH_SIZE = int(os.getenv("MESSAGE_BATCH_SIZE", "5"))
PROCESSING_TIMEOUT = float(os.getenv("PROCESSING_TIMEOUT", "25.0"))
RATE_LIMIT_DELAY = float(os.getenv("RATE_LIMIT_DELAY", "0.5"))
MAX_RESPONSE_LENGTH = int(os.getenv("MAX_RESPONSE_LENGTH", "2000"))
CONTEXT_CLEANUP_INTERVAL = int(os.getenv("CONTEXT_CLEANUP_INTERVAL", "300"))  # 5 minutes

# System prompt configuration
DEFAULT_SYSTEM_PROMPT = ("You are IO Chat, a helpful and conversational AI assistant. "
                         "You're chatting in a Discord/Telegram servers. Keep responses natural, "
                         "engaging, and appropriately sized for chat. Use Discord markdown "
                         "formatting when helpful (like **bold** or *italics*). "
                         "Be friendly but not overly enthusiastic.")

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)