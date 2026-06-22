# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system dependencies needed for compiling python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Create a virtual environment in /app/.venv
RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy python service dependency files
COPY ./python_service/pyproject.toml ./python_service/
COPY ./python_service/requirements.txt ./python_service/

# Install dependencies using uv
RUN uv pip install --no-cache -r ./python_service/pyproject.toml -r ./python_service/requirements.txt

# Stage 2: Final minimal runtime
FROM python:3.11-slim AS runner

WORKDIR /app

# Install runtime utilities like curl (required for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy python_service source code
COPY ./python_service /app/python_service

# Expose FastAPI default port
EXPOSE 8000

ENV PYTHONPATH=/app
ENV HOST=0.0.0.0
ENV PORT=8000

# Health check to monitor backend status
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/api/health || exit 1

# Run FastAPI using uvicorn from the virtual environment
CMD ["uvicorn", "python_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
