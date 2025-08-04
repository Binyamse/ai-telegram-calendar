#!/bin/bash
# Script to test Telegram API functionality

# Set to exit on error
set -e

# Check if bot token is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <TELEGRAM_BOT_TOKEN> <USERNAME> [USER_ID]"
    echo "Example: $0 YOUR_BOT_TOKEN_HERE binyams"
    echo "Example with user ID: $0 YOUR_BOT_TOKEN_HERE '' 123456789"
    echo ""
    echo "Your bot: @fiscalendar_bot (Bot ID: 8317615229)"
    exit 1
fi

TOKEN=$1
USERNAME=$2
USER_ID=$3

echo "🔍 Testing Telegram API with provided token..."

# Test 1: getMe - Verify bot information
echo -e "\n📡 TEST 1: Checking bot information (getMe)"
curl -s "https://api.telegram.org/bot$TOKEN/getMe" | jq .

# Test 2: getUpdates - Check recent updates (useful to see who has messaged the bot)
echo -e "\n📡 TEST 2: Checking recent updates (getUpdates)"
curl -s "https://api.telegram.org/bot$TOKEN/getUpdates" | jq .

# Test 3: If username is provided, try to get chat info
if [ ! -z "$USERNAME" ]; then
    echo -e "\n📡 TEST 3: Looking up chat by username @$USERNAME (getChat)"
    curl -s -X POST "https://api.telegram.org/bot$TOKEN/getChat" \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\":\"@$USERNAME\"}" | jq .
fi

# Test 4: If user_id is provided, try to get chat info
if [ ! -z "$USER_ID" ]; then
    echo -e "\n📡 TEST 4: Looking up chat by user ID $USER_ID (getChat)"
    curl -s -X POST "https://api.telegram.org/bot$TOKEN/getChat" \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\":\"$USER_ID\"}" | jq .
fi

# Test 5: Check if bot domain is configured for Telegram Login
echo -e "\n📡 TEST 5: Checking bot settings for Telegram Login"
curl -s "https://api.telegram.org/bot$TOKEN/getMyCommands" | jq .

# Test 6: Check if the Python module setup is correct
echo -e "\n📡 TEST 6: Checking Python module setup"
if [ -f "telegram_login.py" ]; then
    echo "✅ telegram_login.py module exists in the current directory"
else
    echo "❌ ERROR: telegram_login.py module is missing!"
    echo "    Create the file in your project directory."
fi

# Check if Dockerfile/docker-compose is set up correctly
if grep -q "telegram_login.py" Dockerfile 2>/dev/null || grep -q "telegram_login.py" docker-compose.yaml 2>/dev/null; then
    echo "✅ Dockerfile/docker-compose appears to include telegram_login.py"
else
    echo "⚠️ Warning: Make sure telegram_login.py is copied into your Docker container!"
    echo "    You may need to update your Dockerfile or mount the file as a volume."
fi

# Print some guidance
echo -e "\n🔎 To find your user ID:"
echo "1. Talk to @userinfobot on Telegram and it will tell you your ID"
echo "2. Look for your ID in the getUpdates response above (if you've messaged the bot)"
echo -e "\n📝 Debugging chat_id issues:"
echo "1. Make sure you've messaged the bot directly (not in a group)"
echo "2. The bot can only find users by username who have messaged it first"
echo "3. If you know your user ID, try using it directly instead of username"
echo "4. Check if the bot has the necessary permissions" 
echo -e "\n🌐 Telegram Login Widget Setup:"
echo "1. Message @BotFather, select your bot and go to Bot Settings > Domain"
echo "2. Add your website domain there (e.g., example.com)"
echo "3. Use the widget HTML code from the script output below"

echo -e "\n✉️ To send a test message to a specific user ID:"
echo "curl -s -X POST \"https://api.telegram.org/bot\$TOKEN/sendMessage\" \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"chat_id\":\"YOUR_USER_ID\",\"text\":\"Test message from API\"}'"

# Generate Telegram Login Widget HTML code
BOT_USERNAME=$(curl -s "https://api.telegram.org/bot$TOKEN/getMe" | jq -r '.result.username')
if [ ! -z "$BOT_USERNAME" ]; then
    echo -e "\n🔐 Telegram Login Widget HTML (add to your website):"
    echo "<script async src=\"https://telegram.org/js/telegram-widget.js?22\" "
    echo "        data-telegram-login=\"$BOT_USERNAME\" "
    echo "        data-size=\"large\" "
    echo "        data-auth-url=\"/api/telegram-login\""
    echo "        data-request-access=\"write\">"
    echo "</script>"
    
    # Add verification about fiscalendar_bot
    if [ "$BOT_USERNAME" == "fiscalendar_bot" ]; then
        echo -e "\n✅ Verified: This is indeed your bot (@fiscalendar_bot)"
    else
        echo -e "\n⚠️ Warning: Bot username ($BOT_USERNAME) doesn't match expected bot (@fiscalendar_bot)"
        echo "   Did you use the correct token?"
    fi
fi

echo -e "\nDone!"
