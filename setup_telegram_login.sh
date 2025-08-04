#!/bin/bash
# Script to set up the Telegram Login Widget with your bot name

# Set to exit on error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if bot token is provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: Please provide your Telegram Bot Token${NC}"
    echo "Usage: $0 <TELEGRAM_BOT_TOKEN>"
    echo "Example: $0 123456789:ABCD-EFG_HIJKlmnopQRSTUVwxyz"
    exit 1
fi

TOKEN=$1

echo -e "${BLUE}Setting up Telegram Login Widget...${NC}"

# Get bot information including username
echo -e "${BLUE}Fetching bot information...${NC}"
BOT_INFO=$(curl -s "https://api.telegram.org/bot$TOKEN/getMe")
BOT_USERNAME=$(echo $BOT_INFO | jq -r '.result.username')

if [ -z "$BOT_USERNAME" ] || [ "$BOT_USERNAME" == "null" ]; then
    echo -e "${RED}Error: Could not retrieve bot username. Check your token.${NC}"
    echo "API Response: $BOT_INFO"
    exit 1
fi

echo -e "${GREEN}Found bot username: $BOT_USERNAME${NC}"

# Check if we need to update the web/index.html file
if [ -f "web/index.html" ]; then
    echo -e "${BLUE}Updating login widget in web/index.html...${NC}"
    
    # Backup the original file
    cp web/index.html web/index.html.bak
    echo -e "${GREEN}Created backup: web/index.html.bak${NC}"
    
    # Check if we're using the dynamic script
    if grep -q "telegram-login-button-container" web/index.html; then
        echo -e "${GREEN}Found dynamic login widget. It will automatically use the correct bot name.${NC}"
    else
        echo -e "${BLUE}Updating static login widget...${NC}"
        # Replace the widget script
        sed -i '' "s/data-telegram-login=\"[^\"]*\"/data-telegram-login=\"$BOT_USERNAME\"/" web/index.html
    fi
    
    echo -e "${GREEN}Login widget updated!${NC}"
else
    echo -e "${RED}Warning: Could not find web/index.html${NC}"
fi

# Provide setup instructions for BotFather
echo -e "\n${BLUE}=== IMPORTANT SETUP INSTRUCTIONS ===${NC}"
echo -e "1. Open Telegram and message @BotFather"
echo -e "2. Send the command: /mybots"
echo -e "3. Select your bot: @${BOT_USERNAME}"
echo -e "4. Click 'Bot Settings' > 'Domain'"
echo -e "5. Add your website domain (e.g., example.com - without http/https)"
echo -e "6. Save changes"

# Generate the widget HTML
echo -e "\n${GREEN}=== TELEGRAM LOGIN WIDGET HTML ===${NC}"
echo "<script async src=\"https://telegram.org/js/telegram-widget.js?22\""
echo "        data-telegram-login=\"$BOT_USERNAME\""
echo "        data-size=\"large\""
echo "        data-auth-url=\"/api/telegram-login\""
echo "        data-request-access=\"write\">"
echo "</script>"

echo -e "\n${GREEN}Setup completed!${NC}"
echo -e "Make sure to rebuild your Docker container if needed:"
echo -e "docker-compose build --no-cache telegram-calendar-sync"
echo -e "docker-compose up -d"
