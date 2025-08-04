#!/bin/bash
# Script to fix missing telegram_login.py module issue

echo "🔧 Telegram Login Module Fix Script"
echo "=================================="
echo ""
echo "This script fixes the 'ModuleNotFoundError: No module named 'telegram_login'" error"
echo ""

# Check if the file exists
if [ ! -f "telegram_login.py" ]; then
    echo "❌ ERROR: telegram_login.py not found in current directory!"
    echo "    Please make sure you're in the project root directory."
    exit 1
fi

# Check if Docker is running
if ! docker ps >/dev/null 2>&1; then
    echo "❌ ERROR: Docker doesn't appear to be running!"
    echo "    Please start Docker and try again."
    exit 1
fi

# Get the container ID
CONTAINER_ID=$(docker ps | grep telegram-calendar-sync | awk '{print $1}')
if [ -z "$CONTAINER_ID" ]; then
    echo "❌ ERROR: Could not find running telegram-calendar-sync container!"
    echo "    Make sure the container is running."
    exit 1
fi

echo "✅ Found container: $CONTAINER_ID"
echo ""
echo "📋 Copying telegram_login.py to container..."

# Copy the file to the container
docker cp telegram_login.py $CONTAINER_ID:/app/telegram_login.py

# Fix permissions
docker exec $CONTAINER_ID chown app:app /app/telegram_login.py

echo "✅ File copied successfully!"
echo ""
echo "🔄 Restarting the container..."

# Restart the container
docker restart $CONTAINER_ID

echo "✅ Container restarted!"
echo ""
echo "📊 Checking logs for errors..."
sleep 2

# Check logs for errors
docker logs $CONTAINER_ID --tail 10

echo ""
echo "✅ Fix applied successfully!"
echo "   If you still see errors, you may need to rebuild the container:"
echo "   docker-compose build --no-cache telegram-calendar-sync"
echo "   docker-compose up -d"
