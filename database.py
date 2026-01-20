"""
PostgreSQL database operations for storing messages and conversation history.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from dotenv import load_dotenv
from typing import List, Dict, Optional

load_dotenv()

# Database connection configuration
# Support both DATABASE_URL and individual connection parameters
DATABASE_URL = os.getenv("DATABASE_URL")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "voicechatbot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

def get_connection():
    """Get PostgreSQL database connection."""
    try:
        if DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL)
        else:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
        return conn
    except psycopg2.Error as e:
        print(f"[WARNING] Database connection error: {e}")
        return None

def init_db():
    """Initialize database tables if they don't exist."""
    conn = get_connection()
    if not conn:
        print("[WARNING] Could not connect to database. Database operations will be skipped.")
        return False
    
    try:
        cur = conn.cursor()
        
        # Create messages table
        # Note: If table exists with old schema, we'll need to alter it
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL,
                message_type VARCHAR(20) NOT NULL,
                content TEXT,
                audio_url TEXT,
                message_id VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id VARCHAR(255),
                user_email VARCHAR(255) NOT NULL,
                user_name VARCHAR(255),
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP NOT NULL,
                meeting_type VARCHAR(50),
                google_event_id VARCHAR(255),
                status VARCHAR(50) DEFAULT 'confirmed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Alter table if message_id column is too small (fix for existing databases)
        try:
            cur.execute("""
                ALTER TABLE messages 
                ALTER COLUMN message_id TYPE VARCHAR(255)
            """)
            conn.commit()
        except psycopg2.Error:
            # Column might already be correct size or doesn't exist yet
            conn.rollback()
            pass
        
        # Create indexes for better query performance
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_id ON messages(session_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_message_id ON messages(message_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at ON messages(created_at)
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("[OK] Database initialized successfully")
        return True
        
    except psycopg2.Error as e:
        print(f"[WARNING] Database initialization error: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def save_message(
    session_id: str,
    role: str,
    message_type: str,
    message_id: str,
    content: Optional[str] = None,
    audio_url: Optional[str] = None
) -> bool:
    """
    Save a message to the database.
    
    Args:
        session_id: User session identifier
        role: 'user' or 'model'
        message_type: 'text' or 'voice'
        message_id: Unique message identifier
        content: Message text content or transcription
        audio_url: S3 URL for voice messages
    
    Returns:
        True if successful, False otherwise
    """
    conn = get_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        
        # Use ON CONFLICT to handle duplicate message_id gracefully
        cur.execute("""
            INSERT INTO messages (session_id, role, message_type, content, audio_url, message_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (message_id) 
            DO UPDATE SET 
                content = EXCLUDED.content,
                audio_url = EXCLUDED.audio_url
        """, (session_id, role, message_type, content, audio_url, message_id))
        
        conn.commit()
        cur.close()
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"[WARNING] Error saving message to database: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def get_conversation_history(session_id: str, limit: int = 10) -> List[Dict]:
    """
    Get conversation history for a session from database.
    
    Args:
        session_id: User session identifier
        limit: Maximum number of recent messages to retrieve
    
    Returns:
        List of message dictionaries in the format expected by build_prompt
    """
    conn = get_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Use DESC order and LIMIT, then reverse for most recent messages (faster with index)
        cur.execute("""
            SELECT role, message_type as type, content, audio_url, message_id, created_at as timestamp
            FROM messages
            WHERE session_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (session_id, limit))
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        # Convert to list of dictionaries and reverse to get chronological order
        messages = []
        for row in reversed(rows):  # Reverse to get chronological order (oldest first)
            msg = {
                "role": row["role"],
                "type": row["type"],
                "content": row["content"] or "",
                "audio_url": row["audio_url"] or "",
                "message_id": row["message_id"],
                "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None
            }
            messages.append(msg)
        
        return messages
        
    except psycopg2.Error as e:
        print(f"[WARNING] Error retrieving conversation history: {e}")
        if conn:
            conn.close()
        return []

def get_message_by_id(message_id: str) -> Optional[Dict]:
    """
    Get a specific message by message_id.
    
    Args:
        message_id: Unique message identifier
    
    Returns:
        Message dictionary or None if not found
    """
    conn = get_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT role, message_type as type, content, audio_url, message_id, created_at as timestamp
            FROM messages
            WHERE message_id = %s
        """, (message_id,))
        
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return {
                "role": row["role"],
                "type": row["type"],
                "content": row["content"] or "",
                "audio_url": row["audio_url"] or "",
                "message_id": row["message_id"],
                "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None
            }
        
        return None
        
    except psycopg2.Error as e:
        print(f"[WARNING] Error retrieving message: {e}")
        if conn:
            conn.close()
        return None
