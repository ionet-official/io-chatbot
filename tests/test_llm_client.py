import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
from aioresponses import aioresponses
import aiohttp

from app.llm_client import LLMClient


class TestLLMClient:
    """Test cases for LLMClient class"""

    def test_init(self):
        """Test LLMClient initialization"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        assert client.base_url == "https://api.example.com"
        assert client.api_key == "test_key"
        assert client.model == "test_model"
        assert client.session is None

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from base_url"""
        client = LLMClient("https://api.example.com/", "test_key", "test_model")
        assert client.base_url == "https://api.example.com"

    @pytest.mark.asyncio
    async def test_context_manager_enter(self):
        """Test async context manager __aenter__"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        async with client as entered_client:
            assert entered_client is client
            assert client.session is not None
            assert isinstance(client.session, aiohttp.ClientSession)
            
            # Check headers are set correctly
            assert client.session.headers["Authorization"] == "Bearer test_key"
            assert client.session.headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_context_manager_exit(self):
        """Test async context manager __aexit__"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        async with client:
            session = client.session
            assert session is not None
        
        # Session should be closed after exit
        assert session.closed

    @pytest.mark.asyncio
    async def test_generate_response_success(self):
        """Test successful response generation"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        mock_response = {
            "choices": [{
                "message": {
                    "content": "  This is a test response.  "
                }
            }]
        }
        
        with aioresponses() as m:
            m.post(
                "https://api.example.com/chat/completions",
                payload=mock_response,
                status=200
            )
            
            async with client:
                messages = [{"role": "user", "content": "Hello"}]
                response = await client.generate_response(messages)
                
                assert response == "This is a test response."  # Should be stripped

    @pytest.mark.asyncio
    async def test_generate_response_with_custom_params(self):
        """Test response generation with custom parameters"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        mock_response = {
            "choices": [{
                "message": {
                    "content": "Custom response"
                }
            }]
        }
        
        with aioresponses() as m:
            m.post(
                "https://api.example.com/chat/completions",
                payload=mock_response,
                status=200
            )
            
            async with client:
                messages = [{"role": "user", "content": "Hello"}]
                response = await client.generate_response(
                    messages, 
                    max_tokens=1000, 
                    temperature=0.9
                )
                
                assert response == "Custom response"
                
                # Check that request was made with correct parameters
                assert len(m.requests) == 1

    @pytest.mark.asyncio
    async def test_generate_response_http_error(self):
        """Test response generation with HTTP error"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        with aioresponses() as m:
            m.post(
                "https://api.example.com/chat/completions",
                status=400,
                payload={"error": "Bad request"}
            )
            
            async with client:
                messages = [{"role": "user", "content": "Hello"}]
                response = await client.generate_response(messages)
                
                assert response is None

    @pytest.mark.asyncio
    async def test_generate_response_500_error(self):
        """Test response generation with server error"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        with aioresponses() as m:
            m.post(
                "https://api.example.com/chat/completions",
                status=500,
                body="Internal server error"
            )
            
            async with client:
                messages = [{"role": "user", "content": "Hello"}]
                response = await client.generate_response(messages)
                
                assert response is None

    @pytest.mark.asyncio
    async def test_generate_response_timeout(self):
        """Test response generation with timeout"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        with aioresponses() as m:
            m.post(
                "https://api.example.com/chat/completions",
                exception=asyncio.TimeoutError()
            )
            
            async with client:
                messages = [{"role": "user", "content": "Hello"}]
                response = await client.generate_response(messages)
                
                assert response is None

    @pytest.mark.asyncio
    async def test_generate_response_network_error(self):
        """Test response generation with network error"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        with aioresponses() as m:
            m.post(
                "https://api.example.com/chat/completions",
                exception=aiohttp.ClientError("Network error")
            )
            
            async with client:
                messages = [{"role": "user", "content": "Hello"}]
                response = await client.generate_response(messages)
                
                assert response is None

    @pytest.mark.asyncio
    async def test_generate_response_without_session(self):
        """Test that calling generate_response without session raises RuntimeError"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        messages = [{"role": "user", "content": "Hello"}]
        
        with pytest.raises(RuntimeError, match="LLMClient not initialized"):
            await client.generate_response(messages)

    @pytest.mark.asyncio
    async def test_generate_response_logs_debug_info(self):
        """Test that debug information is logged during request"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        mock_response = {
            "choices": [{
                "message": {
                    "content": "Test response"
                }
            }]
        }
        
        with aioresponses() as m:
            m.post(
                "https://api.example.com/chat/completions",
                payload=mock_response,
                status=200
            )
            
            with patch('app.llm_client.logger') as mock_logger:
                async with client:
                    messages = [{"role": "user", "content": "Hello"}]
                    await client.generate_response(messages)
                    
                    # Verify debug logs were called
                    assert mock_logger.debug.call_count >= 3
                    
                    # Check specific log messages
                    debug_calls = [call.args[0] for call in mock_logger.debug.call_args_list]
                    assert any("Sending request to LLM API" in msg for msg in debug_calls)
                    assert any("Payload:" in msg for msg in debug_calls)
                    assert any("LLM API response status" in msg for msg in debug_calls)

    @pytest.mark.asyncio
    async def test_generate_response_logs_error_info(self):
        """Test that error information is logged during failed request"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        with aioresponses() as m:
            m.post(
                "https://api.example.com/chat/completions",
                status=400,
                body="Bad request error"
            )
            
            with patch('app.llm_client.logger') as mock_logger:
                async with client:
                    messages = [{"role": "user", "content": "Hello"}]
                    await client.generate_response(messages)
                    
                    # Verify error log was called
                    mock_logger.error.assert_called()
                    error_msg = mock_logger.error.call_args[0][0]
                    assert "LLM API error 400" in error_msg

    @pytest.mark.asyncio
    async def test_generate_response_empty_content(self):
        """Test response generation with empty content"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        mock_response = {
            "choices": [{
                "message": {
                    "content": "   "  # Only whitespace
                }
            }]
        }
        
        with aioresponses() as m:
            m.post(
                "https://api.example.com/chat/completions",
                payload=mock_response,
                status=200
            )
            
            async with client:
                messages = [{"role": "user", "content": "Hello"}]
                response = await client.generate_response(messages)
                
                assert response == ""  # Should be empty after strip

    @pytest.mark.asyncio
    async def test_multiple_requests_same_session(self):
        """Test multiple requests using the same session"""
        client = LLMClient("https://api.example.com", "test_key", "test_model")
        
        mock_response = {
            "choices": [{
                "message": {
                    "content": "Response"
                }
            }]
        }
        
        with aioresponses() as m:
            # Add multiple responses
            m.post(
                "https://api.example.com/chat/completions",
                payload=mock_response,
                status=200,
                repeat=True  # Allow multiple calls to the same URL
            )
            
            async with client:
                messages = [{"role": "user", "content": "Hello"}]
                
                # Make multiple requests
                responses = []
                for i in range(3):
                    response = await client.generate_response(messages)
                    responses.append(response)
                
                # All responses should be successful
                assert all(r == "Response" for r in responses)