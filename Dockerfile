FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY src/ ./src/
COPY public/ ./public/

# Expose port
EXPOSE 8000

# Start server
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
