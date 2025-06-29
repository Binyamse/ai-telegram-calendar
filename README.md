# Telegram Calendar Sync with LLM

Automatically extract calendar events from multiple Telegram groups using AI/LLM and sync them to your calendar system.

## Features

- 🤖 **LLM-Powered Event Extraction**: Uses OpenAI GPT or Anthropic Claude to intelligently parse text and extract calendar events
- 📱 **Multiple Group Support**: Monitor multiple Telegram groups simultaneously
- 🐳 **Dockerized**: Easy deployment with Docker and Docker Compose
- 🔄 **Real-time Monitoring**: Continuously monitors for new messages
- 📅 **Smart Date Parsing**: Handles various date formats and time zones
- 💾 **Persistent Storage**: Saves processed messages and extracted events
- 🔧 **Environment Configuration**: All settings via environment variables

## Example Text Processing

The system can intelligently parse complex text like:

```
Subject: Friendly Reminder: Parent-Teacher Conference – Today, June 27, 2025

Dear Parents and Guardians,

This is a kind reminder that our Parent-Teacher Conference will be held today, Friday, June 27, 2025. The conference will begin promptly at 8:30 AM and will continue until 4:00 PM.

There will be a lunch break from 12:00 PM to 1:00 PM, during which meetings will pause and resume promptly after.
```

And extract:
- **Event**: Parent-Teacher Conference
- **Date**: June 27, 2025
- **Time**: 8:30 AM - 4:00 PM
- **Break**: 12:00 PM - 1:00 PM
- **Location**: School (if mentioned)

## Quick Start

### 1. Get Telegram API Credentials

1. Go to https://my.telegram.org/auth
2. Log in with your phone number
3. Go to "API Development Tools"
4. Create a new application and save your `api_id` and `api_hash`

### 2. Get LLM API Key

Choose one:
- **OpenAI**: Get API key from https://platform.openai.com/api-keys
- **Anthropic**: Get API key from https://console.anthropic.com/

### 3. Find Your Group Identifiers

Run this helper script to find your group names/IDs:

```python
import asyncio
from telethon import TelegramClient

async def find_groups():
    client = TelegramClient('temp_session', API_ID, API_HASH)
    await client.start(phone=PHONE_NUMBER)
    
    print("Your Telegram Groups:")
    async for dialog in client.iter_dialogs():
        if dialog.is_group:
            username = dialog.entity.username or "No username"
            print(f"  Name: {dialog.name}")
            print(f"  Username: {username}")
            print(f"  ID: {dialog.entity.id}")
            print("  ---")

asyncio.run(find_groups())
```

### 4. Setup Environment

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your credentials:
   ```bash
   # Telegram API
   TELEGRAM_API_ID=12345678
   TELEGRAM_API_HASH=your_api_hash
   TELEGRAM_PHONE_NUMBER=+1234567890
   
   # Groups (comma-separated)
   TELEGRAM_GROUPS=schoolgroup2024,fisacademics
   
   # LLM API Key (choose one)
   OPENAI_API_KEY=sk-your-key-here
   # ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```

### 5. Run with Docker

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f telegram-calendar-sync

# Stop the service
docker-compose down
```

### 6. First Run Authentication

On first run, you'll need to authenticate with Telegram:

```bash
# View logs to see authentication prompt
docker-compose logs -f telegram-calendar-sync

# The system will ask for your phone verification code
# Enter it when prompted
```

## Output

The system generates several output files in the `./data` directory:

- **`events.json`**: Extracted calendar events in JSON format
- **`processed_messages.json`**: Processed message IDs to avoid duplicates
- **`telegram_session`**: Telegram session files
- **`telegram_calendar.log`**: Application logs

### Sample `events.json` Output

```json
[
  {
    "title": "Parent-Teacher Conference",
    "start_date": "2025-06-27T08:30:00",
    "end_date": "2025-06-27T16:00:00",
    "description": "Parent-Teacher Conference will be held today, Friday, June 27, 2025...",
    "location": "School",
    "source_group": "FIS Academics",
    "source_message_id": 12345,
    "confidence_score": 0.95
  },
  {
    "title": "Math Exam",
    "start_date": "2025-07-15T09:00:00",
    "end_date": null,
    "description": "Final mathematics examination for Grade 10",
    "location": "Room 101",
    "source_group": "Grade 10 Announcements",
    "source_message_id": 12346,
    "confidence_score": 0.88
  }
]
```

## Calendar Integration

### Google Calendar

To sync with Google Calendar, you can use the Google Calendar API:

```python
# Add this to your calendar integration script
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def sync_to_google_calendar():
    # Load events
    with open('./data/events.json', 'r') as f:
        events = json.load(f)
    
    # Initialize Google Calendar API
    service = build('calendar', 'v3', credentials=creds)
    
    for event in events:
        calendar_event = {
            'summary': event['title'],
            'start': {'dateTime': event['start_date']},
            'end': {'dateTime': event['end_date'] or event['start_date']},
            'description': event['description'],
            'location': event['location']
        }
        
        service.events().insert(
            calendarId='primary',
            body=calendar_event
        ).execute()
