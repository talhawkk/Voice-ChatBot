"""
Application configuration and settings.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Flask settings
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", os.urandom(24))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "True").lower() == "true"

# Directories
BASE_DIR = Path(__file__).parent.parent
AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = AUDIO_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
RESPONSES_DIR = AUDIO_DIR / "responses"
RESPONSES_DIR.mkdir(exist_ok=True)
MODELS_DIR = BASE_DIR / "models" / "vosk"

# FFmpeg
_local_ffmpeg = BASE_DIR / "ffmpeg-8.0.1-essentials_build" / "bin" / "ffmpeg.exe"
FFMPEG_BIN = str(_local_ffmpeg) if _local_ffmpeg.exists() else os.getenv("FFMPEG_BIN", "ffmpeg")

# Database (PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "voicechatbot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# AWS S3
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# System prompt
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
