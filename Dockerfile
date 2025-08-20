FROM python:3.11-slim

WORKDIR /app

# Install curl for health check
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Create directory for database (rarely changes, cache this layer)
RUN mkdir -p /app/data

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files (changes most frequently, do this last)
COPY . .

# Environment variables - these will be overridden by Railway
ENV DATABASE_PATH=/app/data/hashrate.db
ENV PYTHONUNBUFFERED=1

# Note: Bigtable configuration should be set via Railway environment variables:
# USE_BIGTABLE=true
# BIGTABLE_PROJECT_ID=adept-storm-466618-b4
# BIGTABLE_INSTANCE_ID=hash-generator-instance
# BIGTABLE_TABLE_ID=hashes
# GOOGLE_APPLICATION_CREDENTIALS_JSON={paste entire JSON content}
#
# Firehose monitoring configuration (optional):
# ENABLE_FIREHOSE_MONITOR=true
# This enables the enhanced dashboard with Bigtable ingestion monitoring

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run the application - Railway needs sh -c for environment variable expansion
# Using threads worker to support WebSocket while avoiding eventlet issues
CMD ["sh", "-c", "gunicorn --worker-class gthread --workers 1 --threads 4 --bind 0.0.0.0:$PORT --timeout 120 --graceful-timeout 30 --log-level info app:app"]