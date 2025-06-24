"""
Pytest configuration and shared fixtures.
"""
import asyncio
import os
import pytest
from unittest.mock import patch


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def env_setup():
    """Set up clean environment for each test."""
    # Mock environment variables to avoid loading real config
    env_vars = {
        'API_KEY': 'test_api_key',
        'DISCORD_TOKEN': 'test_discord_token',
        'TELEGRAM_TOKEN': 'test_telegram_token',
        'API_BASE_URL': 'https://test.api.url',
        'MODEL_NAME': 'test-model',
        'MAX_CONTEXT_MESSAGES': '10',
        'MESSAGE_BATCH_SIZE': '2',
        'PROCESSING_TIMEOUT': '5.0',
        'RATE_LIMIT_DELAY': '0.1',
        'MAX_RESPONSE_LENGTH': '100',
        'CONTEXT_CLEANUP_INTERVAL': '60',
        'LOG_LEVEL': 'DEBUG'
    }
    
    with patch.dict(os.environ, env_vars, clear=True):
        yield


@pytest.fixture
def mock_time():
    """Mock time.time() to return a consistent value."""
    with patch('time.time', return_value=1234567890.0):
        yield 1234567890.0


@pytest.fixture
def sample_messages():
    """Provide sample messages for testing."""
    from app.models import Message
    import time
    
    return [
        Message("Hello", "User1", time.time(), 123, 1),
        Message("Hi there!", "Bot", time.time(), 123, 2, is_bot=True),
        Message("How are you?", "User2", time.time(), 123, 3),
    ]


@pytest.fixture
def mock_aiohttp_session():
    """Mock aiohttp ClientSession for HTTP tests."""
    from unittest.mock import AsyncMock, Mock
    
    session = Mock()
    session.post = AsyncMock()
    session.close = AsyncMock()
    session.closed = False
    
    return session