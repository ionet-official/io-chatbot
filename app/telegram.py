import asyncio
import logging
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from .models import Message
from .message_processor import MessageProcessor
from .config import PROCESSING_TIMEOUT, MODEL_NAME

logger = logging.getLogger(__name__)


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
                    
                    # Check if this is a private chat or group chat
                    if update.effective_chat.type == 'private':
                        # In private chats, send response without ping
                        response_text = msg.content
                    else:
                        # In group chats, ping the user first
                        user_mention = f"@{user.username}" if user.username else user.first_name or "User"
                        response_text = f"{user_mention} {msg.content}"
                    
                    await update.message.reply_text(response_text)
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
        
        # Keep the bot running until stopped
        try:
            while self.application.updater.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Telegram bot task cancelled")
            raise

    async def stop(self):
        """Stop the Telegram bot"""
        logger.info("Stopping Telegram Bot...")
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        logger.info("Telegram Bot stopped")