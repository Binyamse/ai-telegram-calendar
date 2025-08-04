#!/bin/bash
# Script to test Telegram API functionality

# Set to exit on error
set -e

# Check if bot token is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <TELEGRAM_BOT_TOKEN> <USERNAME> [USER_ID]"
    echo "Example: $0 123456789:ABCD-EFG_HIJKlmnopQRSTUVwxyz binyams"
    echo "Example with user ID: $0 123456789:ABCD-EFG_HIJKlmnopQRSTUVwxyz '' 123456789"
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
fi

echo -e "\nDone!"
