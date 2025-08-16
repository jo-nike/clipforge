#!/bin/bash

# ClipForge startup script
# Starts cron service and uvicorn application

set -e

# Start cron daemon in background (as root) - Alpine uses crond
sudo crond

# Setup cron job for cleanup script (every 5 minutes) as clipforge user
echo "*/5 * * * * /app/cleanup_snapshots.sh" | crontab -

# Start the application
exec uvicorn backend.main:app --host 0.0.0.0 --port 8002