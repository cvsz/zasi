FROM python:3.11-slim

WORKDIR /app

# Copy repository
COPY . /app

# Install package (no extra pip deps beyond stdlib)
RUN pip install --no-cache-dir -e .

# Create data directory for SQLite persistence
RUN mkdir -p /app/data

EXPOSE 8080

CMD ["python3", "backend/server.py"]