```

### Apple Calendar (iCal)

Export as ICS format:

```python
from icalendar import Calendar, Event
import json

def export_to_ics():
    cal = Calendar()
    
    with open('./data/events.json', 'r') as f:
        events = json.load(f)
    
    for event_data in events:
        event = Event()
        event.add('summary', event_data['title'])
        event.add('dtstart', datetime.fromisoformat(event_data['start_date']))
        if event_data['end_date']:
            event.add('dtend', datetime.fromisoformat(event_data['end_date']))
        event.add('description', event_data['description'])
        cal.add_component(event)
    
    with open('./data/calendar.ics', 'wb') as f:
        f.write(cal.to_ical())
```

## Configuration Options

### Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `TELEGRAM_API_ID` | ✅ | Telegram API ID | `12345678` |
| `TELEGRAM_API_HASH` | ✅ | Telegram API Hash | `abcdef123456` |
| `TELEGRAM_PHONE_NUMBER` | ✅ | Your phone number | `+1234567890` |
| `TELEGRAM_GROUPS` | ✅ | Comma-separated group list | `group1,group2` |
| `OPENAI_API_KEY` | ⚠️ | OpenAI API key | `sk-...` |
| `ANTHROPIC_API_KEY` | ⚠️ | Anthropic API key | `sk-ant-...` |
| `LOG_LEVEL` | ❌ | Logging level | `INFO` (default) |
| `SCAN_LIMIT` | ❌ | Messages to scan on startup | `100` (default) |

⚠️ = At least one LLM API key required

### Advanced Configuration

```bash
# Custom file paths
CALENDAR_OUTPUT_PATH=/custom/path/events.json
PROCESSED_MESSAGES_PATH=/custom/path/processed.json
SESSION_PATH=/custom/path/session

# Performance tuning
SCAN_LIMIT=200  # Scan more messages on startup
LOG_LEVEL=DEBUG  # More verbose logging
```

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   ```bash
   # Check your API credentials
   docker-compose logs telegram-calendar-sync
   
   # Remove session and re-authenticate
   rm -rf ./data/telegram_session*
   docker-compose restart telegram-calendar-sync
   ```

2. **Group Not Found**
   ```bash
   # List available groups
   python find_groups.py
   
   # Use group ID instead of username
   TELEGRAM_GROUPS=-1001234567890,anothergroup
   ```

3. **No Events Extracted**
   ```bash
   # Check LLM API key
   curl -H "Authorization: Bearer $OPENAI_API_KEY" \
        https://api.openai.com/v1/models
   
   # Enable debug logging
   LOG_LEVEL=DEBUG
   ```

4. **Memory Issues**
   ```bash
   # Increase Docker memory limits
   deploy:
     resources:
       limits:
         memory: 1G
   ```

### Monitoring

Monitor the system with:

```bash
# Real-time logs
docker-compose logs -f

# System resource usage
docker stats telegram-calendar-sync

# Event extraction stats
jq '. | length' ./data/events.json
```

## Security Considerations

- **API Keys**: Never commit API keys to version control
- **Session Files**: Keep Telegram session files secure
- **Network**: Consider running on private networks only
- **Permissions**: Run with minimal required permissions

## Development

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export TELEGRAM_API_ID=123456
export TELEGRAM_API_HASH=abcdef
# ... other vars

# Run directly
python telegram_calendar_sync.py
```

### Adding Custom LLM Providers

Extend the `LLMEventExtractor` class:

```python
async def extract_events_custom(self, text: str, current_date: str):
    # Your custom LLM integration
    # Return List[Dict[str, Any]]
    pass
```

### Custom Event Processing

Override the `process_message` method:

```python
async def process_message(self, message, group_name: str):
    # Custom message processing logic
    # Return List[CalendarEvent]
    pass
```

## Support

For issues and questions:

1. Check the logs: `docker-compose logs -f`
2. Review this README
3. Check Telegram API documentation
4. Verify LLM API status

## License

MIT License - feel free to modify and distribute.