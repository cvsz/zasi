FROM python:3.11-slim

WORKDIR /app

# Copy repository
COPY . /app

# Install package in editable mode
RUN pip install --no-cache-dir -e .

EXPOSE 8080

ENTRYPOINT ["python3", "main.py"]
