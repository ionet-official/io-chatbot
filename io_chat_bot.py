import asyncio
import logging
import time
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import defaultdict, deque
import aiohttp
import discord
from discord.ext import commands, tasks
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, LOG_LEVEL, logging.DEBUG)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.intelligence.io.solutions/api/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")
API_KEY = os.getenv("API_KEY")

if not API_KEY:
    raise ValueError("API_KEY environment variable is required")
if not DISCORD_TOKEN and not TELEGRAM_TOKEN:
    raise ValueError("Either DISCORD_TOKEN or TELEGRAM_TOKEN (or both) must be provided")

MAX_CONTEXT_MESSAGES = int(os.getenv("MAX_CONTEXT_MESSAGES", "20"))
MESSAGE_BATCH_SIZE = int(os.getenv("MESSAGE_BATCH_SIZE", "5"))
PROCESSING_TIMEOUT = float(os.getenv("PROCESSING_TIMEOUT", "25.0"))
RATE_LIMIT_DELAY = float(os.getenv("RATE_LIMIT_DELAY", "0.5"))
MAX_RESPONSE_LENGTH = int(os.getenv("MAX_RESPONSE_LENGTH", "2000"))
CONTEXT_CLEANUP_INTERVAL = int(os.getenv("CONTEXT_CLEANUP_INTERVAL", "300"))  # 5 minutes


@dataclass
class Message:
    """Represents a message in the conversation context"""
    content: str
    author: str
    timestamp: float
    channel_id: int
    message_id: int
    is_bot: bool = False


@dataclass
class ConversationContext:
    """Manages conversation context for a channel"""
    messages: deque = field(default_factory=lambda: deque(maxlen=MAX_CONTEXT_MESSAGES))
    last_activity: float = field(default_factory=time.time)
    processing: bool = False

    def add_message(self, message: Message) -> None:
        """Add a message to the context"""
        self.messages.append(message)
        self.last_activity = time.time()

    def get_context_messages(self) -> List[Dict[str, str]]:
        """Get formatted messages for LLM context"""
        context = []
        for msg in self.messages:
            role = "assistant" if msg.is_bot else "user"
            content = f"{msg.author}: {msg.content}" if not msg.is_bot else msg.content
            context.append({"role": role, "content": content})
        return context

    def is_stale(self, max_age: float = 1800) -> bool:
        """Check if context is stale (no activity for max_age seconds)"""
        return time.time() - self.last_activity > max_age


