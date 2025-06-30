import os
import pytest
from unittest.mock import patch


class TestConfigSimple:
    """Simplified config tests that work reliably"""

    def test_config_import_works(self):
        """Test that config module can be imported"""
        import app.config
        assert hasattr(app.config, 'API_KEY')
        assert hasattr(app.config, 'DISCORD_TOKEN')
        assert hasattr(app.config, 'TELEGRAM_TOKEN')

    def test_config_has_required_constants(self):
        """Test that config has all required constants"""
        import app.config
        
        # Check that all required constants exist
        required_attrs = [
            'API_BASE_URL', 'MODEL_NAME', 'MAX_CONTEXT_MESSAGES',
            'MESSAGE_BATCH_SIZE', 'PROCESSING_TIMEOUT', 'RATE_LIMIT_DELAY',
            'MAX_RESPONSE_LENGTH', 'CONTEXT_CLEANUP_INTERVAL', 'SYSTEM_PROMPT'
        ]
        
        for attr in required_attrs:
            assert hasattr(app.config, attr), f"Missing {attr}"

    def test_config_numeric_types(self):
        """Test that numeric config values have correct types"""
        import app.config
        
        assert isinstance(app.config.MAX_CONTEXT_MESSAGES, int)
        assert isinstance(app.config.MESSAGE_BATCH_SIZE, int)
        assert isinstance(app.config.PROCESSING_TIMEOUT, float)
        assert isinstance(app.config.RATE_LIMIT_DELAY, float)
        assert isinstance(app.config.MAX_RESPONSE_LENGTH, int)
        assert isinstance(app.config.CONTEXT_CLEANUP_INTERVAL, int)

    def test_config_default_values(self):
        """Test that config has reasonable default values"""
        import app.config
        
        assert app.config.MAX_CONTEXT_MESSAGES > 0
        assert app.config.MESSAGE_BATCH_SIZE > 0
        assert app.config.PROCESSING_TIMEOUT > 0
        assert app.config.RATE_LIMIT_DELAY >= 0
        assert app.config.MAX_RESPONSE_LENGTH > 0
        assert app.config.CONTEXT_CLEANUP_INTERVAL > 0

    def test_system_prompt_default_and_custom(self):
        """Test that system prompt can be customized via environment variable"""
        import app.config
        
        # Test that SYSTEM_PROMPT exists and is a string
        assert hasattr(app.config, 'SYSTEM_PROMPT')
        assert isinstance(app.config.SYSTEM_PROMPT, str)
        assert len(app.config.SYSTEM_PROMPT) > 0
        
        # Test that DEFAULT_SYSTEM_PROMPT exists
        assert hasattr(app.config, 'DEFAULT_SYSTEM_PROMPT')
        assert isinstance(app.config.DEFAULT_SYSTEM_PROMPT, str)
        
        # Test custom system prompt via environment variable
        with patch.dict(os.environ, {'SYSTEM_PROMPT': 'Custom test prompt'}):
            # Re-import to get the updated environment variable
            import importlib
            import app.config
            importlib.reload(app.config)
            
            assert app.config.SYSTEM_PROMPT == 'Custom test prompt'
            
            # Clean up by reloading without the custom env var
            importlib.reload(app.config)

