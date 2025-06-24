FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY app/ ./app/

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]