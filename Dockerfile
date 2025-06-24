FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY io_chat_bot.py .

ENV PYTHONUNBUFFERED=1

CMD ["python", "io_chat_bot.py"]