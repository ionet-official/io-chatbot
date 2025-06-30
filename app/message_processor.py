import asyncio
import logging
import time
from typing import Dict, Optional
from collections import defaultdict

from .models import Message, ConversationContext
from .llm_client import LLMClient
from .config import (
    MESSAGE_BATCH_SIZE, PROCESSING_TIMEOUT, RATE_LIMIT_DELAY, 
    MAX_RESPONSE_LENGTH, SYSTEM_PROMPT
)

logger = logging.getLogger(__name__)


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

            # Add system prompt with formatting instructions
            formatting_instructions = ("\n\nIMPORTANT: Use only basic markdown formatting that works across platforms: "
                                     "- Use *bold* for emphasis (single asterisks work on both platforms) "
                                     "- Use `code` for inline code or technical terms "
                                     "- Use bullet points with - or • for lists "
                                     "- Use [text](url) for links "
                                     "- Avoid complex formatting, special characters, or platform-specific syntax")
            
            system_prompt = {
                "role": "system",
                "content": SYSTEM_PROMPT + formatting_instructions
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