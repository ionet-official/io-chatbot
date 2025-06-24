# Use Python 3.10 slim image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY io_chat_bot.py .

# Set environment variable
ENV PYTHONUNBUFFERED=1

# Run the bot
CMD ["python", "io_chat_bot.py"]