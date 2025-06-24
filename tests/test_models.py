import time
import pytest
from unittest.mock import patch
from collections import deque

from app.models import Message, ConversationContext


class TestMessage:
    """Test cases for Message dataclass"""

    def test_message_creation(self):
        """Test basic message creation with required fields"""
        message = Message(
            content="Hello world",
            author="TestUser",
            timestamp=1234567890.0,
            channel_id=12345,
            message_id=67890
        )
        
        assert message.content == "Hello world"
        assert message.author == "TestUser"
        assert message.timestamp == 1234567890.0
        assert message.channel_id == 12345
        assert message.message_id == 67890
        assert message.is_bot is False  # Default value

    def test_message_creation_with_bot_flag(self):
        """Test message creation with is_bot flag set"""
        message = Message(
            content="Bot response",
            author="BotUser",
            timestamp=1234567890.0,
            channel_id=12345,
            message_id=67890,
            is_bot=True
        )
        
        assert message.is_bot is True

    def test_message_equality(self):
        """Test message equality comparison"""
        message1 = Message("Hello", "User", 123.0, 1, 2)
        message2 = Message("Hello", "User", 123.0, 1, 2)
        message3 = Message("Hello", "User", 123.0, 1, 3)  # Different message_id
        
        assert message1 == message2
        assert message1 != message3


class TestConversationContext:
    """Test cases for ConversationContext class"""

    def test_context_creation(self):
        """Test basic context creation with defaults"""
        context = ConversationContext()
        
        assert isinstance(context.messages, deque)
        assert len(context.messages) == 0
        assert context.processing is False
        assert isinstance(context.last_activity, float)

    def test_add_message_updates_activity(self):
        """Test that adding a message updates last_activity timestamp"""
        context = ConversationContext()
        initial_time = context.last_activity
        
        # Sleep to ensure time difference
        time.sleep(0.01)
        
        message = Message("Test", "User", time.time(), 1, 1)
        context.add_message(message)
        
        assert context.last_activity > initial_time
        assert len(context.messages) == 1
        assert context.messages[0] == message

    def test_add_multiple_messages(self):
        """Test adding multiple messages to context"""
        context = ConversationContext()
        
        messages = [
            Message("Message 1", "User1", time.time(), 1, 1),
            Message("Message 2", "User2", time.time(), 1, 2),
            Message("Message 3", "Bot", time.time(), 1, 3, is_bot=True)
        ]
        
        for msg in messages:
            context.add_message(msg)
        
        assert len(context.messages) == 3
        assert list(context.messages) == messages

    @patch('app.models.MAX_CONTEXT_MESSAGES', 2)
    def test_message_deque_max_length(self):
        """Test that message deque respects max length"""
        # Need to recreate context after patching MAX_CONTEXT_MESSAGES
        with patch('app.models.MAX_CONTEXT_MESSAGES', 2):
            # Import after patching to get the new value
            from app.models import ConversationContext as TestContext
            context = TestContext()
            
            # Add more messages than max length
            for i in range(5):
                message = Message(f"Message {i}", "User", time.time(), 1, i)
                context.add_message(message)
            
            # Should only keep the last 2 messages
            assert len(context.messages) == 2
            assert context.messages[0].content == "Message 3"
            assert context.messages[1].content == "Message 4"

    def test_get_context_messages_user_format(self):
        """Test context message formatting for user messages"""
        context = ConversationContext()
        
        user_message = Message("Hello", "TestUser", time.time(), 1, 1)
        context.add_message(user_message)
        
        formatted = context.get_context_messages()
        
        assert len(formatted) == 1
        assert formatted[0]["role"] == "user"
        assert formatted[0]["content"] == "TestUser: Hello"

    def test_get_context_messages_bot_format(self):
        """Test context message formatting for bot messages"""
        context = ConversationContext()
        
        bot_message = Message("Hi there!", "Bot", time.time(), 1, 1, is_bot=True)
        context.add_message(bot_message)
        
        formatted = context.get_context_messages()
        
        assert len(formatted) == 1
        assert formatted[0]["role"] == "assistant"
        assert formatted[0]["content"] == "Hi there!"  # No author prefix for bot

    def test_get_context_messages_mixed(self):
        """Test context message formatting with mixed user and bot messages"""
        context = ConversationContext()
        
        messages = [
            Message("Hello", "User1", time.time(), 1, 1),
            Message("Hi there!", "Bot", time.time(), 1, 2, is_bot=True),
            Message("How are you?", "User2", time.time(), 1, 3)
        ]
        
        for msg in messages:
            context.add_message(msg)
        
        formatted = context.get_context_messages()
        
        assert len(formatted) == 3
        assert formatted[0]["role"] == "user"
        assert formatted[0]["content"] == "User1: Hello"
        assert formatted[1]["role"] == "assistant"
        assert formatted[1]["content"] == "Hi there!"
        assert formatted[2]["role"] == "user"
        assert formatted[2]["content"] == "User2: How are you?"

    def test_is_stale_fresh_context(self):
        """Test that fresh context is not stale"""
        context = ConversationContext()
        
        assert not context.is_stale(max_age=10.0)

    def test_is_stale_old_context(self):
        """Test that old context is stale"""
        context = ConversationContext()
        
        # Mock old timestamp
        old_time = time.time() - 3600  # 1 hour ago
        context.last_activity = old_time
        
        assert context.is_stale(max_age=1800)  # 30 minutes

    def test_is_stale_custom_max_age(self):
        """Test is_stale with custom max_age parameter"""
        context = ConversationContext()
        
        # Set activity to 5 seconds ago
        context.last_activity = time.time() - 5
        
        assert not context.is_stale(max_age=10)  # Not stale with 10s max age
        assert context.is_stale(max_age=3)       # Stale with 3s max age

    def test_processing_flag(self):
        """Test processing flag manipulation"""
        context = ConversationContext()
        
        assert context.processing is False
        
        context.processing = True
        assert context.processing is True
        
        context.processing = False
        assert context.processing is False

    @patch('time.time')
    def test_add_message_timestamp_mocked(self, mock_time):
        """Test add_message with mocked time for precise control"""
        mock_time.return_value = 1234567890.0
        
        context = ConversationContext()
        message = Message("Test", "User", 999.0, 1, 1)  # Different timestamp
        
        context.add_message(message)
        
        # Should update to mocked time
        assert context.last_activity == 1234567890.0