import asyncio
import os
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
import aiohttp

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
    def __init__(self):
        self.client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
        self.llm_extractor = LLMEventExtractor()
        self.processed_messages = set()
        self.events_file = CALENDAR_OUTPUT_PATH
        self.processed_messages_file = PROCESSED_MESSAGES_PATH
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.events_file), exist_ok=True)
        self.load_processed_messages()

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

    async def process_message(self, message, group_name: str) -> List[CalendarEvent]:
        """Process a single message and extract calendar events using LLM"""
        events = []
        
        # Skip if already processed
        message_key = f"{group_name}_{message.id}"
        if message_key in self.processed_messages:
            logger.debug(f"Skipping already processed message {message_key}")
            return events
        
        text = message.text or ""
        if len(text.strip()) < 3:  # Only skip empty or trivial messages
            logger.debug(f"Skipping very short message from {group_name} (length: {len(text.strip())})")
            return events
        
        logger.debug(f"Processing message from {group_name}:\n{text}\n")
        
        try:
            # Use message date as reference point for relative dates
            # Message date from Telegram is always in UTC
            message_date = message.date.replace(tzinfo=timezone.utc)
            reference_date = message_date.strftime('%Y-%m-%d')
            logger.debug(f"Using message date as reference: {reference_date}")
            
            # Extract events using LLM with message date as reference
            logger.debug(f"Sending to LLM for extraction: {text[:500]}...")
            extracted_events = await self.llm_extractor.extract_events(text, reference_date)
            logger.debug(f"LLM returned {len(extracted_events)} potential events")
            
            # Add metadata to events
            for event in extracted_events:
                event.source_group = group_name
                event.source_message_id = message.id
                if not event.description:
                    event.description = text[:500]  # Use original text as description
                
                # Compare timezone-aware datetimes
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
    
    # Run with both scanning and monitoring
    await sync.run(scan_recent=True, monitor=True)

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