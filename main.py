import asyncio
import logging
import os
from typing import Optional

from app.config import (
    DISCORD_TOKEN, TELEGRAM_TOKEN, API_BASE_URL, API_KEY, MODEL_NAME
)
from app.llm_client import LLMClient
from app.message_processor import MessageProcessor
from app.discord import DiscordBot
from app.telegram import TelegramBot

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, LOG_LEVEL, logging.DEBUG)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class BotManager:
    """Manages both Discord and Telegram bots with shared components"""

    def __init__(self):
        self.llm_client: Optional[LLMClient] = None
        self.message_processor: Optional[MessageProcessor] = None
        self.discord_bot: Optional[DiscordBot] = None
        self.telegram_bot: Optional[TelegramBot] = None

    async def initialize(self):
        """Initialize shared components"""
        logger.info("Initializing Bot Manager...")

        self.llm_client = LLMClient(API_BASE_URL, API_KEY, MODEL_NAME)
        await self.llm_client.__aenter__()

        self.message_processor = MessageProcessor(self.llm_client)

        if DISCORD_TOKEN:
            self.discord_bot = DiscordBot(self.message_processor)
            logger.info("Discord bot initialized")

        if TELEGRAM_TOKEN:
            self.telegram_bot = TelegramBot(TELEGRAM_TOKEN, self.message_processor)
            logger.info("Telegram bot initialized")

        logger.info("Bot Manager initialization complete")

    async def start(self):
        """Start all available bots"""
        if not self.discord_bot and not self.telegram_bot:
            raise RuntimeError("No bots available to start. Check your tokens.")

        tasks = []

        if self.discord_bot:
            tasks.append(asyncio.create_task(self.discord_bot.start(DISCORD_TOKEN)))

        if self.telegram_bot:
            tasks.append(asyncio.create_task(self.telegram_bot.start()))

        logger.info(f"Starting {len(tasks)} bot(s)...")
        await asyncio.gather(*tasks)

    async def stop(self):
        """Stop all bots and cleanup"""
        logger.info("Stopping Bot Manager...")

        tasks = []

        if self.discord_bot:
            tasks.append(asyncio.create_task(self.discord_bot.close()))

        if self.telegram_bot:
            tasks.append(asyncio.create_task(self.telegram_bot.stop()))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if self.llm_client:
            await self.llm_client.__aexit__(None, None, None)

        logger.info("Bot Manager stopped")


async def main():
    """Main entry point"""
    bot_manager = BotManager()

    try:
        await bot_manager.initialize()
        await bot_manager.start()
    except KeyboardInterrupt:
        logger.info("Bots stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
    finally:
        await bot_manager.stop()
        logger.info("All bots shutdown")


if __name__ == "__main__":
    asyncio.run(main())