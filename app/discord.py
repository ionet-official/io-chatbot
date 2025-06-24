import asyncio
import logging
import time
import discord
from discord.ext import commands, tasks

from .models import Message
from .message_processor import MessageProcessor
from .config import CONTEXT_CLEANUP_INTERVAL, PROCESSING_TIMEOUT, MODEL_NAME

logger = logging.getLogger(__name__)


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