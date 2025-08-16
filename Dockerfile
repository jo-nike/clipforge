# ClipForge Dockerfile - Multi-stage build for production
FROM python:3.12-alpine as builder

# Install build dependencies for Alpine
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    cargo \
    rust

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.12-alpine

# Install runtime dependencies for Alpine
RUN apk add --no-cache \
    ffmpeg \
    sqlite \
    dcron \
    sudo \
    bash \
    && rm -rf /var/cache/apk/* /tmp/* /var/tmp/*

# Create non-root user and configure sudo (Alpine syntax)
RUN adduser -D -s /bin/bash clipforge \
    && adduser clipforge wheel \
    && echo '%wheel ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers \
    && chmod 440 /etc/sudoers

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/clipforge/.local

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY cleanup_snapshots.sh ./
COPY start.sh ./
COPY pyproject.toml ./

# Create static directories with proper permissions and setup scripts
RUN mkdir -p static/clips/videos static/clips/snapshots static/clips/thumbnails static/clips/edited static/db \
    && chmod +x cleanup_snapshots.sh start.sh \
    && chown -R clipforge:clipforge /app \
    && chmod -R 755 /app/static

# Switch to non-root user
USER clipforge

# Add local Python packages to PATH
ENV PATH=/home/clipforge/.local/bin:$PATH

# Set Python path to include backend
ENV PYTHONPATH=/app/backend:$PYTHONPATH

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8002/api/health', timeout=5)"

# Run the application with cron
CMD ["./start.sh"]