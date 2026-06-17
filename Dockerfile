# Use Python 3.10 slim image for a smaller footprint
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY ./python_service ./python_service
COPY ./test_proxy.py .
COPY ./restart_services.sh .

# Set environment variables
ENV PYTHONPATH=/app
ENV HOST=0.0.0.0
ENV PORT=8000

# Expose port
EXPOSE 8000

# Run FastAPI backend
CMD ["uvicorn", "python_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
