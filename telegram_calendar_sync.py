# Reminder configuration from environment variables
REMINDER_DAYS_BEFORE = int(os.getenv('REMINDER_DAYS_BEFORE', '2'))  # Days before event to send reminder
REMINDER_CHECK_INTERVAL = int(os.getenv('REMINDER_CHECK_INTERVAL', '3600'))  # Seconds between checks (default: 1 hour)
REMINDER_MESSAGE_TEMPLATE = os.getenv('REMINDER_MESSAGE_TEMPLATE',
    '⏰ Reminder: Upcoming event in {days} days!\n\nTitle: {title}\nDate: {date}\n{location}{description}{link}')
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import tempfile
import asyncio
import os
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
import aiohttp
import uuid
from aiohttp import web
import time

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

# Google Calendar imports
from google.oauth2 import service_account
from googleapiclient.discovery import build


# Configuration from environment variables
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
PHONE_NUMBER = os.getenv('TELEGRAM_PHONE_NUMBER', '')
TELEGRAM_GROUPS = os.getenv('TELEGRAM_GROUPS', '').split(',')  # Comma-separated group usernames/IDs
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')  # For GPT-based extraction
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')  # Alternative to OpenAI
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')  # Alternative to OpenAI/Anthropic
GROQ_MODEL = os.getenv('GROQ_MODEL', 'gemma2-9b-it')  # Allow model selection for Groq
CALENDAR_OUTPUT_PATH = os.getenv('CALENDAR_OUTPUT_PATH', '/app/data/events.json')
PROCESSED_MESSAGES_PATH = os.getenv('PROCESSED_MESSAGES_PATH', '/app/data/processed_messages.json')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG')  # Default to DEBUG for more detailed logging
SCAN_LIMIT = int(os.getenv('SCAN_LIMIT', '100'))
SESSION_PATH = os.getenv('SESSION_PATH', '/app/data/telegram_session')
TELEGRAM_CODE = os.getenv('TELEGRAM_CODE', '')  # For verification code
TELEGRAM_2FA_PASSWORD = os.getenv('TELEGRAM_2FA_PASSWORD', '')  # For 2FA
GOOGLE_CALENDAR_CREDENTIALS = os.getenv('GOOGLE_CALENDAR_CREDENTIALS', '/app/data/google-credentials.json')
GOOGLE_CALENDAR_ID = os.getenv('GOOGLE_CALENDAR_ID', '')

# Allowed Telegram usernames for UI access
ALLOWED_TELEGRAM_USERNAMES = set(u.strip().lower() for u in os.getenv('ALLOWED_TELEGRAM_USERNAMES', '').split(',') if u.strip())


# Telegram bot notification config
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# Subscribed chat IDs file
SUBSCRIBED_CHAT_IDS_FILE = os.path.join(os.path.dirname(CALENDAR_OUTPUT_PATH), 'subscribed_chat_ids.json')

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/app/data/telegram_calendar.log') if os.path.exists('/app/data') else logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class CalendarEvent:
    title: str
    start_date: datetime
    end_date: Optional[datetime] = None
    description: str = ""
    location: str = ""
    source_group: str = ""
    source_message_id: int = 0
    confidence_score: float = 0.0
    
    source_type: str = "text"  # "text", "pdf", "image"
    telegram_link: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'start_date': self.start_date.isoformat() if isinstance(self.start_date, datetime) else None,
            'end_date': self.end_date.isoformat() if isinstance(self.end_date, datetime) else None,
            'timestamp': int(self.start_date.timestamp()) if isinstance(self.start_date, datetime) else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CalendarEvent':
        # Remove unknown fields (like 'timestamp')
        data = dict(data)  # Make a copy so we don't mutate the original
        data.pop('timestamp', None)
        data['start_date'] = datetime.fromisoformat(data['start_date'])
        if data.get('end_date'):
            data['end_date'] = datetime.fromisoformat(data['end_date'])
        return cls(**data)