class LLMClient:
    """Handles communication with the LLM API"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def generate_response(self, messages: List[Dict[str, str]],
                                max_tokens: int = 500,
                                temperature: float = 0.7) -> Optional[str]:
        """Generate a response using the LLM API"""
        if not self.session:
            raise RuntimeError("LLMClient not initialized. Use async context manager.")

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }

        logger.debug(f"Sending request to LLM API: {self.base_url}/chat/completions")
        logger.debug(f"Payload: model={self.model}, messages={len(messages)}, max_tokens={max_tokens}, temp={temperature}")

        try:
            async with self.session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload
            ) as response:
                logger.debug(f"LLM API response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    response_content = data["choices"][0]["message"]["content"].strip()
                    logger.debug(f"LLM API response received, length: {len(response_content)}")
                    return response_content
                else:
                    error_text = await response.text()
                    logger.error(f"LLM API error {response.status}: {error_text}")
                    return None
        except asyncio.TimeoutError:
            logger.error("LLM API request timed out")
            return None
        except Exception as e:
            logger.error(f"LLM API request failed: {e}")
            return None


class MessageProcessor:
    """Handles message processing with queues and flow control"""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.message_queues: Dict[int, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.processing_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.contexts: Dict[int, ConversationContext] = defaultdict(ConversationContext)
        self.processing_tasks: Dict[int, asyncio.Task] = {}

    async def add_message(self, channel_id: int, message: Message) -> Optional[str]:
        """Add a message to the processing queue and return the response"""
        logger.debug(f"Adding message to queue for channel {channel_id}: {message.content[:100]}...")
        await self.message_queues[channel_id].put(message)
        logger.debug(f"Queue size for channel {channel_id}: {self.message_queues[channel_id].qsize()}")

        # Start processing task if not already running
        if channel_id not in self.processing_tasks or self.processing_tasks[channel_id].done():
            logger.debug(f"Starting new processing task for channel {channel_id}")
            self.processing_tasks[channel_id] = asyncio.create_task(
                self._process_channel_messages(channel_id)
            )
        else:
            logger.debug(f"Processing task already running for channel {channel_id}")

        # Wait for the processing task to complete and return the result
        try:
            logger.debug(f"Waiting for processing task to complete for channel {channel_id}")
            response = await asyncio.wait_for(self.processing_tasks[channel_id], timeout=PROCESSING_TIMEOUT)
            logger.debug(f"Processing completed for channel {channel_id}, response length: {len(response) if response else 0}")
            return response
        except asyncio.TimeoutError:
            logger.warning(f"Processing timeout for channel {channel_id}")
            return "Sorry, I'm taking too long to respond. Please try again!"
        except Exception as e:
            logger.error(f"Error processing message for channel {channel_id}: {e}")
            return "I encountered an error processing your message. Please try again!"

    async def _process_channel_messages(self, channel_id: int) -> str:
        """Process messages for a specific channel"""
        logger.debug(f"Starting message processing for channel {channel_id}")
        async with self.processing_locks[channel_id]:
            queue = self.message_queues[channel_id]
            context = self.contexts[channel_id]
            logger.debug(f"Acquired processing lock for channel {channel_id}")

            while not queue.empty():
                logger.debug(f"Processing batch for channel {channel_id}, queue size: {queue.qsize()}")
                # Collect batch of messages
                batch = []
                for _ in range(min(MESSAGE_BATCH_SIZE, queue.qsize())):
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=0.1)
                        batch.append(message)
                        logger.debug(f"Added message to batch: {message.content[:50]}...")
                    except asyncio.TimeoutError:
                        logger.debug("Timeout waiting for message in batch collection")
                        break

                if not batch:
                    logger.debug(f"No messages in batch for channel {channel_id}")
                    break

                logger.debug(f"Processing batch of {len(batch)} messages for channel {channel_id}")
                # Add messages to context
                for message in batch:
                    context.add_message(message)

                # Generate response for the last user message in batch
                last_user_message = None
                for message in reversed(batch):
                    if not message.is_bot:
                        last_user_message = message
                        break

                if last_user_message:
                    logger.debug(f"Generating response for message: {last_user_message.content[:50]}...")
                    response = await self._generate_and_send_response(channel_id, last_user_message)
                    if response:
                        logger.debug(f"Generated response for channel {channel_id}: {response[:50]}...")
                        return response
                    else:
                        logger.debug(f"No response generated for channel {channel_id}")

                # Rate limiting
                logger.debug(f"Applying rate limit delay of {RATE_LIMIT_DELAY}s")
                await asyncio.sleep(RATE_LIMIT_DELAY)

            logger.debug(f"Completed processing for channel {channel_id}, no response generated")
            return ""

    async def _generate_and_send_response(self, channel_id: int, user_message: Message) -> Optional[str]:
        """Generate and send a response to a user message"""
        logger.debug(f"Generating response for channel {channel_id}, user: {user_message.author}")
        context = self.contexts[channel_id]
        context.processing = True

        try:
            # Get conversation context
            context_messages = context.get_context_messages()
            logger.debug(f"Retrieved {len(context_messages)} context messages for channel {channel_id}")

            # Add system prompt
            system_prompt = {
                "role": "system",
                "content": ("You are IO Chat, a helpful and conversational AI assistant. "
                            "You're chatting in a Discord server. Keep responses natural, "
                            "engaging, and appropriately sized for chat. Use Discord markdown "
                            "formatting when helpful (like **bold** or *italics*). "
                            "Be friendly but not overly enthusiastic.")
            }

            messages = [system_prompt] + context_messages
            logger.debug(f"Prepared {len(messages)} messages for LLM API call")

            # Generate response
            logger.debug(f"Calling LLM API for channel {channel_id}")
            response = await self.llm_client.generate_response(messages)

            if response:
                logger.debug(f"LLM API returned response for channel {channel_id}, length: {len(response)}")
                if len(response) > MAX_RESPONSE_LENGTH:
                    logger.debug(f"Truncating response from {len(response)} to {MAX_RESPONSE_LENGTH} characters")
                    response = response[:MAX_RESPONSE_LENGTH-3] + "..."

                bot_message = Message(
                    content=response,
                    author="IO Chat",
                    timestamp=time.time(),
                    channel_id=channel_id,
                    message_id=0,  # Will be set when sent
                    is_bot=True
                )
                context.add_message(bot_message)
                logger.debug(f"Added bot response to context for channel {channel_id}")

                return response
            else:
                logger.debug(f"LLM API returned empty response for channel {channel_id}")
                return "Sorry, I'm having trouble generating a response right now. Please try again!"

        except Exception as e:
            logger.error(f"Error generating response for channel {channel_id}: {e}")
            return "Oops! Something went wrong. Please try again later."
        finally:
            context.processing = False
            logger.debug(f"Set processing=False for channel {channel_id}")

    def cleanup_stale_contexts(self) -> None:
        """Remove stale conversation contexts"""
        logger.debug(f"Starting context cleanup, total contexts: {len(self.contexts)}")
        stale_channels = [
            channel_id for channel_id, context in self.contexts.items()
            if context.is_stale()
        ]

        logger.debug(f"Found {len(stale_channels)} stale contexts to clean up")

        for channel_id in stale_channels:
            logger.info(f"Cleaning up stale context for channel {channel_id}")
            del self.contexts[channel_id]
            if channel_id in self.message_queues:
                logger.debug(f"Removing message queue for channel {channel_id}")
                del self.message_queues[channel_id]
            if channel_id in self.processing_locks:
                logger.debug(f"Removing processing lock for channel {channel_id}")
                del self.processing_locks[channel_id]
            if channel_id in self.processing_tasks:
                task = self.processing_tasks[channel_id]
                if not task.done():
                    logger.debug(f"Canceling processing task for channel {channel_id}")
                    task.cancel()
                del self.processing_tasks[channel_id]

        logger.debug(f"Context cleanup completed, remaining contexts: {len(self.contexts)}")


def get_prefix(bot, message):
    """Custom prefix function that handles both '!io ' and '!io' formats"""
    return ['!io ', '!io']

class DiscordBot(commands.Bot):
    """Discord bot implementation"""

    def __init__(self, message_processor: MessageProcessor):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            help_command=None,
            case_insensitive=True
        )

        self.message_processor = message_processor
        self.start_time = time.time()

    async def setup_hook(self):
        """Initialize the Discord bot components"""
        logger.info("Setting up Discord Bot...")

        # Start background tasks
        self.cleanup_task.start()

        @self.command(name='help')
        async def help_cmd(ctx):
            """Show help information"""
            logger.debug(f"Help command called by {ctx.author.display_name} in channel {ctx.channel.id}")
            embed = discord.Embed(
                title="🤖 IO Chat Bot Help",
                description="A conversational AI assistant powered by Llama-3.3-70B",
                color=0x00ff88
            )
            embed.add_field(
                name="💬 Chat with me",
                value="• Mention me (@IO Chat) in any message\n"
                      "• Reply to my messages\n"
                      "• Send me a DM\n"
                      "• I maintain conversation context!",
                inline=False
            )
            embed.add_field(
                name="🛠️ Commands",
                value="• `!io help` - Show this help\n"
                      "• `!io status` - Bot status\n"
                      "• `!io clear` - Clear conversation context",
                inline=False
            )
            embed.add_field(
                name="ℹ️ Features",
                value="• Context-aware conversations\n"
                      "• Batch message processing\n"
                      "• Smart flow control\n"
                      "• Extensible architecture",
                inline=False
            )
            embed.set_footer(text="Powered by Intelligence.io Solutions")
            await ctx.send(embed=embed)

        @self.command(name='status')
        async def status_cmd(ctx):
            """Show bot status"""
            uptime = time.time() - self.start_time
            uptime_str = f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s"
            active_contexts = len(self.message_processor.contexts) if self.message_processor else 0
            embed = discord.Embed(title="🤖 IO Chat Bot Status", color=0x00ff88)
            embed.add_field(name="Uptime", value=uptime_str, inline=True)
            embed.add_field(name="Guilds", value=len(self.guilds), inline=True)
            embed.add_field(name="Active Contexts", value=active_contexts, inline=True)
            embed.add_field(name="Model", value=MODEL_NAME, inline=False)
            await ctx.send(embed=embed)

        @self.command(name='clear')
        async def clear_cmd(ctx):
            """Clear conversation context for this channel"""
            if self.message_processor and ctx.channel.id in self.message_processor.contexts:
                del self.message_processor.contexts[ctx.channel.id]
                await ctx.send("🗑️ Conversation context cleared!")
            else:
                await ctx.send("💭 No conversation context to clear.")

        logger.info("Discord Bot setup complete")

    async def close(self):
        """Clean shutdown"""
        logger.info("Shutting down Discord Bot...")

        if hasattr(self, 'cleanup_task'):
            self.cleanup_task.cancel()

        await super().close()
        logger.info("Discord Bot shutdown complete")

    async def on_ready(self):
        """Called when the bot is ready"""
        logger.info(f"{self.user} has connected to Discord!")
        logger.info(f"Bot is in {len(self.guilds)} guilds")

        logger.debug(f"Registered commands: {[cmd.name for cmd in self.commands]}")
        logger.debug(f"Command prefix: {self.command_prefix}")
        for cmd in self.commands:
            logger.debug(f"Command: {cmd.name}, aliases: {cmd.aliases}")

        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="your conversations | !io help"
        )
        await self.change_presence(activity=activity)

    async def on_message(self, message: discord.Message):
        """Handle incoming messages"""
        # Ignore bot messages (except for context)
        if message.author == self.user:
            return

        logger.debug(f"Received message from {message.author.display_name} in channel {message.channel.id}: {message.content[:100]}...")

        await self.process_commands(message)

        if message.content.startswith('!io'):
            logger.debug(f"Message {message.content} is a command, skipping processing")
            return

        # Check if bot is mentioned or in DM
        is_mentioned = self.user in message.mentions
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_reply_to_bot = (message.reference and
                           message.reference.resolved and
                           message.reference.resolved.author == self.user)

        logger.debug(f"Message triggers: mentioned={is_mentioned}, dm={is_dm}, reply_to_bot={is_reply_to_bot}")

        if not (is_mentioned or is_dm or is_reply_to_bot):
            logger.debug("Message doesn't trigger bot, ignoring")
            return

        logger.debug(f"Processing message from {message.author.display_name}")

        msg = Message(
            content=message.clean_content,
            author=message.author.display_name,
            timestamp=message.created_at.timestamp(),
            channel_id=message.channel.id,
            message_id=message.id
        )

        if self.message_processor:
            logger.debug(f"Adding message to processor for channel {message.channel.id}")
            await self.message_processor.add_message(message.channel.id, msg)

            async with message.channel.typing():
                logger.debug(f"Showing typing indicator for channel {message.channel.id}")
                # Wait for processing to complete or timeout
                context = self.message_processor.contexts[message.channel.id]
                wait_time = 0
                while context.processing and wait_time < PROCESSING_TIMEOUT:
                    await asyncio.sleep(0.5)
                    wait_time += 0.5

                logger.debug(f"Processing completed for channel {message.channel.id}, wait_time: {wait_time}s")

                # Get the latest bot message from context
                for msg in reversed(context.messages):
                    if msg.is_bot:
                        logger.debug(f"Sending bot response to channel {message.channel.id}: {msg.content[:50]}...")
                        await message.channel.send(msg.content)
                        break
        else:
            logger.error("Message processor not initialized")

    @tasks.loop(seconds=CONTEXT_CLEANUP_INTERVAL)
    async def cleanup_task(self):
        """Periodic cleanup of stale contexts"""
        if self.message_processor:
            self.message_processor.cleanup_stale_contexts()

    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        """Wait for bot to be ready before starting cleanup"""
        await self.wait_until_ready()


class TelegramBot:
    """Telegram bot implementation"""

    def __init__(self, token: str, message_processor: MessageProcessor):
        self.token = token
        self.message_processor = message_processor
        self.application = Application.builder().token(token).build()
        self.start_time = time.time()
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup message and command handlers"""
        self.application.add_handler(CommandHandler("help", self._help_command))
        self.application.add_handler(CommandHandler("status", self._status_command))
        self.application.add_handler(CommandHandler("clear", self._clear_command))

        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

        logger.info("Telegram Bot handlers setup complete")

    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help information"""
        logger.debug(f"Help command called by {update.effective_user.first_name} in chat {update.effective_chat.id}")

        help_text = """🤖 *IO Chat Bot Help*

