import time
from dataclasses import dataclass, field
from typing import Dict, List
from collections import deque

from .config import MAX_CONTEXT_MESSAGES


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