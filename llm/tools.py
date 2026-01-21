import json
from datetime import datetime, timedelta
from services.calendar_service import GoogleCalendarService
from database import get_connection

# Initialize Service
calendar_service = GoogleCalendarService()

# --- 1. Tool Schemas ---
APPOINTMENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Check if a specific date and time slot is available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_time": {"type": "string", "description": "ISO 8601 date time (e.g. 2023-10-27T14:00:00)"}
                },
                "required": ["date_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a meeting after confirming availability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_name": {"type": "string"},
                    "user_email": {"type": "string"},
                    "start_time": {"type": "string"},
                    "meeting_type": {"type": "string", "enum": ["online", "phone", "in-person"]},
                    "notes": {"type": "string"}
                },
                "required": ["user_name", "user_email", "start_time"]
            }
        }
    }
]

# --- 2. Tool Logic ---

def check_availability_tool(args_json):
    try:
        args = json.loads(args_json)
        dt = datetime.fromisoformat(args.get("date_time"))
        
        # ✅ Default to 1 hour (60 minutes) instead of 30
        duration_minutes = args.get("duration_minutes", 60)
        
        is_free = calendar_service.is_slot_available(dt, duration_minutes)
        
        # ✅ Handle None (error case)
        if is_free is None:
            return json.dumps({
                "status": "error", 
                "msg": "Could not check calendar availability. Please try again or contact support."
            })
        
        if is_free:
            return json.dumps({
                "status": "available", 
                "msg": f"The slot at {dt} for {duration_minutes} minutes is free."
            })
        else:
            return json.dumps({
                "status": "busy", 
                "msg": f"Sorry, {dt} is already booked. Please choose another time."
            })
    except Exception as e:
        print(f"[Tool Error] Availability Check: {e}")
        import traceback
        traceback.print_exc()
        return json.dumps({"status": "error", "msg": str(e)})

def book_appointment_tool(args_json, session_id):
    try:
        args = json.loads(args_json)
        name = args.get("user_name")
        email = args.get("user_email")
        start_str = args.get("start_time")
        meeting_type = args.get("meeting_type", "online")
        
        start_dt = datetime.fromisoformat(start_str)
        end_dt = start_dt + timedelta(minutes=30) 
        
        # 1. Create on Google Calendar (CRITICAL STEP)
        event = calendar_service.create_event(
            summary=f"Meeting: {name}",
            start_time=start_dt,
            end_time=end_dt,
            attendee_email=email,
            description=f"Type: {meeting_type}\nSession: {session_id}",
            meet_link=(meeting_type == "online")
        )
        
        if not event:
            return json.dumps({"status": "error", "msg": "Google API failed to create event."})

        # 2. Save to Database (OPTIONAL STEP - Don't fail if this breaks)
        try:
            conn = get_connection()
            if conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO appointments (session_id, user_email, user_name, start_time, end_time, meeting_type, google_event_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (session_id, email, name, start_dt, end_dt, meeting_type, event['id']))
                conn.commit()
                conn.close()
        except Exception as db_e:
            # Log error but DO NOT fail the booking
            print(f"⚠️ Database Error (Booking still succeeded): {db_e}")

        # Return Success to LLM because Calendar worked!
        return json.dumps({
            "status": "success", 
            "msg": "Appointment confirmed. Invitation sent.",
            "link": event.get('htmlLink')
        })

    except Exception as e:
        print(f"[Tool Error] Booking Failed: {e}")
        return json.dumps({"status": "error", "msg": str(e)})