A conversational AI assistant powered by Llama-3.3-70B

💬 *Chat with me*
• Send me any message directly
• I maintain conversation context!

🛠️ *Commands*
• `/help` - Show this help
• `/status` - Bot status  
• `/clear` - Clear conversation context

ℹ️ *Features*
• Context-aware conversations
• Batch message processing
• Smart flow control
• Extensible architecture

*Powered by IO Intelligence* 🚀"""

        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot status"""
        uptime = time.time() - self.start_time
        uptime_str = f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s"
        active_contexts = len(self.message_processor.contexts) if self.message_processor else 0

        status_text = f"""🤖 *IO Chat Bot Status*

⏱️ Uptime: `{uptime_str}`
💬 Active Contexts: `{active_contexts}`
🧠 Model: `{MODEL_NAME}`"""

        await update.message.reply_text(status_text, parse_mode='Markdown')

    async def _clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clear conversation context for this chat"""
        chat_id = update.effective_chat.id
        if self.message_processor and chat_id in self.message_processor.contexts:
            del self.message_processor.contexts[chat_id]
            await update.message.reply_text("🗑️ Conversation context cleared!")
        else:
            await update.message.reply_text("💭 No conversation context to clear.")

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages"""
        if not update.message or not update.message.text:
            return

        user = update.effective_user
        chat_id = update.effective_chat.id
        message_text = update.message.text

        logger.debug(f"Received message from {user.first_name} in chat {chat_id}: {message_text[:100]}...")

        msg = Message(
            content=message_text,
            author=user.first_name or user.username or "Unknown",
            timestamp=update.message.date.timestamp(),
            channel_id=chat_id,
            message_id=update.message.message_id
        )

        if self.message_processor:
            logger.debug(f"Adding message to processor for chat {chat_id}")

            await context.bot.send_chat_action(chat_id=chat_id, action="typing")

            await self.message_processor.add_message(chat_id, msg)

            msg_context = self.message_processor.contexts[chat_id]
            wait_time = 0
            while msg_context.processing and wait_time < PROCESSING_TIMEOUT:
                await asyncio.sleep(0.5)
                wait_time += 0.5

            logger.debug(f"Processing completed for chat {chat_id}, wait_time: {wait_time}s")

            for msg in reversed(msg_context.messages):
                if msg.is_bot:
                    logger.debug(f"Sending bot response to chat {chat_id}: {msg.content[:50]}...")
                    await update.message.reply_text(msg.content)
                    break
        else:
            logger.error("Message processor not initialized")

    async def start(self):
        """Start the Telegram bot"""
        logger.info("Starting Telegram Bot...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram Bot started successfully")

    async def stop(self):
        """Stop the Telegram bot"""
        logger.info("Stopping Telegram Bot...")
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        logger.info("Telegram Bot stopped")


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