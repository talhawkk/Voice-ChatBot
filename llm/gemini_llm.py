"""
Gemini Flash LLM integration with conversation context management.
Uses Redis for live context, PostgreSQL for long-term history.
"""
import os
import sys
import time
import requests
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("⚠️  Missing GEMINI_API_KEY. Set it in .env or environment variables.")

# Model configuration - Updated for 2025
# Gemini 1.5 models are deprecated, using Gemini 2.0
_PRIMARY_MODEL = "gemini-2.0-flash-exp"
_FALLBACK_MODELS = []  # No fallbacks - if primary fails, show clear error

_last_request_time = 0
_min_request_interval = 1.5  # Minimum seconds between requests

def build_prompt(user_message: str, conversation_history: List[Dict[str, Any]] = None, language: str = "en") -> str:
    """
    Build prompt from user message and conversation history with language support.
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
    
    if conversation_history is None or len(conversation_history) == 0:
        return SYSTEM_PROMPT + lang_instruction + "\n\nUser: " + user_message
    else:
        prompt_parts = [SYSTEM_PROMPT + lang_instruction + "\n\nConversation:"]
        
        # Add conversation history (last 6 messages for context)
        for msg in conversation_history[-6:]:
            role = "User" if msg.get("role") == "user" else "Jarvis"
            content = msg.get("content", "")
            if content:
                prompt_parts.append(f"{role}: {content}")
        
        prompt_parts.append(f"User: {user_message}\nJarvis:")
        return "\n".join(prompt_parts)

def generate_response(
    user_message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    language: str = "en"
) -> str:
    """
    Generate response using Gemini Flash with conversation context.
    
    Args:
        user_message: User's message
        conversation_history: List of previous messages (from Redis)
        language: Detected language code
    
    Returns:
        AI response text
    """
    global _last_request_time
    
    if not API_KEY:
        return "Sorry, AI service is not configured. Please set GEMINI_API_KEY."
    
    # Rate limiting
    current_time = time.time()
    time_since_last = current_time - _last_request_time
    if time_since_last < _min_request_interval:
        time.sleep(_min_request_interval - time_since_last)
    
    # Build prompt
    prompt = build_prompt(user_message, conversation_history, language)
    
    # Try models
    models_to_try = [_PRIMARY_MODEL] + _FALLBACK_MODELS
    
    for model_name in models_to_try:
        try:
            _last_request_time = time.time()
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 429:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", "Quota exceeded")
                raise RuntimeError(f"Gemini API quota exceeded: {error_msg}. Please check your API key quota or billing.")
            
            if response.status_code >= 400:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                
                if response.status_code == 404:
                    raise RuntimeError(f"Model '{model_name}' not found. Gemini 1.5 models are deprecated. Please use gemini-2.0-flash-exp or check available models at https://ai.google.dev/api/models")
                elif response.status_code == 403:
                    raise RuntimeError(f"Access denied for model '{model_name}'. Please check your API key permissions.")
                else:
                    raise RuntimeError(f"Gemini API error ({response.status_code}): {error_msg}")
            
            result = response.json()
            
            if "candidates" in result and len(result["candidates"]) > 0:
                candidate = result["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    parts = candidate["content"]["parts"]
                    if len(parts) > 0 and "text" in parts[0]:
                        text = parts[0]["text"].strip()
                        if text:
                            return text
            
            raise RuntimeError("Empty response from Gemini API")
            
        except requests.exceptions.RequestException as e:
            if model_name == _PRIMARY_MODEL and models_to_try.index(model_name) < len(models_to_try) - 1:
                print(f"⚠️  Primary model failed: {e}. Trying fallback...")
                continue
            raise RuntimeError(f"Gemini API failed: {e}")
        except Exception as e:
            if model_name == _PRIMARY_MODEL and models_to_try.index(model_name) < len(models_to_try) - 1:
                print(f"⚠️  Primary model error: {e}. Trying fallback...")
                continue
            raise RuntimeError(f"Gemini API error: {e}")
    
    raise RuntimeError("All models failed")
