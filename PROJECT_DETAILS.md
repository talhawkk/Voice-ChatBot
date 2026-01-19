# Voice ChatBot Project - Professional Architecture

## Project Overview

This is a **Voice ChatBot Application** built with Flask and WebSocket support for real-time voice interactions. The application integrates multiple AI services for speech-to-text, text-to-speech, and language model responses.

**Architecture**: Clean, modular, production-ready structure with separated concerns.

## Architecture

### Core Components

1. **Backend (Flask + SocketIO)**
   - Main application: `app.py`
   - WebSocket handlers integrated in main app
   - REST API endpoints for chat and voice messages

2. **AI Services**
   - **STT (Speech-to-Text)**: Deepgram (streaming, real-time, multi-language)
   - **TTS (Text-to-Speech)**: Edge TTS (free, multi-language)
   - **LLM (Language Model)**: OpenAI GPT-4o-mini (cost-effective)

3. **Storage**
   - **Redis**: Live conversation context (session management)
   - **PostgreSQL**: Long-term message history
   - **AWS S3**: Optional audio file storage

4. **Frontend**
   - Modern web UI with voice recording
   - Real-time WebSocket communication
   - Voice call mode with streaming audio

## Key Features

- ✅ Real-time voice conversations via WebSocket
- ✅ Deepgram Voice Agent (full-duplex voice calls)
- ✅ Multi-language support (English, Urdu, Hindi)
- ✅ Text chat mode
- ✅ Voice message recording and playback
- ✅ Conversation history persistence
- ✅ Auto language detection
- ✅ Streaming transcription (partial + final)

## Project Structure

```
4_Voice-ChatBot/
├── app.py                    # Main Flask application (entry point)
├── database.py               # PostgreSQL operations
├── requirements.txt          # Python dependencies
├── PROJECT_DETAILS.md       # This file
│
├── agents/                   # Voice agents
│   ├── voice_agent.py        # Legacy voice agent (STT + LLM + TTS)
│   └── deepgram_voice_agent.py  # Deepgram Voice Agent (full-duplex)
│
├── config/                   # Configuration
│   └── settings.py
│
├── stt/                      # Speech-to-Text services
│   └── deepgram_stt.py       # Deepgram streaming STT
│
├── tts/                      # Text-to-Speech services
│   └── edge_tts.py          # Edge TTS (free, multi-language)
│
├── llm/                      # Language Model services
│   ├── openai_llm.py        # OpenAI LLM (gpt-4o-mini)
│   └── gemini_llm.py        # Gemini LLM (optional)
│
├── storage/                  # Storage services
│   ├── redis_client.py      # Redis operations
│   └── s3.py                # AWS S3 operations
│
├── utils/                    # Shared utilities
│   └── language.py          # Language detection utility
│
├── templates/                # Frontend templates
│   └── index.html           # Main UI
│
└── static/                   # Static files
    └── recorder.js          # Frontend JavaScript (voice recording & WebSocket)
```

## API Endpoints

### REST Endpoints
- `GET /` - Main page
- `GET /conversation-history` - Get conversation history
- `POST /chat` - Send text message
- `POST /voice-message` - Send voice message (record & send)
- `POST /ai-response` - Generate AI response for voice message
- `POST /voice-call-chunk` - Process voice call audio chunk (legacy mode)
- `POST /transcribe/<message_id>` - Get transcription for message
- `GET /audio/<message_id>` - Get audio file by message ID

### WebSocket Events
- `connect` - Client connection
- `disconnect` - Client disconnection
- `start_call` - Start voice call session (Voice Agent or Legacy mode)
- `end_call` - End voice call session
- `pcm_audio_chunk` - Send PCM audio chunk (Voice Agent mode)
- `audio_chunk` - Send audio chunk (Legacy mode)
- `transcription` - Receive transcription updates
- `response_text` - Receive LLM response text
- `audio_response` - Receive TTS audio chunks
- `agent_status` - Receive agent status updates (thinking/speaking/listening)
- `agent_done` - Agent finished speaking

## Configuration

### Required Environment Variables (.env)

