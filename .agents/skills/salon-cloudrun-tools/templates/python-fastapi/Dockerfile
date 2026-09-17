# Dockerfile for Python FastAPI Salon Tool on Google Cloud Run
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create and switch to non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

# Run uvicorn on port $PORT
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1
