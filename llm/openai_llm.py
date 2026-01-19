"""
OpenAI LLM integration with conversation context management.
Uses Redis for live context, PostgreSQL for long-term history.
Cost-effective model: gpt-4o-mini (very cheap, good quality)
"""
import os
import sys
import time
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

try:
    from openai import OpenAI
except ImportError:
    print("⚠️  OpenAI package not installed. Run: pip install openai")
    OpenAI = None

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    print("⚠️  Missing OPENAI_API_KEY. Set it in .env file.")

# Cost-effective model configuration
_MODEL = "gpt-4o-mini"  # Very cheap, excellent quality (~$0.15 per 1M input tokens, ~$0.60 per 1M output tokens)
_FALLBACK_MODEL = "gpt-3.5-turbo"  # Even cheaper fallback (~$0.50 per 1M input, ~$1.50 per 1M output)

_last_request_time = 0
_min_request_interval = 0.5  # Minimum seconds between requests (OpenAI is faster)

def build_messages(user_message: str, conversation_history: List[Dict[str, Any]] = None, language: str = "en") -> List[Dict[str, str]]:
    """
    Build messages list for OpenAI API with conversation history and language support.
    """
    SYSTEM_PROMPT = """You are Jarvis, a friendly AI assistant and chatbot. Your role is to be helpful, conversational, and act as both an assistant and a friend.

Guidelines:
- Keep responses concise and to the point (2-4 sentences maximum)
- Be friendly, warm, and conversational
- Avoid very long explanations unless specifically asked
- Use natural, casual language
- Be helpful and informative but brief
- Show personality and be engaging
- If asked about complex topics, provide a concise summary rather than detailed explanations

Remember: Short, friendly, and helpful responses work best for voice conversations."""
    
    # Language-specific instruction
    lang_instruction = ""
    if language == "ur":
        has_urdu_script = any(c in "ءآأؤإئابتثجحخدذرزسشصضطظعغفقكلمنهوىي" for c in user_message)
        if has_urdu_script:
            lang_instruction = "\nImportant: User is speaking in Urdu (اردو). Respond ONLY in Urdu using Urdu script (Arabic script). Example: آپ کا کیا حال ہے؟"
        else:
            lang_instruction = "\nImportant: User is speaking in Roman Urdu (Urdu written in English letters like 'kia haal hai'). Respond ONLY in Roman Urdu (Urdu words written in Latin script). Example: 'Main theek hoon, aap ka kya haal hai?'"
    elif language == "hi":
        has_hindi_script = any(c in "अआइईउऊएऐओऔऋकखगघचछजझटठडढणतथदधनपफबभमयरलवशषसह" for c in user_message)
        if has_hindi_script:
            lang_instruction = "\nImportant: User is speaking in Hindi (हिंदी). Respond ONLY in Hindi using Devanagari script. Example: आप कैसे हैं?"
        else:
            lang_instruction = "\nImportant: User is speaking in Roman Hindi (Hindi written in English letters). Respond ONLY in Roman Hindi (Hindi words written in Latin script). Example: 'Main theek hoon, aap kaise hain?'"
    else:
        lang_instruction = "\nImportant: Respond ONLY in English. Use English for all responses."
    
    # Build messages list
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT + lang_instruction
        }
    ]
    
    # Add conversation history (last 6 messages for context)
    if conversation_history:
        for msg in conversation_history[-6:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                # Map roles to OpenAI format
                if role == "model" or role == "assistant":
                    messages.append({"role": "assistant", "content": content})
                else:
                    messages.append({"role": "user", "content": content})
    
    # Add current user message
    messages.append({
        "role": "user",
        "content": user_message
    })
    
    return messages

def generate_response(
    user_message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    language: str = "en"
) -> str:
    """
    Generate response using OpenAI API with conversation context.
    
    Args:
        user_message: User's message
        conversation_history: List of previous messages (from Redis)
        language: Detected language code
    
    Returns:
        AI response text
    """
    global _last_request_time
    
    if not API_KEY:
        return "Sorry, AI service is not configured. Please set OPENAI_API_KEY."
    
    if not OpenAI:
        return "Sorry, OpenAI package is not installed. Please run: pip install openai"
    
    # Rate limiting
    current_time = time.time()
    time_since_last = current_time - _last_request_time
    if time_since_last < _min_request_interval:
        time.sleep(_min_request_interval - time_since_last)
    
    # Build messages
    messages = build_messages(user_message, conversation_history, language)
    
    # Initialize OpenAI client
    client = OpenAI(api_key=API_KEY)
    
    # Try primary model first
    models_to_try = [_MODEL, _FALLBACK_MODEL]
    
    for model_name in models_to_try:
        try:
            _last_request_time = time.time()
            
            # Make API call
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=150,  # Keep responses short for voice
                temperature=0.7,  # Balanced creativity
                timeout=30
            )
            
            # Extract response text
            if response.choices and len(response.choices) > 0:
                choice = response.choices[0]
                if choice.message and choice.message.content:
                    text = choice.message.content.strip()
                    if text:
                        return text
            
            raise RuntimeError("Empty response from OpenAI API")
            
        except Exception as e:
            error_msg = str(e)
            
            # Check for rate limit or quota errors
            if "rate limit" in error_msg.lower() or "quota" in error_msg.lower():
                if model_name == _MODEL and len(models_to_try) > 1:
                    print(f"⚠️  Rate limit on {model_name}. Trying fallback...")
                    continue
                raise RuntimeError(f"OpenAI API rate limit/quota exceeded: {error_msg}")
            
            # Check for authentication errors
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                raise RuntimeError(f"OpenAI API authentication failed. Please check your API key.")
            
            # Check for model errors
            if "404" in error_msg or "not found" in error_msg.lower():
                if model_name == _MODEL and len(models_to_try) > 1:
                    print(f"⚠️  Model {model_name} not available. Trying fallback...")
                    continue
                raise RuntimeError(f"OpenAI model '{model_name}' not found or unavailable.")
            
            # For other errors, try fallback if available
            if model_name == _MODEL and len(models_to_try) > 1:
                print(f"⚠️  Error with {model_name}: {error_msg}. Trying fallback...")
                continue
            
            raise RuntimeError(f"OpenAI API error: {error_msg}")
    
    raise RuntimeError("All OpenAI models failed")