```env
# OpenAI API (for LLM)
OPENAI_API_KEY=your_openai_api_key

# Deepgram API (for STT and Voice Agent)
DEEPGRAM_API_KEY=your_deepgram_api_key

# Database (PostgreSQL - optional)
DATABASE_URL=postgresql://user:pass@localhost:5432/voicechatbot
# OR individual settings:
DB_HOST=localhost
DB_PORT=5432
DB_NAME=voicechatbot
DB_USER=postgres
DB_PASSWORD=your_password

# Redis (optional but recommended for session management)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# AWS S3 (optional, for audio file storage)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_S3_BUCKET=your_bucket_name
AWS_REGION=us-east-1

# Flask
FLASK_DEBUG=True
FLASK_SECRET_KEY=your_secret_key
```

## Dependencies

All dependencies are listed in `requirements.txt`:

### Core
- Flask 3.1.2
- flask-socketio >= 5.3.0
- python-socketio >= 5.10.0
- python-engineio >= 4.7.0
- Werkzeug 3.1.5

### AI Services
- deepgram-sdk >= 3.2.0 (STT & Voice Agent)
- edge-tts >= 6.1.0 (TTS)
- openai >= 1.0.0 (LLM)

### Storage
- redis >= 5.0.0 (Session management)
- psycopg2-binary >= 2.9.0 (PostgreSQL)
- boto3 >= 1.28.0 (AWS S3)

### Audio Processing
- pydub >= 0.25.1 (Audio conversion)
- soundfile == 0.13.1 (Audio I/O)
- websockets >= 12.0 (Deepgram Voice Agent WebSocket)

### Utilities
- python-dotenv == 1.0.1 (Environment variables)
- requests == 2.32.5 (HTTP client)
- numpy == 2.4.1 (Numerical operations)

### Type Hints
- pydantic == 2.12.5
- pydantic_core == 2.41.5
- typing_extensions == 4.15.0

## Installation

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   - Create `.env` file in project root
   - Set required API keys (OPENAI_API_KEY, DEEPGRAM_API_KEY)
   - Configure optional services (Redis, PostgreSQL, S3)

3. **Start Redis** (optional but recommended):
   ```bash
   redis-server
   ```

4. **Start PostgreSQL** (optional):
   - Ensure PostgreSQL is running
   - Database will be auto-created on first run

5. **Run the application**:
   ```bash
   python app.py
   ```

6. **Access the application**:
   - Open browser to `http://localhost:5000`

## Voice Agent Modes

### 1. Deepgram Voice Agent (Recommended)
- Full-duplex voice conversations
- Single WebSocket connection
- Real-time STT + LLM + TTS
- Low latency, smooth experience
- Requires: DEEPGRAM_API_KEY

### 2. Legacy Mode (Fallback)
- Separate STT, LLM, TTS calls
- Uses Deepgram STT + OpenAI LLM + Edge TTS
- Works if Voice Agent unavailable
- Slightly higher latency

## Development Notes

- The application uses **threading** mode for SocketIO (compatible with all platforms)
- Deepgram streaming STT requires API key for real-time transcription
- Edge TTS is free and doesn't require API key
- OpenAI GPT-4o-mini is used for cost-effectiveness (~$0.15 per 1M input tokens)
- Voice Agent mode uses WebSocket for low-latency streaming
- Voice message mode uses HTTP POST for record-and-send workflow
- All services (Redis, PostgreSQL, S3) are optional - app works without them

## Known Issues & Notes

1. **Python 3.13+ Compatibility**: `pydub` has compatibility issues with Python 3.13+ (audioop module was removed).
   - **Impact**: Only affects audio conversion operations
   - **Workaround**: Main functionality works fine, audio conversion may need alternative
   - **Solution**: Use Python 3.11 or 3.12, or wait for pydub update

2. **Optional Services**: Database, Redis, and S3 are optional - app works without them

3. **FFmpeg**: Included in project for audio processing (Windows)

4. **Audio Format**: Voice Agent requires LINEAR16 PCM at 48kHz input, 24kHz output

## Future Improvements

- [ ] Add more language support
- [ ] Implement conversation export
- [ ] Add user authentication
- [ ] Improve error handling and retry logic
- [ ] Add audio quality settings
- [ ] Implement rate limiting
- [ ] Add monitoring and logging
- [ ] Support for more LLM providers

## Support

For issues or questions, check:
- Project documentation
- API documentation for Deepgram, OpenAI, Edge TTS
- Flask-SocketIO documentation

---

**Last Updated**: January 2025
**Status**: ✅ Production-ready, clean architecture, all features working
**Version**: 2.0 (Refactored & Professional)
