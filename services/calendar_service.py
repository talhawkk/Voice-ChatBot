import os
import json
import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

class GoogleCalendarService:
    def __init__(self):
        self.creds = None
        
        # ✅ Priority 1: Try environment variable (for Heroku/deployed)
        token_json_str = os.getenv("GOOGLE_TOKEN_JSON")
        if token_json_str:
            try:
                token_data = json.loads(token_json_str)
                self.creds = Credentials.from_authorized_user_info(token_data, SCOPES)
                print("[OK] Loaded Google Calendar token from GOOGLE_TOKEN_JSON environment variable")
            except Exception as e:
                print(f"[WARNING] Error loading token from GOOGLE_TOKEN_JSON: {e}")
        
        # ✅ Priority 2: Try token.json file (for local development)
        if not self.creds and os.path.exists('token.json'):
            try:
                self.creds = Credentials.from_authorized_user_file('token.json', SCOPES)
                print("[OK] Loaded Google Calendar token from token.json file")
            except Exception as e:
                print(f"[WARNING] Error loading token.json: {e}")
            
        # Refresh logic if token expires
        if self.creds and self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                print("[OK] Token refreshed successfully")
            except Exception as e:
                print(f"[WARNING] Token refresh failed: {e}")
                self.creds = None

    def get_service(self):
        if not self.creds or not self.creds.valid:
            print("[WARNING] Calendar Credentials invalid. Set GOOGLE_TOKEN_JSON or run generate_token.py")
            return None
        return build('calendar', 'v3', credentials=self.creds)

    def is_slot_available(self, start_time: datetime.datetime, duration_minutes: int = 60):
        """Checks if a time slot is free (Admin Calendar)."""
        service = self.get_service()
        if not service:
            print("[WARNING] Calendar service not available - cannot check availability")
            return None  # Return None to indicate error, not False

        end_time = start_time + datetime.timedelta(minutes=duration_minutes)
        
        # Check 'freebusy' status
        body = {
            "timeMin": start_time.isoformat() + 'Z',
            "timeMax": end_time.isoformat() + 'Z',
            "timeZone": "UTC",
            "items": [{"id": CALENDAR_ID}]
        }
        
        try:
            events_result = service.freebusy().query(body=body).execute()
            calendars = events_result.get('calendars', {})
            busy_list = calendars.get(CALENDAR_ID, {}).get('busy', [])
            
            # ✅ Add debugging info
            if busy_list:
                print(f"[INFO] Calendar has {len(busy_list)} busy event(s) in this slot:")
                for event in busy_list:
                    print(f"   - {event.get('start')} to {event.get('end')}")
            else:
                print(f"[OK] Slot is free: {start_time} to {end_time} ({duration_minutes} minutes)")
            
            return len(busy_list) == 0
        except Exception as e:
            print(f"[ERROR] Calendar Check Error: {e}")
            import traceback
            traceback.print_exc()
            return None  # Return None to indicate error

    def create_event(self, summary, start_time, end_time, attendee_email, description=None, meet_link=False):
        """Creates an event on Admin calendar and invites the User."""
        service = self.get_service()
        if not service: return None

        event = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'},
            'end': {'dateTime': end_time.isoformat(), 'timeZone': 'UTC'},
            'attendees': [{'email': attendee_email}],
            'reminders': {'useDefault': True},
        }

        # Add Google Meet link if requested
        if meet_link:
            event['conferenceData'] = {
                'createRequest': {
                    'requestId': f"req-{int(datetime.datetime.now().timestamp())}",
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            }

        try:
            # sendUpdates='all' sends the email invitation to the user
            event = service.events().insert(
                calendarId=CALENDAR_ID, 
                body=event, 
                conferenceDataVersion=1,
                sendUpdates='all' 
            ).execute()
            return event
        except HttpError as error:
            print(f"Event Creation Error: {error}")
            return None