import os
import time
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# Import the new tools
from llm.tools import APPOINTMENT_TOOLS, check_availability_tool, book_appointment_tool

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

_MODEL = "gpt-4o-mini"

def build_messages(user_message: str, conversation_history: List[Dict[str, Any]] = None, language: str = "en") -> List[Dict[str, str]]:
    """
    Build messages list preserving your original Language Logic.
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Base System Prompt with Booking Rules
    SYSTEM_PROMPT = f"""You are Jarvis, a friendly AI assistant and scheduling pro.
    Current Time: {current_time}
    
    YOUR ROLES:
    1. Chat Friend: Be warm and conversational.
    2. Scheduler: Help users book appointments.
    
    SCHEDULING RULES:
    - To book, you MUST collect: Name, Email, and Desired Time.
    - ALWAYS check availability first using 'check_availability'.
    - If free, use 'book_appointment' to confirm.
    
    GENERAL RULES:
    - Keep responses concise (2-4 sentences max for voice).
    """
    
    # Your Original Language Logic
    lang_instruction = ""
    if language == "ur":
        has_urdu_script = any(c in "ءآأؤإئابتثجحخدذرزسشصضطظعغفقكلمنهوىي" for c in user_message)
        if has_urdu_script:
            lang_instruction = "\nImportant: User is speaking in Urdu (اردو). Respond ONLY in Urdu script."
        else:
            lang_instruction = "\nImportant: User is speaking in Roman Urdu. Respond ONLY in Roman Urdu."
    elif language == "hi":
        has_hindi_script = any(c in "अआइईउऊएऐओऔऋकखगघचछजझटठडढणतथदधनपफबभमयरलवशषसह" for c in user_message)
        if has_hindi_script:
            lang_instruction = "\nImportant: User is speaking in Hindi. Respond ONLY in Hindi Devanagari."
        else:
            lang_instruction = "\nImportant: User is speaking in Roman Hindi. Respond ONLY in Roman Hindi."
    
    messages = [{
        "role": "system",
        "content": SYSTEM_PROMPT + lang_instruction
    }]
    
    # Add History
    if conversation_history:
        for msg in conversation_history[-6:]:
            role = "assistant" if msg.get("role") in ["model", "assistant"] else "user"
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
    
    messages.append({"role": "user", "content": user_message})
    return messages

def generate_response(
    user_message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    language: str = "en",
    session_id: str = "unknown"  # <--- NEW: We need this for the DB
) -> str:
    
    if not API_KEY: return "Error: OPENAI_API_KEY missing."
    client = OpenAI(api_key=API_KEY)
    
    messages = build_messages(user_message, conversation_history, language)
    
    try:
        # 1. First Call (Determine Intent)
        response = client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=APPOINTMENT_TOOLS,
            tool_choice="auto",
            temperature=0.7
        )
        
        msg = response.choices[0].message
        
        # 2. Check if AI wants to use a Tool
        if msg.tool_calls:
            # Add the "thought" to history so the AI remembers it asked for a tool
            messages.append(msg)
            
            for tool in msg.tool_calls:
                func_name = tool.function.name
                args = tool.function.arguments
                result = "{}"
                
                # Execute the tool
                if func_name == "check_availability":
                    result = check_availability_tool(args)
                elif func_name == "book_appointment":
                    result = book_appointment_tool(args, session_id)
                
                # Add result to history
                messages.append({
                    "tool_call_id": tool.id,
                    "role": "tool",
                    "name": func_name,
                    "content": result
                })
            
            # 3. Second Call (Generate Final Answer based on Tool Result)
            final_resp = client.chat.completions.create(
                model=_MODEL,
                messages=messages
            )
            return final_resp.choices[0].message.content

        # Normal Chat Response
        return msg.content

    except Exception as e:
        print(f"LLM Error: {e}")
        return "Sorry, I'm having trouble connecting to my brain right now."