import asyncio
import time
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from telegram import Update, User, Chat, Message as TelegramMessage
from telegram.ext import ContextTypes

from app.telegram import TelegramBot
from app.models import Message
from app.message_processor import MessageProcessor


class TestTelegramBot:
    """Test cases for TelegramBot class"""

    @pytest.fixture
    def mock_message_processor(self):
        """Create a mock message processor"""
        processor = Mock(spec=MessageProcessor)
        processor.contexts = {}
        return processor

    @pytest.fixture
    def telegram_bot(self, mock_message_processor):
        """Create a TelegramBot instance with mock dependencies"""
        with patch('telegram.ext.Application.builder') as mock_builder:
            mock_app = Mock()
            mock_builder.return_value.token.return_value.build.return_value = mock_app
            
            bot = TelegramBot("test_token", mock_message_processor)
            bot.application = mock_app
            return bot

    def test_init_sets_correct_attributes(self, mock_message_processor):
        """Test that TelegramBot initialization sets correct attributes"""
        with patch('telegram.ext.Application.builder') as mock_builder:
            mock_app = Mock()
            mock_builder.return_value.token.return_value.build.return_value = mock_app
            
            bot = TelegramBot("test_token", mock_message_processor)
            
            assert bot.token == "test_token"
            assert bot.message_processor is mock_message_processor
            assert isinstance(bot.start_time, float)
            assert bot.application is mock_app

    def test_setup_handlers_adds_correct_handlers(self, telegram_bot):
        """Test that setup_handlers adds the correct handlers"""
        telegram_bot.application.add_handler = Mock()
        
        telegram_bot._setup_handlers()
        
        # Should add 4 handlers: help, status, clear commands, and message handler
        assert telegram_bot.application.add_handler.call_count == 4

    @pytest.mark.asyncio
    async def test_help_command(self, telegram_bot):
        """Test help command functionality"""
        # Mock update and context
        update = Mock()
        update.effective_user.first_name = "TestUser"
        update.effective_chat.id = 123
        update.message.reply_text = AsyncMock()
        
        context = Mock()
        
        await telegram_bot._help_command(update, context)
        
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "IO Chat Bot Help" in call_args[0][0]
        assert call_args[1]['parse_mode'] == 'Markdown'

    @pytest.mark.asyncio
    async def test_status_command(self, telegram_bot):
        """Test status command functionality"""
        # Set a known start time
        telegram_bot.start_time = time.time() - 3661  # 1 hour, 1 minute, 1 second ago
        telegram_bot.message_processor.contexts = {'1': Mock(), '2': Mock()}
        
        update = Mock()
        update.message.reply_text = AsyncMock()
        context = Mock()
        
        await telegram_bot._status_command(update, context)
        
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        status_text = call_args[0][0]
        
        assert "IO Chat Bot Status" in status_text
        assert "1h 1m 1s" in status_text
        assert "Active Contexts: `2`" in status_text
        assert call_args[1]['parse_mode'] == 'Markdown'

    @pytest.mark.asyncio
    async def test_clear_command_with_context(self, telegram_bot):
        """Test clear command when context exists"""
        update = Mock()
        update.effective_chat.id = 123
        update.message.reply_text = AsyncMock()
        context = Mock()
        
        # Add context to processor
        telegram_bot.message_processor.contexts[123] = Mock()
        
        await telegram_bot._clear_command(update, context)
        
        # Context should be removed
        assert 123 not in telegram_bot.message_processor.contexts
        update.message.reply_text.assert_called_once_with("🗑️ Conversation context cleared!")

    @pytest.mark.asyncio
    async def test_clear_command_without_context(self, telegram_bot):
        """Test clear command when no context exists"""
        update = Mock()
        update.effective_chat.id = 123
        update.message.reply_text = AsyncMock()
        context = Mock()
        
        await telegram_bot._clear_command(update, context)
        
        update.message.reply_text.assert_called_once_with("💭 No conversation context to clear.")

    @pytest.mark.asyncio
    async def test_handle_message_success(self, telegram_bot):
        """Test successful message handling with bot mention"""
        # Create mock update
        update = Mock()
        update.message = Mock()
        update.message.text = "Hello @testbot!"  # Include bot mention
        update.effective_user = Mock()
        update.effective_user.first_name = "TestUser"
        update.effective_user.username = "testuser"
        update.effective_chat.id = 123
        update.effective_chat.type = 'group'  # Simulate group chat to test mention behavior
        update.message.date.timestamp.return_value = 1234567890.0
        update.message.message_id = 456
        update.message.reply_text = AsyncMock()
        update.message.reply_to_message = None  # No reply
        
        # Create mock context
        context = Mock()
        context.bot.send_chat_action = AsyncMock()
        context.bot.username = "testbot"  # Set bot username for mention detection
        context.bot.id = 999  # Bot ID
        
        # Mock message processor
        telegram_bot.message_processor.add_message = AsyncMock()
        telegram_bot.message_processor.contexts = {123: Mock()}
        telegram_bot.message_processor.contexts[123].processing = False
        
        # Mock bot response
        bot_message = Mock()
        bot_message.is_bot = True
        bot_message.content = "Hi there!"
        telegram_bot.message_processor.contexts[123].messages = [bot_message]
        
        await telegram_bot._handle_message(update, context)
        
        # Verify message was added to processor
        telegram_bot.message_processor.add_message.assert_called_once()
        call_args = telegram_bot.message_processor.add_message.call_args
        assert call_args[0][0] == 123  # chat_id
        assert isinstance(call_args[0][1], Message)
        
        # Verify response was sent with user mention (since it's a group chat)
        update.message.reply_text.assert_called_once_with("@testuser Hi there!", parse_mode='Markdown')
        
        # Verify typing action was sent
        context.bot.send_chat_action.assert_called_once_with(chat_id=123, action="typing")

    @pytest.mark.asyncio
    async def test_handle_message_private_chat(self, telegram_bot):
        """Test message handling in private chat (no mention)"""
        # Create mock update for private chat
        update = Mock()
        update.message = Mock()
        update.message.text = "Hello bot!"
        update.effective_user = Mock()
        update.effective_user.first_name = "TestUser"
        update.effective_user.username = "testuser"
        update.effective_chat.id = 123
        update.effective_chat.type = 'private'  # Private chat - no mention needed
        update.message.date.timestamp.return_value = 1234567890.0
        update.message.message_id = 456
        update.message.reply_text = AsyncMock()
        
        # Create mock context
        context = Mock()
        context.bot.send_chat_action = AsyncMock()
        
        # Mock message processor
        telegram_bot.message_processor.add_message = AsyncMock()
        telegram_bot.message_processor.contexts = {123: Mock()}
        telegram_bot.message_processor.contexts[123].processing = False
        
        # Mock bot response
        bot_message = Mock()
        bot_message.is_bot = True
        bot_message.content = "Hi there!"
        telegram_bot.message_processor.contexts[123].messages = [bot_message]
        
        await telegram_bot._handle_message(update, context)
        
        # Verify response was sent without user mention (since it's a private chat)
        update.message.reply_text.assert_called_once_with("Hi there!", parse_mode='Markdown')

    @pytest.mark.asyncio
    async def test_handle_message_no_text(self, telegram_bot):
        """Test message handling when message has no text"""
        update = Mock()
        update.message = None
        context = Mock()
        
        telegram_bot.message_processor.add_message = AsyncMock()
        
        await telegram_bot._handle_message(update, context)
        
        telegram_bot.message_processor.add_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_empty_text(self, telegram_bot):
        """Test message handling when message text is empty"""
        update = Mock()
        update.message = Mock()
        update.message.text = None
        context = Mock()
        
        telegram_bot.message_processor.add_message = AsyncMock()
        
        await telegram_bot._handle_message(update, context)
        
        telegram_bot.message_processor.add_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_no_processor(self, telegram_bot):
        """Test message handling when processor is None"""
        update = Mock()
        update.message = Mock()
        update.message.text = "Hello"
        update.effective_user = Mock()
        update.effective_user.first_name = "TestUser"
        update.effective_chat.id = 123
        update.message.date.timestamp.return_value = time.time()
        update.message.message_id = 456
        
        context = Mock()
        
        telegram_bot.message_processor = None
        
        # Should not raise an exception
        await telegram_bot._handle_message(update, context)

    @pytest.mark.asyncio
    async def test_handle_message_user_name_fallback(self, telegram_bot):
        """Test message handling with username fallback in private chat"""
        update = Mock()
        update.message = Mock()
        update.message.text = "Hello"
        update.effective_user = Mock()
        update.effective_user.first_name = None  # No first name
        update.effective_user.username = "testuser"
        update.effective_chat.id = 123
        update.effective_chat.type = 'private'  # Private chat - no mention needed
        update.message.date.timestamp.return_value = time.time()
        update.message.message_id = 456
        update.message.reply_text = AsyncMock()
        update.message.reply_to_message = None
        
        context = Mock()
        context.bot.send_chat_action = AsyncMock()
        context.bot.username = "testbot"
        context.bot.id = 999
        
        telegram_bot.message_processor.add_message = AsyncMock()
        telegram_bot.message_processor.contexts = {123: Mock()}
        telegram_bot.message_processor.contexts[123].processing = False
        telegram_bot.message_processor.contexts[123].messages = []
        
        await telegram_bot._handle_message(update, context)
        
        # Check that username was used
        call_args = telegram_bot.message_processor.add_message.call_args
        message = call_args[0][1]
        assert message.author == "testuser"

    @pytest.mark.asyncio
    async def test_handle_message_unknown_user_fallback(self, telegram_bot):
        """Test message handling with 'Unknown' fallback in private chat"""
        update = Mock()
        update.message = Mock()
        update.message.text = "Hello"
        update.effective_user = Mock()
        update.effective_user.first_name = None
        update.effective_user.username = None
        update.effective_chat.id = 123
        update.effective_chat.type = 'private'  # Private chat - no mention needed
        update.message.date.timestamp.return_value = time.time()
        update.message.message_id = 456
        update.message.reply_text = AsyncMock()
        update.message.reply_to_message = None
        
        context = Mock()
        context.bot.send_chat_action = AsyncMock()
        context.bot.username = "testbot"
        context.bot.id = 999
        
        telegram_bot.message_processor.add_message = AsyncMock()
        telegram_bot.message_processor.contexts = {123: Mock()}
        telegram_bot.message_processor.contexts[123].processing = False
        telegram_bot.message_processor.contexts[123].messages = []
        
        await telegram_bot._handle_message(update, context)
        
        # Check that "Unknown" was used
        call_args = telegram_bot.message_processor.add_message.call_args
        message = call_args[0][1]
        assert message.author == "Unknown"

    @pytest.mark.asyncio
    async def test_handle_message_ignores_non_triggered_messages(self, telegram_bot):
        """Test that bot ignores messages in groups without mention/reply"""
        update = Mock()
        update.message = Mock()
        update.message.text = "Hello everyone!"  # No bot mention
        update.effective_user = Mock()
        update.effective_user.first_name = "TestUser"
        update.effective_user.username = "testuser"
        update.effective_chat.id = 123
        update.effective_chat.type = 'group'  # Group chat
        update.message.date.timestamp.return_value = time.time()
        update.message.message_id = 456
        update.message.reply_text = AsyncMock()
        update.message.reply_to_message = None  # No reply
        
        context = Mock()
        context.bot.send_chat_action = AsyncMock()
        context.bot.username = "testbot"
        context.bot.id = 999
        
        telegram_bot.message_processor.add_message = AsyncMock()
        
        await telegram_bot._handle_message(update, context)
        
        # Verify message was NOT added to processor (bot should ignore it)
        telegram_bot.message_processor.add_message.assert_not_called()
        update.message.reply_text.assert_not_called()
        context.bot.send_chat_action.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_waits_for_processing(self, telegram_bot):
        """Test that message handling waits for processing to complete"""
        update = Mock()
        update.message = Mock()
        update.message.text = "Hello"
        update.effective_user = Mock()
        update.effective_user.first_name = "TestUser"
        update.effective_chat.id = 123
        update.message.date.timestamp.return_value = time.time()
        update.message.message_id = 456
        update.message.reply_text = AsyncMock()
        
        context = Mock()
        context.bot.send_chat_action = AsyncMock()
        
        telegram_bot.message_processor.add_message = AsyncMock()
        telegram_bot.message_processor.contexts = {123: Mock()}
        
        # Simulate processing state
        processing_context = telegram_bot.message_processor.contexts[123]
        processing_context.processing = True
        processing_context.messages = []
        
        # Use a counter to simulate processing completion
        call_count = 0
        async def side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:  # After a few iterations, set processing to False
                processing_context.processing = False
        
        with patch('asyncio.sleep', side_effect=side_effect, new_callable=AsyncMock):
            await telegram_bot._handle_message(update, context)

    @pytest.mark.asyncio
    async def test_start_initializes_application(self, telegram_bot):
        """Test that start method initializes the application"""
        telegram_bot.application.initialize = AsyncMock()
        telegram_bot.application.start = AsyncMock()
        telegram_bot.application.updater.start_polling = AsyncMock()
        telegram_bot.application.updater.running = False  # Mock to prevent infinite loop
        
        await telegram_bot.start()
        
        telegram_bot.application.initialize.assert_called_once()
        telegram_bot.application.start.assert_called_once()
        telegram_bot.application.updater.start_polling.assert_called_once_with(drop_pending_updates=True)

    @pytest.mark.asyncio
    async def test_stop_shuts_down_application(self, telegram_bot):
        """Test that stop method shuts down the application"""
        telegram_bot.application.updater.stop = AsyncMock()
        telegram_bot.application.stop = AsyncMock()
        telegram_bot.application.shutdown = AsyncMock()
        
        await telegram_bot.stop()
        
        telegram_bot.application.updater.stop.assert_called_once()
        telegram_bot.application.stop.assert_called_once()
        telegram_bot.application.shutdown.assert_called_once()

    def test_message_creation_from_telegram_update(self, telegram_bot):
        """Test that Message object is created correctly from Telegram update"""
        # This tests the logic used in _handle_message
        update = Mock()
        update.message.text = "Test message"
        update.effective_user.first_name = "TestUser"
        update.message.date.timestamp.return_value = 1234567890.0
        update.effective_chat.id = 123
        update.message.message_id = 456
        
        # Extract the Message creation logic
        msg = Message(
            content=update.message.text,
            author=update.effective_user.first_name,
            timestamp=update.message.date.timestamp(),
            channel_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
        
        assert msg.content == "Test message"
        assert msg.author == "TestUser"
        assert msg.timestamp == 1234567890.0
        assert msg.channel_id == 123
        assert msg.message_id == 456
        assert msg.is_bot is False

    @pytest.mark.asyncio
    async def test_status_command_no_contexts(self, telegram_bot):
        """Test status command when no contexts exist"""
        telegram_bot.start_time = time.time() - 10  # 10 seconds ago
        telegram_bot.message_processor.contexts = {}
        
        update = Mock()
        update.message.reply_text = AsyncMock()
        context = Mock()
        
        await telegram_bot._status_command(update, context)
        
        call_args = update.message.reply_text.call_args
        status_text = call_args[0][0]
        assert "Active Contexts: `0`" in status_text

    @pytest.mark.asyncio
    async def test_help_command_logging(self, telegram_bot):
        """Test that help command logs debug information"""
        update = Mock()
        update.effective_user.first_name = "TestUser"
        update.effective_chat.id = 123
        update.message.reply_text = AsyncMock()
        
        context = Mock()
        
        with patch('app.telegram.logger') as mock_logger:
            await telegram_bot._help_command(update, context)
            
            mock_logger.debug.assert_called_once()
            debug_msg = mock_logger.debug.call_args[0][0]
            assert "Help command called by TestUser in chat 123" in debug_msg

    @pytest.mark.asyncio
    async def test_handle_message_logging(self, telegram_bot):
        """Test that message handling logs debug information"""
        update = Mock()
        update.message = Mock()
        update.message.text = "Hello bot!"
        update.effective_user = Mock()
        update.effective_user.first_name = "TestUser"
        update.effective_chat.id = 123
        update.message.date.timestamp.return_value = time.time()
        update.message.message_id = 456
        update.message.reply_text = AsyncMock()
        
        context = Mock()
        context.bot.send_chat_action = AsyncMock()
        
        telegram_bot.message_processor.add_message = AsyncMock()
        telegram_bot.message_processor.contexts = {123: Mock()}
        telegram_bot.message_processor.contexts[123].processing = False
        telegram_bot.message_processor.contexts[123].messages = []
        
        with patch('app.telegram.logger') as mock_logger:
            await telegram_bot._handle_message(update, context)
            
            # Should log receiving message and adding to processor
            assert mock_logger.debug.call_count >= 2