class LLMEventExtractor:
    """Extract calendar events using LLM (OpenAI GPT, Anthropic Claude, or Groq)"""
    
    def __init__(self):
        self.openai_key = OPENAI_API_KEY
        self.anthropic_key = ANTHROPIC_API_KEY
        self.groq_key = GROQ_API_KEY
        self.groq_model = GROQ_MODEL
        
    async def extract_events_openai(self, text: str, current_date: str) -> List[Dict[str, Any]]:
        """Extract events using OpenAI GPT"""
        if not self.openai_key:
            return []
            
        prompt = f"""
Today's date: {current_date}

Analyze the following text and extract any calendar events, meetings, deadlines, or important dates.
Return a JSON array of events with this exact structure:

[
  {{
    "title": "Event name or description",
    "start_date": "YYYY-MM-DD",
    "start_time": "HH:MM" (if mentioned, otherwise null),
    "end_date": "YYYY-MM-DD" (if different from start_date, otherwise null),
    "end_time": "HH:MM" (if mentioned, otherwise null),
    "description": "Additional details about the event",
    "location": "Location if mentioned",
    "confidence_score": 0.95 (float between 0 and 1)
  }}
]

IMPORTANT DATE HANDLING:
1. For explicit dates like "June 27, 2025":
   - Use the exact date as specified
   - Convert to YYYY-MM-DD format (e.g., "2025-06-27")
   - Include all time information if provided

2. For relative dates (e.g., "tomorrow", "next week"):
   - Convert to absolute dates based on today ({current_date})
   - For "tomorrow" => use {(datetime.fromisoformat(current_date) + timedelta(days=1)).strftime('%Y-%m-%d')}

3. For same-day time ranges (e.g., "8:30 AM to 4:00 PM"):
   - Use the same date for start and end
   - Convert times to 24-hour format (e.g., "08:30" to "16:00")

4. For recurring patterns:
   - Extract each occurrence as a separate event
   - Use specific dates, not patterns

- If year is not mentioned, assume current year (2025)
- Always use YYYY-MM-DD format for dates
- Always use HH:MM format for times (24-hour)

Text to analyze:
{text}

Important:
- If year is not mentioned, assume current year (2025)
- Extract ALL dates and events mentioned
- Include recurring events if mentioned
- Be precise with date formats (YYYY-MM-DD)
- Use 24-hour time format (HH:MM)
- Return empty array [] if no events found
"""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {self.openai_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': 'gpt-4',  # Using correct model name
                        'messages': [
                            {'role': 'system', 'content': 'You are an expert at extracting calendar events from text. Always return valid JSON.'},
                            {'role': 'user', 'content': prompt}
                        ],
                        'temperature': 0.1
                    }
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        content = result['choices'][0]['message']['content'].strip()
                        
                        try:
                            # First try to parse the content directly as JSON
                            return json.loads(content)
                        except json.JSONDecodeError:
                            # If direct parsing fails, try to extract JSON from markdown
                            if '```json' in content:
                                content = content.split('```json')[1].split('```')[0].strip()
                            elif '```' in content:
                                content = content.split('```')[1].split('```')[0].strip()
                            return json.loads(content)
                    else:
                        logger.error(f"OpenAI API error: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return []

    async def extract_events_anthropic(self, text: str, current_date: str) -> List[Dict[str, Any]]:
        """Extract events using Anthropic Claude"""
        if not self.anthropic_key:
            return []
            
        prompt = f"""Today's date: {current_date}

Analyze this text and extract calendar events. Return only a JSON array with this structure:

[
  {{
    "title": "Event name",
    "start_date": "YYYY-MM-DD",
    "start_time": "HH:MM",
    "end_date": "YYYY-MM-DD",
    "end_time": "HH:MM",
    "description": "Details",
    "location": "Location",
    "confidence_score": 0.95
  }}
]

IMPORTANT DATE HANDLING:
- For relative dates like "tomorrow", "next week", etc., convert them to absolute dates based on today's date ({current_date})
- For "tomorrow" => use {(datetime.fromisoformat(current_date) + timedelta(days=1)).strftime('%Y-%m-%d')}
- Always convert relative dates to absolute dates before returning
- Use YYYY-MM-DD format for all dates

Text: {text}"""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.anthropic.com/v1/messages',
                    headers={
                        'x-api-key': self.anthropic_key,
                        'Content-Type': 'application/json',
                        'anthropic-version': '2023-06-01'
                    },
                    json={
                        'model': 'claude-3-haiku-20240307',
                        'max_tokens': 1000,
                        'messages': [{'role': 'user', 'content': prompt}]
                    }
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        content = result.get('content', [{}])[0].get('text', '').strip()
                        
                        try:
                            # First try to parse the content directly as JSON
                            return json.loads(content)
                        except json.JSONDecodeError:
                            # If direct parsing fails, try to extract JSON from markdown
                            if '```json' in content:
                                content = content.split('```json')[1].split('```')[0].strip()
                            elif '```' in content:
                                content = content.split('```')[1].split('```')[0].strip()
                            
                            try:
                                return json.loads(content)
                            except json.JSONDecodeError:
                                logger.error(f"Failed to parse Anthropic response as JSON: {content}")
                                return []
                    else:
                        logger.error(f"Anthropic API error: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error calling Anthropic API: {e}")
            return []

    async def extract_events_groq(self, text: str, current_date: str) -> List[Dict[str, Any]]:
        """Extract events using Groq LLM with model selection"""
        if not self.groq_key:
            return []
        model = self.groq_model or 'mixtral-8x7b-32768'
        logger.debug(f"Using Groq model: {model}")
        prompt = f"""
Today's date: {current_date}

Analyze the following text and extract any calendar events, meetings, deadlines, or important dates.
Return a JSON array of events with this exact structure:

[
  {{
    "title": "Event name or description",
    "start_date": "YYYY-MM-DD",
    "start_time": "HH:MM" (if mentioned, otherwise null),
    "end_date": "YYYY-MM-DD" (if different from start_date, otherwise null),
    "end_time": "HH:MM" (if mentioned, otherwise null),
    "description": "Additional details about the event",
    "location": "Location if mentioned",
    "confidence_score": 0.95 (float between 0 and 1)
  }}
]

IMPORTANT DATE HANDLING:
1. For explicit dates like "June 27, 2025":
   - Use the exact date as specified
   - Convert to YYYY-MM-DD format (e.g., "2025-06-27")
   - Include all time information if provided

2. For relative dates (e.g., "tomorrow", "next week"):
   - Convert to absolute dates based on today ({current_date})
   - For "tomorrow" => use {(datetime.fromisoformat(current_date) + timedelta(days=1)).strftime('%Y-%m-%d')}

3. For same-day time ranges (e.g., "8:30 AM to 4:00 PM"):
   - Use the same date for start and end
   - Convert times to 24-hour format (e.g., "08:30" to "16:00")

Text to analyze:
{text}"""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {self.groq_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': model,
                        'messages': [
                            {'role': 'system', 'content': 'You are an expert at extracting calendar events from text. Always return valid JSON.'},
                            {'role': 'user', 'content': prompt}
                        ],
                        'temperature': 0.1
                    }
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        content = result['choices'][0]['message']['content'].strip()
                        try:
                            # First try to parse the content directly as JSON
                            return json.loads(content)
                        except json.JSONDecodeError:
                            # If direct parsing fails, try to extract JSON from markdown
                            if '```json' in content:
                                content = content.split('```json')[1].split('```')[0].strip()
                            elif '```' in content:
                                content = content.split('```')[1].split('```')[0].strip()
                            return json.loads(content)
                    else:
                        logger.error(f"Groq API error: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"Error calling Groq API: {e}")
            return []

    async def extract_events(self, text: str, reference_date: str = None) -> List[CalendarEvent]:
        """Extract events using available LLM provider"""
        # Use provided reference date or UTC timezone for consistency
        current_date = reference_date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
        logger.debug(f"Extracting events with reference date: {current_date}")
        
        # Try providers in order: OpenAI, Groq, Anthropic
        events_data = []
        try:
            if self.openai_key:
                logger.debug("Using OpenAI for extraction")
                events_data = await self.extract_events_openai(text, current_date)
                logger.debug(f"OpenAI response: {json.dumps(events_data, indent=2)}")
            elif self.groq_key:
                logger.debug("Using Groq for extraction")
                events_data = await self.extract_events_groq(text, current_date)
                logger.debug(f"Groq response: {json.dumps(events_data, indent=2)}")
            elif self.anthropic_key:
                logger.debug("Using Anthropic for extraction")
                events_data = await self.extract_events_anthropic(text, current_date)
                logger.debug(f"Anthropic response: {json.dumps(events_data, indent=2)}")
            
            if not events_data:
                logger.debug(f"No events extracted from message text: {text[:200]}...")
                return []
                
        except Exception as e:
            logger.error(f"Error in LLM extraction: {e}", exc_info=True)
            return []
        
        # Convert to CalendarEvent objects
        events = []
        for event_data in events_data:
            try:
                # Validate and parse the date with UTC timezone
                try:
                    start_date = datetime.strptime(event_data['start_date'], '%Y-%m-%d')
                    start_date = start_date.replace(tzinfo=timezone.utc)
                except ValueError as e:
                    logger.error(f"Invalid date format in event: {event_data['start_date']}")
                    continue

                # Add time if provided (in UTC)
                if event_data.get('start_time'):
                    try:
                        time_parts = event_data['start_time'].split(':')
                        if len(time_parts) == 2 and all(t.isdigit() for t in time_parts):
                            hour, minute = map(int, time_parts)
                            if 0 <= hour < 24 and 0 <= minute < 60:
                                start_date = start_date.replace(hour=hour, minute=minute)
                            else:
                                logger.error(f"Invalid time values in event: {event_data['start_time']}")
                        else:
                            logger.error(f"Invalid time format in event: {event_data['start_time']}")
                    except Exception as e:
                        logger.error(f"Error parsing time: {e}")
                
                # Handle end date/time (in UTC)
                end_date = None
                if event_data.get('end_date'):
                    end_date = datetime.strptime(event_data['end_date'], '%Y-%m-%d')
                    end_date = end_date.replace(tzinfo=timezone.utc)
                    if event_data.get('end_time'):
                        time_parts = event_data['end_time'].split(':')
                        end_date = end_date.replace(hour=int(time_parts[0]), minute=int(time_parts[1]))
                elif event_data.get('end_time'):
                    # Same day, different end time
                    end_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    time_parts = event_data['end_time'].split(':')
                    end_date = end_date.replace(hour=int(time_parts[0]), minute=int(time_parts[1]))
                
                event = CalendarEvent(
                    title=event_data['title'],
                    start_date=start_date,
                    end_date=end_date,
                    description=event_data.get('description', ''),
                    location=event_data.get('location', ''),
                    confidence_score=event_data.get('confidence_score', 0.8)
                )
                events.append(event)
                
            except Exception as e:
                logger.error(f"Error parsing event data {event_data}: {e}")
                continue
        
        return events

class GoogleCalendarClient:
    def __init__(self, credentials_path: str, calendar_id: str):
        self.calendar_id = calendar_id
        self.service = None
        self.credentials_path = credentials_path
        self._authenticate()

    def _authenticate(self):
        try:
            scopes = ['https://www.googleapis.com/auth/calendar']
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=scopes)
            self.service = build('calendar', 'v3', credentials=credentials)
            logger.info('Authenticated with Google Calendar API')
        except Exception as e:
            logger.error(f'Google Calendar authentication failed: {e}')
            self.service = None

    def create_event(self, event: 'CalendarEvent'):
        if not self.service or not self.calendar_id:
            logger.warning('Google Calendar service or calendar ID not configured.')
            return None
        try:
            event_body = {
                'summary': event.title,
                'description': event.description,
                'start': {
                    'dateTime': event.start_date.isoformat(),
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': (event.end_date or event.start_date).isoformat(),
                    'timeZone': 'UTC',
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 24 * 60},  # 1 day before
                        {'method': 'email', 'minutes': 24 * 60}   # 1 day before
                    ],
                },
            }
            # Only include location if present and non-empty
            if event.location:
                event_body['location'] = event.location
            # Only include source if a valid URL is present (Google Calendar requires a valid URL)
            # Here, we check if event.description contains a URL and use it as the source
            url_match = None
            if event.description:
                url_match = re.search(r'https?://\S+', event.description)
            if url_match:
                event_body['source'] = {
                    'title': event.source_group or 'Telegram',
                    'url': url_match.group(0)
                }
            created_event = self.service.events().insert(calendarId=self.calendar_id, body=event_body).execute()
            logger.info(f'Event pushed to Google Calendar: {event.title} ({created_event.get("id")})')
            return created_event
        except Exception as e:
            logger.error(f'Failed to create Google Calendar event: {e}')
            return None

