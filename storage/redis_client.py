"""
Redis client for live conversation context and streaming state.
"""
import os
import json
import redis
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Global Redis client (lazy loaded)
_redis_client: Optional[redis.Redis] = None

def get_redis_client() -> Optional[redis.Redis]:
    """Get or create Redis client."""
    global _redis_client
    
    if _redis_client is not None:
        try:
            _redis_client.ping()
            return _redis_client
        except:
            _redis_client = None
    
    try:
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=5
        )
        _redis_client.ping()
        print(f"✅ Redis connected: {REDIS_HOST}:{REDIS_PORT}")
        return _redis_client
    except Exception as e:
        print(f"⚠️  Redis not available: {e}")
        return None

def is_redis_available() -> bool:
    """Check if Redis is available."""
    client = get_redis_client()
    return client is not None

# Conversation context keys
def get_context_key(session_id: str) -> str:
    """Get Redis key for conversation context."""
    return f"context:{session_id}"

def get_streaming_state_key(session_id: str) -> str:
    """Get Redis key for streaming state."""
    return f"stream:{session_id}"

def get_partial_transcript_key(session_id: str) -> str:
    """Get Redis key for partial transcript."""
    return f"partial:{session_id}"

def save_conversation_context(session_id: str, messages: List[Dict[str, Any]], ttl: int = 3600) -> bool:
    """
    Save conversation context to Redis.
    
    Args:
        session_id: Session identifier
        messages: List of message dicts
        ttl: Time to live in seconds (default 1 hour)
    
    Returns:
        True if successful
    """
    client = get_redis_client()
    if not client:
        return False
    
    try:
        key = get_context_key(session_id)
        # Store as JSON
        client.setex(key, ttl, json.dumps(messages))
        return True
    except Exception as e:
        print(f"⚠️  Error saving context to Redis: {e}")
        return False

def get_conversation_context(session_id: str) -> List[Dict[str, Any]]:
    """
    Get conversation context from Redis.
    
    Args:
        session_id: Session identifier
    
    Returns:
        List of message dicts
    """
    client = get_redis_client()
    if not client:
        return []
    
    try:
        key = get_context_key(session_id)
        data = client.get(key)
        if data:
            return json.loads(data)
        return []
    except Exception as e:
        print(f"⚠️  Error getting context from Redis: {e}")
        return []

def append_to_context(session_id: str, message: Dict[str, Any], max_messages: int = 20) -> bool:
    """
    Append message to conversation context.
    
    Args:
        session_id: Session identifier
        message: Message dict to append
        max_messages: Maximum messages to keep (FIFO)
    
    Returns:
        True if successful
    """
    messages = get_conversation_context(session_id)
    messages.append(message)
    
    # Keep only last N messages
    if len(messages) > max_messages:
        messages = messages[-max_messages:]
    
    return save_conversation_context(session_id, messages)

def set_streaming_state(session_id: str, state: Dict[str, Any], ttl: int = 300) -> bool:
    """
    Set streaming state (for active voice calls).
    
    Args:
        session_id: Session identifier
        state: State dict
        ttl: Time to live in seconds (default 5 minutes)
    
    Returns:
        True if successful
    """
    client = get_redis_client()
    if not client:
        return False
    
    try:
        key = get_streaming_state_key(session_id)
        client.setex(key, ttl, json.dumps(state))
        return True
    except Exception as e:
        print(f"⚠️  Error setting streaming state: {e}")
        return False

def get_streaming_state(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Get streaming state.
    
    Args:
        session_id: Session identifier
    
    Returns:
        State dict or None
    """
    client = get_redis_client()
    if not client:
        return None
    
    try:
        key = get_streaming_state_key(session_id)
        data = client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        print(f"⚠️  Error getting streaming state: {e}")
        return None

def set_partial_transcript(session_id: str, text: str, ttl: int = 60) -> bool:
    """
    Set partial transcript (for streaming STT).
    
    Args:
        session_id: Session identifier
        text: Partial transcript text
        ttl: Time to live in seconds (default 1 minute)
    
    Returns:
        True if successful
    """
    client = get_redis_client()
    if not client:
        return False
    
    try:
        key = get_partial_transcript_key(session_id)
        client.setex(key, ttl, text)
        return True
    except Exception as e:
        print(f"⚠️  Error setting partial transcript: {e}")
        return False

def get_partial_transcript(session_id: str) -> Optional[str]:
    """
    Get partial transcript.
    
    Args:
        session_id: Session identifier
    
    Returns:
        Partial transcript text or None
    """
    client = get_redis_client()
    if not client:
        return None
    
    try:
        key = get_partial_transcript_key(session_id)
        return client.get(key)
    except Exception as e:
        print(f"⚠️  Error getting partial transcript: {e}")
        return None

def clear_session(session_id: str) -> bool:
    """
    Clear all session data from Redis.
    
    Args:
        session_id: Session identifier
    
    Returns:
        True if successful
    """
    client = get_redis_client()
    if not client:
        return False
    
    try:
        keys = [
            get_context_key(session_id),
            get_streaming_state_key(session_id),
            get_partial_transcript_key(session_id)
        ]
        client.delete(*keys)
        return True
    except Exception as e:
        print(f"⚠️  Error clearing session: {e}")
        return False
