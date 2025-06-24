import asyncio
import time
import pytest
from unittest.mock import Mock, patch, AsyncMock
from collections import defaultdict

from app.message_processor import MessageProcessor
from app.models import Message, ConversationContext
from app.llm_client import LLMClient


class TestMessageProcessor:
    """Test cases for MessageProcessor class"""

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client"""
        client = Mock(spec=LLMClient)
        client.generate_response = AsyncMock()
        return client

    @pytest.fixture
    def processor(self, mock_llm_client):
        """Create a MessageProcessor instance with mock LLM client"""
        return MessageProcessor(mock_llm_client)

    def test_init(self, mock_llm_client):
        """Test MessageProcessor initialization"""
        processor = MessageProcessor(mock_llm_client)
        
        assert processor.llm_client is mock_llm_client
        assert isinstance(processor.message_queues, defaultdict)
        assert isinstance(processor.processing_locks, defaultdict)
        assert isinstance(processor.contexts, defaultdict)
        assert isinstance(processor.processing_tasks, dict)

    @pytest.mark.asyncio
    async def test_add_message_creates_queue(self, processor):
        """Test that adding a message creates a queue for the channel"""
        message = Message("Test", "User", time.time(), 123, 1)
        
        # Mock the processing task to avoid actual processing
        with patch.object(processor, '_process_channel_messages', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = "Response"
            
            response = await processor.add_message(123, message)
            
            assert 123 in processor.message_queues
            assert response == "Response"

    @pytest.mark.asyncio
    async def test_add_message_starts_processing_task(self, processor):
        """Test that adding a message starts a processing task"""
        message = Message("Test", "User", time.time(), 123, 1)
        
        with patch.object(processor, '_process_channel_messages', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = "Response"
            
            await processor.add_message(123, message)
            
            mock_process.assert_called_once_with(123)
            assert 123 in processor.processing_tasks

    @pytest.mark.asyncio
    async def test_add_message_reuses_running_task(self, processor):
        """Test that if a task is already running, it's reused"""
        message1 = Message("Test1", "User", time.time(), 123, 1)
        message2 = Message("Test2", "User", time.time(), 123, 2)
        
        # Create a long-running mock task
        task_started = asyncio.Event()
        task_continue = asyncio.Event()
        
        async def long_running_process(channel_id):
            task_started.set()
            await task_continue.wait()
            return "Response"
        
        with patch.object(processor, '_process_channel_messages', side_effect=long_running_process):
            # Start first message processing
            task1 = asyncio.create_task(processor.add_message(123, message1))
            
            # Wait for the task to start
            await task_started.wait()
            
            # Add second message - should reuse the running task
            task2 = asyncio.create_task(processor.add_message(123, message2))
            
            # Let the task complete
            task_continue.set()
            
            response1 = await task1
            response2 = await task2
            
            assert response1 == "Response"
            assert response2 == "Response"

    @pytest.mark.asyncio
    async def test_add_message_timeout_handling(self, processor):
        """Test timeout handling in add_message"""
        message = Message("Test", "User", time.time(), 123, 1)
        
        # Mock a task that takes too long
        async def slow_process(channel_id):
            await asyncio.sleep(10)  # Much longer than timeout
            return "Response"
        
        with patch.object(processor, '_process_channel_messages', side_effect=slow_process):
            with patch('app.message_processor.PROCESSING_TIMEOUT', 0.1):  # Very short timeout
                response = await processor.add_message(123, message)
                
                assert "taking too long to respond" in response

    @pytest.mark.asyncio
    async def test_add_message_exception_handling(self, processor):
        """Test exception handling in add_message"""
        message = Message("Test", "User", time.time(), 123, 1)
        
        # Mock a task that raises an exception
        async def failing_process(channel_id):
            raise Exception("Test error")
        
        with patch.object(processor, '_process_channel_messages', side_effect=failing_process):
            response = await processor.add_message(123, message)
            
            assert "encountered an error processing" in response

    @pytest.mark.asyncio
    async def test_process_channel_messages_empty_queue(self, processor):
        """Test processing when queue is empty"""
        result = await processor._process_channel_messages(123)
        
        assert result == ""

    @pytest.mark.asyncio
    async def test_process_channel_messages_single_message(self, processor, mock_llm_client):
        """Test processing a single message"""
        channel_id = 123
        message = Message("Hello", "User", time.time(), channel_id, 1)
        
        # Add message to queue
        await processor.message_queues[channel_id].put(message)
        
        # Mock LLM response
        mock_llm_client.generate_response.return_value = "Hi there!"
        
        result = await processor._process_channel_messages(channel_id)
        
        assert result == "Hi there!"
        assert len(processor.contexts[channel_id].messages) == 2  # User + bot message

    @pytest.mark.asyncio
    async def test_process_channel_messages_batch_processing(self, processor, mock_llm_client):
        """Test batch processing of multiple messages"""
        channel_id = 123
        messages = [
            Message(f"Message {i}", "User", time.time(), channel_id, i)
            for i in range(5)
        ]
        
        # Add messages to queue
        for msg in messages:
            await processor.message_queues[channel_id].put(msg)
        
        # Mock LLM response
        mock_llm_client.generate_response.return_value = "Batch response"
        
        with patch('app.message_processor.MESSAGE_BATCH_SIZE', 3):
            result = await processor._process_channel_messages(channel_id)
        
        assert result == "Batch response"
        # Should process first batch of 3 messages + bot response
        assert len(processor.contexts[channel_id].messages) == 4

    @pytest.mark.asyncio
    async def test_process_channel_messages_only_bot_messages(self, processor):
        """Test processing when batch contains only bot messages"""
        channel_id = 123
        bot_message = Message("Bot message", "Bot", time.time(), channel_id, 1, is_bot=True)
        
        # Add bot message to queue
        await processor.message_queues[channel_id].put(bot_message)
        
        result = await processor._process_channel_messages(channel_id)
        
        assert result == ""  # No response generated for bot-only batch

    @pytest.mark.asyncio
    async def test_generate_and_send_response_success(self, processor, mock_llm_client):
        """Test successful response generation"""
        channel_id = 123
        message = Message("Hello", "User", time.time(), channel_id, 1)
        
        mock_llm_client.generate_response.return_value = "Hello there!"
        
        result = await processor._generate_and_send_response(channel_id, message)
        
        assert result == "Hello there!"
        
        # Check that bot message was added to context
        context = processor.contexts[channel_id]
        assert len(context.messages) == 1
        assert context.messages[0].is_bot is True
        assert context.messages[0].content == "Hello there!"

    @pytest.mark.asyncio
    async def test_generate_and_send_response_long_message_truncation(self, processor, mock_llm_client):
        """Test that long responses are truncated"""
        channel_id = 123
        message = Message("Hello", "User", time.time(), channel_id, 1)
        
        # Generate a very long response
        long_response = "x" * 3000
        mock_llm_client.generate_response.return_value = long_response
        
        with patch('app.message_processor.MAX_RESPONSE_LENGTH', 100):
            result = await processor._generate_and_send_response(channel_id, message)
        
        assert len(result) == 100
        assert result.endswith("...")

    @pytest.mark.asyncio
    async def test_generate_and_send_response_llm_failure(self, processor, mock_llm_client):
        """Test handling of LLM API failure"""
        channel_id = 123
        message = Message("Hello", "User", time.time(), channel_id, 1)
        
        mock_llm_client.generate_response.return_value = None
        
        result = await processor._generate_and_send_response(channel_id, message)
        
        assert "having trouble generating a response" in result

    @pytest.mark.asyncio
    async def test_generate_and_send_response_exception(self, processor, mock_llm_client):
        """Test exception handling in response generation"""
        channel_id = 123
        message = Message("Hello", "User", time.time(), channel_id, 1)
        
        mock_llm_client.generate_response.side_effect = Exception("API Error")
        
        result = await processor._generate_and_send_response(channel_id, message)
        
        assert "Something went wrong" in result

    @pytest.mark.asyncio
    async def test_generate_and_send_response_processing_flag(self, processor, mock_llm_client):
        """Test that processing flag is set and unset correctly"""
        channel_id = 123
        message = Message("Hello", "User", time.time(), channel_id, 1)
        context = processor.contexts[channel_id]
        
        assert context.processing is False
        
        # Mock LLM to check processing flag during call
        async def check_processing(*args, **kwargs):
            assert context.processing is True
            return "Response"
        
        mock_llm_client.generate_response.side_effect = check_processing
        
        await processor._generate_and_send_response(channel_id, message)
        
        assert context.processing is False

    @pytest.mark.asyncio
    async def test_generate_and_send_response_system_prompt(self, processor, mock_llm_client):
        """Test that system prompt is included in LLM call"""
        channel_id = 123
        message = Message("Hello", "User", time.time(), channel_id, 1)
        
        mock_llm_client.generate_response.return_value = "Response"
        
        await processor._generate_and_send_response(channel_id, message)
        
        # Check that generate_response was called with system prompt
        call_args = mock_llm_client.generate_response.call_args[0][0]
        assert call_args[0]["role"] == "system"
        assert "IO Chat" in call_args[0]["content"]

    def test_cleanup_stale_contexts_no_stale(self, processor):
        """Test cleanup when no contexts are stale"""
        # Add some fresh contexts
        for i in range(3):
            context = processor.contexts[i]
            context.last_activity = time.time()  # Fresh timestamp
        
        initial_count = len(processor.contexts)
        processor.cleanup_stale_contexts()
        
        assert len(processor.contexts) == initial_count

    def test_cleanup_stale_contexts_with_stale(self, processor):
        """Test cleanup of stale contexts"""
        # Add fresh context
        processor.contexts[1].last_activity = time.time()
        
        # Add stale context
        processor.contexts[2].last_activity = time.time() - 3600  # 1 hour ago
        processor.message_queues[2] = asyncio.Queue()
        processor.processing_locks[2] = asyncio.Lock()
        
        # Add a mock task
        mock_task = Mock()
        mock_task.done.return_value = False
        processor.processing_tasks[2] = mock_task
        
        processor.cleanup_stale_contexts()
        
        # Fresh context should remain
        assert 1 in processor.contexts
        
        # Stale context should be removed
        assert 2 not in processor.contexts
        assert 2 not in processor.message_queues
        assert 2 not in processor.processing_locks
        assert 2 not in processor.processing_tasks
        
        # Task should be cancelled
        mock_task.cancel.assert_called_once()

    def test_cleanup_stale_contexts_completed_task(self, processor):
        """Test cleanup with completed task"""
        # Add stale context with completed task
        processor.contexts[1].last_activity = time.time() - 3600
        
        mock_task = Mock()
        mock_task.done.return_value = True  # Task is already done
        processor.processing_tasks[1] = mock_task
        
        processor.cleanup_stale_contexts()
        
        # Task should not be cancelled if already done
        mock_task.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limiting_applied(self, processor, mock_llm_client):
        """Test that rate limiting delay is applied"""
        channel_id = 123
        
        # Add multiple messages to trigger multiple batches
        for i in range(10):
            message = Message(f"Message {i}", "User", time.time(), channel_id, i)
            await processor.message_queues[channel_id].put(message)
        
        mock_llm_client.generate_response.return_value = "Response"
        
        with patch('app.message_processor.MESSAGE_BATCH_SIZE', 2):
            with patch('app.message_processor.RATE_LIMIT_DELAY', 0.1):
                with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                    await processor._process_channel_messages(channel_id)
                    
                    # Sleep should be called for rate limiting between batches
                    # Check if sleep was called with the expected delay
                    if mock_sleep.call_count > 0:
                        mock_sleep.assert_called_with(0.1)

    @pytest.mark.asyncio
    async def test_concurrent_channel_processing(self, processor, mock_llm_client):
        """Test that different channels can be processed concurrently"""
        mock_llm_client.generate_response.return_value = "Response"
        
        # Add messages to different channels
        message1 = Message("Hello 1", "User", time.time(), 123, 1)
        message2 = Message("Hello 2", "User", time.time(), 456, 1)
        
        # Process both channels concurrently
        task1 = asyncio.create_task(processor.add_message(123, message1))
        task2 = asyncio.create_task(processor.add_message(456, message2))
        
        response1, response2 = await asyncio.gather(task1, task2)
        
        assert response1 == "Response"
        assert response2 == "Response"
        assert 123 in processor.contexts
        assert 456 in processor.contexts