class TelegramCalendarSync:
    def is_allowed_user(self, username: str) -> bool:
        """Check if the Telegram username is allowed for UI access."""
        return username and username.lower() in ALLOWED_TELEGRAM_USERNAMES
    async def handle_login_request(self, request: web.Request) -> web.Response:
        """Handle login request: verify allowed username and send code via bot."""
        try:
            data = await request.json()
            username = data.get('username', '').strip().lower()
            if not self.is_allowed_user(username):
                return web.json_response({'error': 'User not allowed'}, status=403)
            # Generate a random 6-digit code
            code = str(uuid.uuid4().int % 1000000).zfill(6)
            # Store code in a temp file (per username)
            code_file = os.path.join(os.path.dirname(CALENDAR_OUTPUT_PATH), f'login_code_{username}.json')
            with open(code_file, 'w') as f:
                json.dump({'code': code, 'timestamp': time.time()}, f)
            # Send code via Telegram bot
            if TELEGRAM_BOT_TOKEN:
                async with aiohttp.ClientSession() as session:
                    # Find user chat ID via username
                    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChat"
                    payload = {"chat_id": f"@{username}"}
                    async with session.post(url, json=payload) as resp:
                        chat_info = await resp.json()
                        chat_id = None
                        if chat_info.get('ok') and chat_info.get('result', {}).get('id'):
                            chat_id = chat_info['result']['id']
                        if chat_id:
                            msg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                            msg_payload = {"chat_id": chat_id, "text": f"Your login code: {code}"}
                            await session.post(msg_url, json=msg_payload)
                        else:
                            logger.warning(f"Could not find chat_id for @{username}")
            logger.info(f"Sent login code to @{username}")
            return web.json_response({'status': 'code_sent'})
        except Exception as e:
            logger.error(f"Error in login request: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def handle_login_verify(self, request: web.Request) -> web.Response:
        """Handle login code verification: check allowed user and code."""
        try:
            data = await request.json()
            username = data.get('username', '').strip().lower()
            code = data.get('code', '').strip()
            if not self.is_allowed_user(username):
                return web.json_response({'error': 'User not allowed'}, status=403)
            code_file = os.path.join(os.path.dirname(CALENDAR_OUTPUT_PATH), f'login_code_{username}.json')
            if not os.path.exists(code_file):
                return web.json_response({'error': 'No code found. Please request a new code.'}, status=400)
            with open(code_file, 'r') as f:
                code_data = json.load(f)
            # Check code and expiry (valid for 10 min)
            if code_data['code'] != code or time.time() - code_data['timestamp'] > 600:
                return web.json_response({'error': 'Invalid or expired code.'}, status=400)
            # Set session cookie
            response = web.json_response({'status': 'verified'})
            response.set_cookie('tg_user', username, max_age=86400, httponly=True)
            # Remove code file after successful login
            os.remove(code_file)
            return response
        except Exception as e:
            logger.error(f"Error in login verify: {e}")
            return web.json_response({'error': str(e)}, status=500)
    def get_subscribed_chat_ids(self):
        """Load subscribed chat IDs from file."""
        if os.path.exists(SUBSCRIBED_CHAT_IDS_FILE):
            try:
                with open(SUBSCRIBED_CHAT_IDS_FILE, 'r') as f:
                    return set(json.load(f))
            except Exception as e:
                logger.error(f"Error loading subscribed chat IDs: {e}")
        return set()

    def add_subscribed_chat_id(self, chat_id):
        """Add a chat ID to the subscribed list."""
        chat_ids = self.get_subscribed_chat_ids()
        chat_ids.add(str(chat_id))
        try:
            with open(SUBSCRIBED_CHAT_IDS_FILE, 'w') as f:
                json.dump(list(chat_ids), f)
        except Exception as e:
            logger.error(f"Error saving subscribed chat IDs: {e}")

    def remove_subscribed_chat_id(self, chat_id):
        """Remove a chat ID from the subscribed list."""
        chat_ids = self.get_subscribed_chat_ids()
        chat_ids.discard(str(chat_id))
        try:
            with open(SUBSCRIBED_CHAT_IDS_FILE, 'w') as f:
                json.dump(list(chat_ids), f)
        except Exception as e:
            logger.error(f"Error saving subscribed chat IDs: {e}")

    async def send_telegram_reminder(self, event: CalendarEvent):
        """Send a reminder message for an event via Telegram bot to all subscribed users."""
        if not TELEGRAM_BOT_TOKEN:
            logger.warning("Telegram bot token not set for reminders.")
            return
        chat_ids = self.get_subscribed_chat_ids()
        if not chat_ids:
            logger.info("No subscribed users to send reminders.")
            return
        message = REMINDER_MESSAGE_TEMPLATE.format(
            days=REMINDER_DAYS_BEFORE,
            title=event.title,
            date=event.start_date.strftime('%Y-%m-%d %H:%M'),
            location=(f"Location: {event.location}\n" if event.location else ''),
            description=(f"Description: {event.description[:200]}\n" if event.description else ''),
            link=(f"Link: {event.telegram_link}\n" if event.telegram_link else '')
        )
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            for chat_id in chat_ids:
                payload = {
                    "chat_id": chat_id,
                    "text": message
                }
                try:
                    async with session.post(url, json=payload) as resp:
                        if resp.status == 200:
                            logger.info(f"Sent reminder for event '{event.title}' to Telegram chat {chat_id}")
                        else:
                            logger.error(f"Failed to send Telegram reminder to {chat_id}: {await resp.text()}")
                except Exception as e:
                    logger.error(f"Error sending Telegram reminder to {chat_id}: {e}")

    async def reminder_task(self):
        """Background task to check for events in 2 days and send reminders."""
        logger.info("Starting Telegram reminder background task...")
        while True:
            try:
                # Load events
                if os.path.exists(CALENDAR_OUTPUT_PATH):
                    with open(CALENDAR_OUTPUT_PATH, 'r') as f:
                        events_data = json.load(f)
                else:
                    events_data = []
                now = datetime.now(timezone.utc)
                target_date = now + timedelta(days=REMINDER_DAYS_BEFORE)
                reminders = []
                for e in events_data:
                    try:
                        event_dt = None
                        if 'timestamp' in e:
                            event_dt = datetime.fromtimestamp(e['timestamp'], tz=timezone.utc)
                        elif 'start_date' in e:
                            event_dt = datetime.fromisoformat(e['start_date'])
                        if event_dt:
                            delta = (event_dt - target_date).total_seconds()
                            # ±12 hours window, configurable if needed
                            if abs(delta) < 12*3600 and event_dt > now:
                                reminders.append(CalendarEvent.from_dict(e))
                    except Exception as ex:
                        logger.error(f"Error parsing event for reminder: {ex}")
                # Avoid duplicate reminders: keep track in a file
                sent_file = os.path.join(os.path.dirname(CALENDAR_OUTPUT_PATH), 'sent_reminders.json')
                sent_ids = set()
                if os.path.exists(sent_file):
                    try:
                        sent_ids = set(json.load(open(sent_file)))
                    except Exception:
                        sent_ids = set()
                new_sent = set()
                for event in reminders:
                    event_id = f"{event.title}_{event.start_date.isoformat()}"
                    if event_id not in sent_ids:
                        await self.send_telegram_reminder(event)
                        new_sent.add(event_id)
                # Update sent reminders file
                if new_sent:
                    with open(sent_file, 'w') as f:
                        json.dump(list(sent_ids | new_sent), f)
                logger.info(f"Checked reminders: {len(reminders)} events, {len(new_sent)} sent.")
            except Exception as e:
                logger.error(f"Error in reminder task: {e}")
            await asyncio.sleep(REMINDER_CHECK_INTERVAL)
    def __init__(self):
        self.client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
        self.llm_extractor = LLMEventExtractor()
        self.processed_messages = set()
        self.events_file = CALENDAR_OUTPUT_PATH
        self.processed_messages_file = PROCESSED_MESSAGES_PATH
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.events_file), exist_ok=True)
        self.load_processed_messages()

        # Web server for uploads
        self.web_app = web.Application()
        self.web_app.add_routes([
            web.post('/upload', self.handle_upload),
            web.post('/dismiss-event', self.handle_dismiss_event),
            web.post('/clear-dismissed', self.handle_clear_dismissed),
            web.post('/subscribe-reminders', self.handle_subscribe_reminders),
            web.post('/unsubscribe-reminders', self.handle_unsubscribe_reminders)
        ])
    async def handle_subscribe_reminders(self, request: web.Request) -> web.Response:
        """Handle user subscription to Telegram reminders."""
        try:
            data = await request.json()
            chat_id = data.get('chat_id')
            if not chat_id:
                return web.json_response({'error': 'chat_id required'}, status=400)
            self.add_subscribed_chat_id(chat_id)
            logger.info(f"User {chat_id} subscribed to reminders.")
            return web.json_response({'status': 'subscribed'})
        except Exception as e:
            logger.error(f"Error subscribing to reminders: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def handle_unsubscribe_reminders(self, request: web.Request) -> web.Response:
        """Handle user unsubscription from Telegram reminders."""
        try:
            data = await request.json()
            chat_id = data.get('chat_id')
            if not chat_id:
                return web.json_response({'error': 'chat_id required'}, status=400)
            self.remove_subscribed_chat_id(chat_id)
            logger.info(f"User {chat_id} unsubscribed from reminders.")
            return web.json_response({'status': 'unsubscribed'})
        except Exception as e:
            logger.error(f"Error unsubscribing from reminders: {e}")
            return web.json_response({'error': str(e)}, status=500)

        # Google Calendar client
        self.gcal = None
        if GOOGLE_CALENDAR_ID and os.path.exists(GOOGLE_CALENDAR_CREDENTIALS):
            self.gcal = GoogleCalendarClient(GOOGLE_CALENDAR_CREDENTIALS, GOOGLE_CALENDAR_ID)
        else:
            logger.info('Google Calendar integration not enabled (missing credentials or calendar ID)')

    def load_processed_messages(self):
        """Load previously processed message IDs, robust to file errors and empty files."""
        try:
            logger.debug(f"Loading processed messages from file: {os.path.abspath(self.processed_messages_file)}")
            if os.path.exists(self.processed_messages_file):
                with open(self.processed_messages_file, 'r') as f:
                    content = f.read().strip()
                    if not content or content == '[]':
                        logger.debug("No processed messages found (file empty or only []).")
                        self.processed_messages = set()
                        return
                    try:
                        loaded = json.loads(content)
                        self.processed_messages = set(loaded)
                        logger.info(f"Loaded {len(self.processed_messages)} processed message IDs from file.")
                    except Exception as e:
                        logger.error(f"Error parsing processed_messages.json: {e}. File content: {content}")
                        self.processed_messages = set()
            else:
                logger.debug("Processed messages file does not exist, starting with empty set.")
                self.processed_messages = set()
        except Exception as e:
            logger.error(f"Error loading processed messages: {e}")
            self.processed_messages = set()
    
    def save_processed_messages(self):
        """Save processed message IDs, only if there are any."""
        try:
            logger.debug(f"Saving processed messages to file: {os.path.abspath(self.processed_messages_file)}")
            logger.debug(f"Saving {len(self.processed_messages)} processed message IDs.")
            with open(self.processed_messages_file, 'w') as f:
                json.dump(list(self.processed_messages), f)
        except Exception as e:
            logger.error(f"Error saving processed messages: {e}")
    
    def load_existing_events(self) -> List[CalendarEvent]:
        """Load existing events from file, robust to file errors and empty files."""
        try:
            logger.debug(f"Loading events from file: {os.path.abspath(self.events_file)}")
            if os.path.exists(self.events_file):
                with open(self.events_file, 'r') as f:
                    content = f.read().strip()
                    if not content or content == '[]':
                        logger.debug("No existing events found (file empty or only []).")
                        return []
                    try:
                        events_data = json.loads(content)
                        logger.debug(f"Loaded {len(events_data)} existing events from file.")
                        return [CalendarEvent.from_dict(event) for event in events_data]
                    except Exception as e:
                        logger.error(f"Error parsing events.json: {e}. File content: {content}")
                        return []
        except Exception as e:
            logger.error(f"Error loading existing events: {e}")
        return []
    
    def save_events(self, events: List[CalendarEvent], force_flush: bool = False):
        """Save events to file and Google Calendar, avoiding duplicates."""
        try:
            logger.debug(f"Saving events to file: {os.path.abspath(self.events_file)}")
            existing_events = self.load_existing_events()
            logger.debug(f"Before saving, {len(existing_events)} events loaded from file.")
            existing_signatures = {
                (e.title, e.start_date.date(), e.source_group, e.source_message_id)
                for e in existing_events
            }
            new_events_added = 0
            for event in events:
                signature = (event.title, event.start_date.date(), event.source_group, event.source_message_id)
                if signature not in existing_signatures:
                    existing_events.append(event)
                    existing_signatures.add(signature)
                    new_events_added += 1
                    logger.debug(f"Adding new event: {event.title} on {event.start_date}")
                    # Push to Google Calendar if enabled
                    if self.gcal:
                        self.gcal.create_event(event)
            try:
                with open(self.events_file, 'w') as f:
                    json_data = [event.to_dict() for event in existing_events]
                    json.dump(json_data, f, indent=2, default=str)
                    f.flush()
                    os.fsync(f.fileno())
                logger.info(f"Saved events file with {len(existing_events)} total events (added {new_events_added} new events)")
            except Exception as e:
                logger.error(f"Error writing events to file: {e}")
        except Exception as e:
            logger.error(f"Error in save_events: {e}")

    async def extract_text_from_media(self, file_path: str) -> tuple[Optional[str], Optional[str]]:
        """Extracts text from a given file path (PDF or image)."""
        source_type = None
        text = None
        file_ext = os.path.splitext(file_path)[1].lower()

        if file_ext == '.pdf':
            try:
                doc = fitz.open(file_path)
                text = "\n".join(page.get_text() for page in doc)
                source_type = "pdf"
                logger.info(f"Extracted text from PDF ({len(text)} chars)")
            except Exception as e:
                logger.error(f"PDF extraction failed: {e}")
        elif file_ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp']:
            try:
                img = Image.open(file_path)
                text = pytesseract.image_to_string(img)
                source_type = "image"
                logger.info(f"Extracted text from image ({len(text)} chars)")
            except Exception as e:
                logger.error(f"Image OCR failed: {e}")
        
        return text, source_type

    async def handle_upload(self, request: web.Request) -> web.Response:
        """Handle file uploads from the web UI."""
        try:
            reader = await request.multipart()
            field = await reader.next()
            if not field or field.name != 'file':
                return web.json_response({'error': 'File field is missing'}, status=400)

            filename = field.filename
            logger.info(f"Handling upload for file: {filename}")

            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    tmp.write(chunk)
                tmp_path = tmp.name

            text, source_type = await self.extract_text_from_media(tmp_path)

            if not text or not source_type:
                os.unlink(tmp_path)
                return web.json_response({'error': 'Could not extract text from file or unsupported file type.'}, status=400)

            reference_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            extracted_events = await self.llm_extractor.extract_events(text, reference_date)
            
            events = []
            for event in extracted_events:
                event.source_group = f"Uploaded File: {filename}"
                event.source_message_id = int(uuid.uuid4().int & (1<<31)-1)
                event.source_type = source_type
                if not event.description:
                    event.description = text[:500]
                if event.confidence_score >= 0.5:
                    events.append(event)
                    logger.info(f"Extracted event from upload: {event.title}")

            if events:
                self.save_events(events, force_flush=True)
                logger.info(f"Saved {len(events)} events from uploaded file {filename}")

            os.unlink(tmp_path)
            return web.json_response({'status': 'success', 'events_found': len(events)})
        except Exception as e:
            logger.error(f"Error handling upload: {e}", exc_info=True)
            return web.json_response({'error': str(e)}, status=500)

    async def handle_dismiss_event(self, request: web.Request) -> web.Response:
        """Handle dismissing an event from the UI."""
        try:
            data = await request.json()
            event_id = data.get('eventId')
            
            if event_id is None:
                return web.json_response({'error': 'eventId is required'}, status=400)
            
            # Load existing dismissed events
            dismissed_file = os.path.join(os.path.dirname(CALENDAR_OUTPUT_PATH), 'dismissed_events.json')
            dismissed_events = []
            
            if os.path.exists(dismissed_file):
                try:
                    with open(dismissed_file, 'r') as f:
                        dismissed_events = json.load(f)
                except:
                    dismissed_events = []
            
            # Add new dismissed event if not already there
            if event_id not in dismissed_events:
                dismissed_events.append(event_id)
                
                # Save updated dismissed events
                with open(dismissed_file, 'w') as f:
                    json.dump(dismissed_events, f)
                
                logger.info(f"Event {event_id} dismissed")
            
            return web.json_response({'status': 'success'})
        except Exception as e:
            logger.error(f"Error dismissing event: {e}", exc_info=True)
            return web.json_response({'error': str(e)}, status=500)

    async def handle_clear_dismissed(self, request: web.Request) -> web.Response:
        """Handle clearing all dismissed events."""
        try:
            dismissed_file = os.path.join(os.path.dirname(CALENDAR_OUTPUT_PATH), 'dismissed_events.json')
            
            # Remove the dismissed events file
            if os.path.exists(dismissed_file):
                os.remove(dismissed_file)
                logger.info("All dismissed events cleared")
            
            return web.json_response({'status': 'success'})
        except Exception as e:
            logger.error(f"Error clearing dismissed events: {e}", exc_info=True)
            return web.json_response({'error': str(e)}, status=500)

    async def process_message(self, message, group_name: str) -> List[CalendarEvent]:
        """Process a single message and extract calendar events using LLM"""
        events = []
        
        # Skip if already processed
        message_key = f"{group_name}_{message.id}"
        if message_key in self.processed_messages:
            logger.debug(f"Skipping already processed message {message_key}")
            return events
        


        text = message.text or ""
        extracted_texts = []
        extracted_types = []
        if text.strip():
            extracted_texts.append(text)
            extracted_types.append("text")

        # --- Media extraction: PDF and images ---
        try:
            if getattr(message, 'media', None):
                with tempfile.TemporaryDirectory() as tmpdir:
                    file_path = await message.download_media(file=tmpdir)
                    if file_path:
                        logger.info(f"Downloaded media to {file_path}")
                        media_text, media_type = await self.extract_text_from_media(file_path)
                        if media_text and media_type:
                            extracted_texts.append(media_text)
                            extracted_types.append(media_type)
        except Exception as e:
            logger.error(f"Media extraction error: {e}")

        if not any(t.strip() for t in extracted_texts):
            logger.debug(f"No text or extractable media in message from {group_name}")
            self.processed_messages.add(message_key)
            return events

        try:
            # Use message date as reference point for relative dates
            message_date = message.date.replace(tzinfo=timezone.utc)
            reference_date = message_date.strftime('%Y-%m-%d')
            for idx, text_variant in enumerate(extracted_texts):
                logger.debug(f"Sending to LLM for extraction: {text_variant[:500]}...")
                extracted_events = await self.llm_extractor.extract_events(text_variant, reference_date)
                logger.debug(f"LLM returned {len(extracted_events)} potential events")
                for event in extracted_events:
                    event.source_group = group_name
                    event.source_message_id = message.id
                    event.source_type = extracted_types[idx] if idx < len(extracted_types) else "text"
                    # Telegram link: https://t.me/c/{chat_id}/{message_id} (for private/supergroups)
                    # or https://t.me/{username}/{message_id} (for public groups)
                    try:
                        if hasattr(message, 'chat') and hasattr(message.chat, 'username') and message.chat.username:
                            event.telegram_link = f"https://t.me/{message.chat.username}/{message.id}"
                        elif hasattr(message, 'chat') and hasattr(message.chat, 'id'):
                            chat_id = str(message.chat.id)
                            if chat_id.startswith("-100"):
                                event.telegram_link = f"https://t.me/c/{chat_id[4:]}/{message.id}"
                    except Exception as e:
                        logger.error(f"Failed to build telegram link: {e}")
                    if not event.description:
                        event.description = text_variant[:500]
                    if (event.confidence_score >= 0.5 and 
                        event.start_date.replace(tzinfo=timezone.utc) >= message_date - timedelta(days=1)):
                        events.append(event)
                        logger.info(f"Extracted event: {event.title} on {event.start_date.strftime('%Y-%m-%d %H:%M')} (confidence: {event.confidence_score:.2f})")
                    else:
                        logger.debug(f"Rejected event: {event.title} (confidence: {event.confidence_score:.2f}, date: {event.start_date})")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

        # Mark message as processed
        self.processed_messages.add(message_key)

        if not events:
            logger.debug(f"No events found in message from {group_name}")

        return events
    
    async def scan_group_messages(self, group_identifier: str, limit: int = SCAN_LIMIT):
        """Scan recent messages from a specific group"""
        try:
            logger.info(f"Scanning {limit} recent messages from {group_identifier}")
            # Get the chat entity
            chat = await self.client.get_entity(group_identifier)
            group_name = getattr(chat, 'title', str(group_identifier))
            all_events = []
            message_count = 0
            # Get recent messages
            async for message in self.client.iter_messages(chat, limit=limit):
                message_count += 1
                events = await self.process_message(message, group_name)
                if events:  # Only process if we found events
                    all_events.extend(events)
                    # Save events immediately when found
                    self.save_events(events)
                # Always save processed messages after each message
                self.save_processed_messages()
                # Progress indicator
                if message_count % 10 == 0:
                    logger.info(f"Processed {message_count}/{limit} messages from {group_name}, found {len(all_events)} events so far")
                    await asyncio.sleep(0.5)  # Small delay to avoid rate limiting
            if all_events:
                logger.info(f"Found total of {len(all_events)} calendar events in {group_name}")
            else:
                logger.info(f"No calendar events found in {group_name}")
            return all_events
        except Exception as e:
            logger.error(f"Error scanning group {group_identifier}: {e}")
            return []

    async def scan_all_groups(self):
        """Scan all configured groups"""
        total_events = []
        total_groups = len([g for g in TELEGRAM_GROUPS if g.strip()])
        current_group = 0
        
        for group in TELEGRAM_GROUPS:
            group = group.strip()
            if group:
                current_group += 1
                logger.info(f"Processing group {current_group}/{total_groups}: {group}")
                
                events = await self.scan_group_messages(group)
                if events:
                    total_events.extend(events)
                    # Save accumulated events from this group
                    self.save_events(events, force_flush=True)
                
                self.save_processed_messages()
                
                # Show progress
                logger.info(f"Progress: {current_group}/{total_groups} groups processed, {len(total_events)} total events found")
                
                # Delay between groups
                if current_group < total_groups:
                    await asyncio.sleep(1)
        
        # Final save to ensure all events are persisted
        if total_events:
            self.save_events(total_events, force_flush=True)
            
        logger.info(f"Completed scanning all groups. Total events found: {len(total_events)}")
        return total_events
    
    async def start_monitoring(self):
        """Start real-time monitoring of all groups"""
        try:
            logger.info("Starting real-time monitoring...")
            
            # Get all chat entities
            chats = []
            for group in TELEGRAM_GROUPS:
                group = group.strip()
                if group:
                    try:
                        chat = await self.client.get_entity(group)
                        chats.append(chat)
                        logger.info(f"Monitoring group: {getattr(chat, 'title', str(group))}")
                    except Exception as e:
                        logger.error(f"Could not add group {group} to monitoring: {e}")
            
            if not chats:
                logger.error("No valid groups to monitor")
                return
            
            @self.client.on(events.NewMessage(chats=chats))
            async def handler(event):
                try:
                    chat_title = getattr(event.chat, 'title', 'Unknown')
                    logger.info(f"New message received from {chat_title}")
                    events = await self.process_message(event.message, chat_title)
                    if events:
                        self.save_events(events)
                    # Always save processed messages after each new message
                    self.save_processed_messages()
                    if events:
                        logger.info(f"Processed new message with {len(events)} events")
                except Exception as e:
                    logger.error(f"Error handling new message: {e}")
            
            logger.info("Real-time monitoring started. Press Ctrl+C to stop.")
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Error in monitoring: {e}")
    
    async def run_web_server(self):
        """Run the aiohttp web server."""
        runner = web.AppRunner(self.web_app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        logger.info("Started web server on port 8080")
        # Keep it running by returning a long-running awaitable
        await asyncio.Event().wait()

        async def start_reminder_background(self, app):
            # Start the reminder task in the background
            asyncio.create_task(self.reminder_task())

    async def run(self, scan_recent: bool = True, monitor: bool = True):
        """Main run method"""
        try:
            logger.info("Starting Telegram Calendar Sync...")
            
            # Validate configuration
            if not API_ID or not API_HASH or not PHONE_NUMBER:
                raise ValueError("Missing required Telegram credentials")
            
            if not TELEGRAM_GROUPS or not any(g.strip() for g in TELEGRAM_GROUPS):
                raise ValueError("No Telegram groups configured")
            
            if not OPENAI_API_KEY and not ANTHROPIC_API_KEY and not GROQ_API_KEY:
                raise ValueError("No LLM API key provided (OpenAI, Anthropic, or Groq required)")
            
            # Connect to Telegram with silent authentication
            try:
                await self.client.connect()
                
                if not await self.client.is_user_authorized():
                    if not TELEGRAM_CODE:
                        raise ValueError("TELEGRAM_CODE environment variable required for first-time auth")
                        
                    try:
                        # First request the code, which will be sent to the user's phone
                        sent_code = await self.client.send_code_request(PHONE_NUMBER)
                        # Then sign in with the code and the returned phone_code_hash
                        await self.client.sign_in(
                            phone=PHONE_NUMBER,
                            code=TELEGRAM_CODE,
                            phone_code_hash=sent_code.phone_code_hash
                        )
                    except SessionPasswordNeededError:
                        if not TELEGRAM_2FA_PASSWORD:
                            raise ValueError("2FA is enabled but TELEGRAM_2FA_PASSWORD not provided")
                        await self.client.sign_in(password=TELEGRAM_2FA_PASSWORD)
                
                logger.info("Connected to Telegram successfully")
                
                if scan_recent:
                    logger.info("Scanning recent messages...")
                    await self.scan_all_groups()
                
                if monitor:
                    logger.info("Starting real-time monitoring...")
                    await self.start_monitoring()
                
            except Exception as e:
                logger.error(f"Telegram authentication error: {e}")
                raise
            
        except Exception as e:
            logger.error(f"Error in main run: {e}")
            raise

async def main():
    """Main entry point"""
    sync = TelegramCalendarSync()
    
    telegram_task = sync.run(scan_recent=True, monitor=True)
    web_server_task = sync.run_web_server()
    # Start reminder background task
    sync.web_app.on_startup.append(sync.start_reminder_background)
    await asyncio.gather(telegram_task, web_server_task)

if __name__ == "__main__":
    logger.info("Telegram Calendar Sync with LLM Event Extraction")
    logger.info("Configuration:")
    logger.info(f"  Groups: {len([g for g in TELEGRAM_GROUPS if g.strip()])}")
    
    # Determine active LLM provider
    llm_provider = "None"
    if OPENAI_API_KEY:
        llm_provider = "OpenAI"
    elif GROQ_API_KEY:
        llm_provider = "Groq"
    elif ANTHROPIC_API_KEY:
        llm_provider = "Anthropic"
    
    logger.info(f"  LLM Provider: {llm_provider}")
    logger.info(f"  Output: {CALENDAR_OUTPUT_PATH}")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        exit(1)