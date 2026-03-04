# Multi-stage build for optimized image size
FROM python:3.12-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies (incl. test deps for running tests in builder)
COPY requirements.txt requirements-dev.txt /build/
RUN pip install --no-cache-dir --user -r requirements-dev.txt

# Copy app and tests, run integration tests (build fails if tests fail)
COPY ./app ./app
COPY ./tests ./tests
ENV PYTHONPATH=/build
RUN python -m pytest tests/ -v

# Test stage: run tests in Docker (e.g. docker build --target test -t backend-test . && docker run --rm backend-test)
FROM python:3.12-slim AS test
WORKDIR /app
COPY requirements.txt requirements-dev.txt /app/
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY ./app ./app
COPY ./tests ./tests
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "pytest", "tests/integration/test_analyze_stock_llm.py", "-v"]

# Final stage
FROM python:3.12-slim

WORKDIR /app

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY ./app ./app

# Create logs directory and set proper permissions
RUN mkdir -p /app/app/logs && \
    chown -R appuser:appuser /app /home/appuser/.local

# Set PATH to include user's local bin
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Expose port (Cloud Run uses PORT environment variable)
EXPOSE 8080

# Health check (Cloud Run handles health checks at platform level, but this is useful for local dev)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Start the application
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
