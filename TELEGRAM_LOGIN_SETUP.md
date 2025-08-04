# Telegram Login Setup Instructions

This document explains how to set up the Telegram Login Widget for your calendar application.

## 1. Configure Your Bot with BotFather

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send the command `/mybots` and select your bot: **@fiscalendar_bot**
3. Click on "Bot Settings" > "Domain"
4. Add your domain name (e.g., `example.com`) where your application is hosted
5. Save the changes

## 2. Environment Variables

Set the following environment variables in your `.env` file or deployment environment:

```bash
# Your bot token (required for Telegram Login)
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ

# Allowed usernames (comma-separated, lowercase, without @)
ALLOWED_TELEGRAM_USERNAMES=username1,username2,username3

# Allowed user IDs (comma-separated)
ALLOWED_TELEGRAM_USER_IDS=123456789,987654321
```

## 3. Testing Telegram Login

You can use the included test script to verify your Telegram Login setup:

```bash
# Make the script executable
chmod +x test_telegram_api.sh

# Run the script with your bot token
./test_telegram_api.sh YOUR_BOT_TOKEN
```

This will:
1. Check if your bot is working correctly
2. Show recent updates to see users who have messaged your bot
3. Generate HTML code for the Telegram Login Widget

## 4. Security Considerations

- The Telegram Login Widget validates user identity on your server using a secure hash
- Only users with usernames or IDs in your allowed lists can access your application
- Telegram Login is more secure than the previous verification code method
- Users must have interacted with your bot at least once before they can use the widget

## 5. Troubleshooting

If you encounter issues:

1. Make sure your domain is correctly set in BotFather
2. Check that your bot token is correct
3. Verify that your whitelist contains the correct usernames and user IDs
4. Use the test script to diagnose specific issues
5. Check server logs for detailed error messages

## 6. Finding User IDs

To find a user's Telegram ID:

1. Tell the user to message [@userinfobot](https://t.me/userinfobot) on Telegram
2. The bot will reply with their account information including their numeric ID
3. Add this ID to the `ALLOWED_TELEGRAM_USER_IDS` environment variable
