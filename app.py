"""
Refactored Voice Agent Application with WebSocket streaming.
Integrates Deepgram STT, Edge TTS, OpenAI LLM (gpt-4o-mini), Redis, and PostgreSQL.
Real-time streaming voice calls with WebSocket support.
"""
from flask import Flask, render_template, request, jsonify, session, send_file
from flask_socketio import SocketIO, emit
from pathlib import Path
import os
import uuid
from datetime import datetime
import base64
import tempfile

# Import services
from database import init_db, save_message, get_conversation_history, get_message_by_id
from storage.redis_client import is_redis_available, get_redis_client
from agents.voice_agent import VoiceAgent
from agents.deepgram_voice_agent import (
    DeepgramVoiceAgent,
    create_voice_agent,
    is_voice_agent_available
)
from storage.redis_client import clear_session
from stt.deepgram_stt import speech_to_text
from llm.openai_llm import generate_response
from tts.edge_tts import text_to_speech_bytes_sync

# Import S3 functions (optional)
from storage import upload_to_s3, is_s3_configured

# Configuration
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "True").lower() == "true"

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Initialize SocketIO
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=False,
    engineio_logger=False
)

# Active voice call sessions
active_agents = {}
# Track which mode each session uses: 'voice_agent' or 'legacy'
session_modes = {}

# Service availability flags
_db_available = False
_s3_available = False

def initialize_services():
    """Initialize all services and check availability."""
    global _db_available, _s3_available
    
    # Initialize database
    _db_available = init_db()
    
    # Check S3
    _s3_available = is_s3_configured()
    
    # Check Redis
    redis_available = is_redis_available()
    
    print("\n🚀 Starting Voice Agent Server...")
    print("   - WebSocket: Enabled")
    print("   - STT: Deepgram (streaming, real-time)")
    print("   - TTS: Edge TTS (free)")
    print("   - LLM: OpenAI (gpt-4o-mini)\n")
    
    if _db_available:
        print("✅ Database: Connected")
    else:
        print("⚠️  Database: Not available (optional)")
    
    if redis_available:
        print("✅ Redis: Connected")
    else:
        print("⚠️  Redis: Not available (optional)")
    
    if _s3_available:
        print("✅ S3: Configured")
    else:
        print("⚠️  S3: Not configured (optional)")

# Initialize on startup
initialize_services()

@app.route('/')
def index():
    """Serve main page."""
    return render_template('index.html')

@app.route('/conversation-history')
def conversation_history():
    """Get conversation history for current session."""
    try:
        session_id = session.get('session_id')
        if not session_id:
            session_id = f"session_{uuid.uuid4().hex[:12]}"
            session['session_id'] = session_id
        
        history = get_conversation_history(session_id)
        return jsonify(history)
    except Exception as e:
        print(f"[WARNING] Error getting history: {e}")
        return jsonify([])

@app.route('/chat', methods=['POST'])
def chat():
    """Handle text chat message."""
    try:
        data = request.json
        # Support both 'text' and 'message' fields for compatibility
        text = data.get('text', '').strip() or data.get('message', '').strip()
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        # Get or create session ID
        session_id = session.get('session_id')
        if not session_id:
            session_id = f"session_{uuid.uuid4().hex[:12]}"
            session['session_id'] = session_id
        
        # Generate response
        from storage.redis_client import get_conversation_context, append_to_context
        context = get_conversation_context(session_id)
        response_text = generate_response(text, context, "en")
        
        # Save to context
        append_to_context(session_id, {
            'role': 'user',
            'content': text,
            'timestamp': datetime.now().isoformat()
        })
        append_to_context(session_id, {
            'role': 'model',
            'content': response_text,
            'timestamp': datetime.now().isoformat()
        })
        
        # Save to database
        if _db_available:
            try:
                user_msg_id = str(uuid.uuid4())[:36]
                assistant_msg_id = str(uuid.uuid4())[:36]
                save_message(session_id, 'user', 'text', user_msg_id, text, None)
                save_message(session_id, 'assistant', 'text', assistant_msg_id, response_text, None)
            except:
                pass
        
        return jsonify({
            'response': response_text,
            'jarvis': response_text,  # Frontend expects 'jarvis' field
            'text': response_text,    # Also include 'text' for compatibility
            'message_id': str(uuid.uuid4())
        })
        
    except Exception as e:
        print(f"[ERROR] Chat error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/voice-message', methods=['POST'])
def voice_message():
    """Handle voice message (record and send)."""
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file'}), 400
        
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'error': 'No audio file selected'}), 400
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name
        
        try:
            # Transcribe using Deepgram
            print(f"[Voice Message] Transcribing audio from: {tmp_path}")
            transcription, detected_lang = speech_to_text(tmp_path, "en")
            print(f"[Voice Message] Transcription result: '{transcription}', lang: {detected_lang}")
            
            if not transcription or transcription.strip() == '':
                print(f"[Voice Message] Empty transcription - audio may be too short or silent")
                return jsonify({'error': 'Could not transcribe audio - try speaking louder or longer'}), 400
            
            # Get or create session ID
            session_id = session.get('session_id')
            if not session_id:
                session_id = f"session_{uuid.uuid4().hex[:12]}"
                session['session_id'] = session_id
            
            # Generate response
            from storage.redis_client import get_conversation_context, append_to_context
            context = get_conversation_context(session_id)
            response_text = generate_response(transcription, context, detected_lang)
            
            # Generate TTS audio
            audio_bytes = text_to_speech_bytes_sync(response_text, detected_lang)
            
            # Save audio files
            message_id = str(uuid.uuid4())
            timestamp = datetime.now().strftime("%Y%m%d_%H-%M-%S")
            
            # Save user audio
            uploads_dir = Path("audio/uploads")
            uploads_dir.mkdir(parents=True, exist_ok=True)
            user_audio_path = uploads_dir / f"{timestamp}_{message_id}.webm"
            with open(tmp_path, 'rb') as src, open(user_audio_path, 'wb') as dst:
                dst.write(src.read())
            
            # Save response audio
            responses_dir = Path("audio/responses")
            responses_dir.mkdir(parents=True, exist_ok=True)
            response_audio_path = responses_dir / f"{timestamp}_{message_id}.mp3"
            with open(response_audio_path, 'wb') as f:
                f.write(audio_bytes)
            
            # Upload to S3 if configured
            user_audio_url = None
            response_audio_url = None
            if _s3_available:
                try:
                    user_audio_url = upload_to_s3(str(user_audio_path), f"uploads/{user_audio_path.name}")
                    response_audio_url = upload_to_s3(str(response_audio_path), f"responses/{response_audio_path.name}")
                except:
                    pass
            
            # Save to context
            append_to_context(session_id, {
                'role': 'user',
                'content': transcription,
                'timestamp': datetime.now().isoformat()
            })
            append_to_context(session_id, {
                'role': 'model',
                'content': response_text,
                'timestamp': datetime.now().isoformat()
            })
            
            # Save to database
            if _db_available:
                try:
                    # Truncate message_id if too long (database constraint)
                    db_message_id = message_id[:36] if len(message_id) > 36 else message_id
                    save_message(session_id, 'user', 'voice', db_message_id, transcription, str(user_audio_path))
                    save_message(session_id, 'assistant', 'voice', f"{db_message_id}_response", response_text, str(response_audio_path))
                except Exception as e:
                    print(f"[WARNING] Error saving message to database: {e}")
            
            # Return response with all needed fields for frontend
            return jsonify({
                'transcription': transcription,
                'response': response_text,
                'text': response_text,  # For compatibility
                'jarvis': response_text,  # For compatibility
                'audio_url': f'/audio/{message_id}',
                'response_audio_url': f'/audio/{message_id}',  # AI response audio
                'message_id': message_id,
                'language': detected_lang
            })
            
        finally:
            # Clean up temp file
            try:
                Path(tmp_path).unlink()
            except:
                pass
        
    except Exception as e:
        print(f"[ERROR] Voice message error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/ai-response', methods=['POST'])
def ai_response():
    """Handle AI response generation for voice messages (separate endpoint for frontend compatibility)."""
    try:
        data = request.json
        transcription = data.get('transcription', '').strip()
        user_message_id = data.get('message_id', '')
        language = data.get('language', 'en')
        
        if not transcription:
            return jsonify({'error': 'No transcription provided'}), 400
        
        # Get or create session ID
        session_id = session.get('session_id')
        if not session_id:
            session_id = f"session_{uuid.uuid4().hex[:12]}"
            session['session_id'] = session_id
        
        # Generate response
        from storage.redis_client import get_conversation_context, append_to_context
        context = get_conversation_context(session_id)
        response_text = generate_response(transcription, context, language)
        
        # Generate TTS audio
        audio_bytes = text_to_speech_bytes_sync(response_text, language)
        
        # Save response audio
        message_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d_%H-%M-%S")
        responses_dir = Path("audio/responses")
        responses_dir.mkdir(parents=True, exist_ok=True)
        response_audio_path = responses_dir / f"{timestamp}_{message_id}.mp3"
        with open(response_audio_path, 'wb') as f:
            f.write(audio_bytes)
        
        # Save to context
        append_to_context(session_id, {
            'role': 'user',
            'content': transcription,
            'timestamp': datetime.now().isoformat()
        })
        append_to_context(session_id, {
            'role': 'model',
            'content': response_text,
            'timestamp': datetime.now().isoformat()
        })
        
        # Save to database
        if _db_available:
            try:
                db_message_id = message_id[:36] if len(message_id) > 36 else message_id
                save_message(session_id, 'assistant', 'voice', db_message_id, response_text, str(response_audio_path))
            except Exception as e:
                print(f"[WARNING] Error saving message to database: {e}")
        
        return jsonify({
            'text': response_text,
            'jarvis': response_text,
            'audio_url': f'/audio/{message_id}',
            'message_id': message_id
        })
        
    except Exception as e:
        print(f"[ERROR] AI response error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/voice-call-chunk', methods=['POST'])
def voice_call_chunk():
    """Handle voice call audio chunk (for VAD-based processing)."""
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file'}), 400
        
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'error': 'No audio file selected'}), 400
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name
        
        try:
            # Transcribe using Deepgram
            transcription, detected_lang = speech_to_text(tmp_path, "en")
            
            if not transcription:
                return jsonify({'transcription': '', 'language': detected_lang})
            
            # Get or create session ID
            session_id = session.get('session_id')
            if not session_id:
                session_id = f"session_{uuid.uuid4().hex[:12]}"
                session['session_id'] = session_id
            
            # Generate response
            from storage.redis_client import get_conversation_context, append_to_context
            context = get_conversation_context(session_id)
            response_text = generate_response(transcription, context, detected_lang)
            
            # Generate TTS audio
            audio_bytes = text_to_speech_bytes_sync(response_text, detected_lang)
            
            # Save response audio
            message_id = str(uuid.uuid4())
            timestamp = datetime.now().strftime("%Y%m%d_%H-%M-%S")
            responses_dir = Path("audio/responses")
            responses_dir.mkdir(parents=True, exist_ok=True)
            response_audio_path = responses_dir / f"{timestamp}_{message_id}.mp3"
            with open(response_audio_path, 'wb') as f:
                f.write(audio_bytes)
            
            # Save to context
            append_to_context(session_id, {
                'role': 'user',
                'content': transcription,
                'timestamp': datetime.now().isoformat()
            })
            append_to_context(session_id, {
                'role': 'model',
                'content': response_text,
                'timestamp': datetime.now().isoformat()
            })
            
            return jsonify({
                'transcription': transcription,
                'text': response_text,  # Frontend expects 'text' field
                'response': response_text,
                'audio_url': f'/audio/{message_id}',
                'message_id': message_id,
                'language': detected_lang
            })
            
        finally:
            # Clean up temp file
            try:
                Path(tmp_path).unlink()
            except:
                pass
        
    except Exception as e:
        print(f"[ERROR] Voice call chunk error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'transcription': ''}), 500

@app.route('/audio/<message_id>')
def get_audio(message_id):
    """Get audio file by message ID."""
    # Search for audio file
    audio_dirs = [
        Path("audio/responses"),
        Path("audio/uploads")
    ]
    
    for audio_dir in audio_dirs:
        matches = list(audio_dir.glob(f"*_{message_id}.*"))
        if matches:
            mimetype = "audio/webm" if matches[0].suffix == ".webm" else "audio/mpeg"
            return send_file(matches[0], mimetype=mimetype)
    
    return jsonify({"error": "Audio file not found"}), 404

@app.route('/transcribe/<message_id>', methods=['POST'])
def transcribe_message(message_id):
    """Get transcription for a message by message_id."""
    try:
        # Get message from database
        message = get_message_by_id(message_id)
        
        if not message:
            return jsonify({'error': 'Message not found'}), 404
        
        # If message already has content (transcription), return it
        if message.get('content') and message.get('content').strip():
            return jsonify({'transcription': message['content']})
        
        # If message has audio_url, try to transcribe it
        audio_url = message.get('audio_url')
        if audio_url:
            # Check if it's a local file path
            if os.path.exists(audio_url):
                transcription, _ = speech_to_text(audio_url, "en")
                if transcription:
                    return jsonify({'transcription': transcription})
        
        return jsonify({'error': 'Could not transcribe audio'}), 400
        
    except Exception as e:
        print(f"[ERROR] Transcription error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# WebSocket handlers
@socketio.on('connect')
def handle_connect(auth):
    """Handle WebSocket connection."""
    print(f"[OK] WebSocket client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection. Cleanup any active voice agents."""
    # Find and cleanup sessions for this socket
    sessions_to_remove = []
    for sid, agent in list(active_agents.items()):
        # Try to identify sessions that belong to disconnecting client
        if hasattr(agent, 'socketio_sid') and agent.socketio_sid == request.sid:
            sessions_to_remove.append(sid)
    
    for sid in sessions_to_remove:
        if sid in active_agents:
            agent = active_agents.pop(sid)
            mode = session_modes.pop(sid, 'legacy')
            
            try:
                if mode == 'voice_agent' and hasattr(agent, 'stop'):
                    agent.stop()
                elif hasattr(agent, 'cleanup'):
                    agent.cleanup()
            except Exception as e:
                print(f"[WARNING] Error during cleanup: {e}")
    
    print(f"[CLOSED] WebSocket client disconnected: {request.sid}")

@socketio.on('start_call')
def handle_start_call(data):
    """
    Start voice call session.
    Uses Deepgram Voice Agent API with pydub for audio conversion.
    Falls back to Legacy mode if Voice Agent unavailable.
    """
    session_id = data.get('session_id')
    use_voice_agent = data.get('use_voice_agent', True)  # Default to Voice Agent
    
    if not session_id:
        session_id = f"session_{uuid.uuid4().hex[:12]}"
    
    # Clean up any existing session
    if session_id in active_agents:
        old_agent = active_agents.pop(session_id)
        old_mode = session_modes.pop(session_id, 'legacy')
        if old_mode == 'voice_agent' and hasattr(old_agent, 'stop'):
            old_agent.stop()
        elif hasattr(old_agent, 'cleanup'):
            old_agent.cleanup()
    
    print(f"[Voice Call] Starting session: {session_id}")
    
    # Try Deepgram Voice Agent first (if requested and available)
    if use_voice_agent and is_voice_agent_available():
        print(f"[Voice Call] Using Deepgram Voice Agent mode")
        
        # Create callbacks for Voice Agent events
        def on_transcription(text, is_final):
            socketio.emit('transcription', {
                'text': text,
                'is_final': is_final,
                'session_id': session_id
            })
        
        def on_response_text(text):
            socketio.emit('response_text', {
                'text': text,
                'session_id': session_id
            })
        
        def on_audio_response(audio_bytes):
            # Send linear16 PCM audio to client
            # Client needs to decode this (24kHz, 16-bit, mono)
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            socketio.emit('audio_response', {
                'audio': audio_b64,
                'format': 'linear16',
                'sample_rate': 24000,
                'session_id': session_id
            })
        
        def on_agent_thinking():
            socketio.emit('agent_thinking', {'session_id': session_id})
        
        def on_agent_speaking():
            socketio.emit('agent_speaking', {'session_id': session_id})
        
        def on_agent_done():
            socketio.emit('agent_done', {'session_id': session_id})
        
        def on_error(error_msg):
            socketio.emit('error', {
                'message': error_msg,
                'session_id': session_id
            })
        
        # Create Voice Agent with callbacks
        agent = create_voice_agent(
            session_id=session_id,
            callbacks={
                'on_transcription': on_transcription,
                'on_response_text': on_response_text,
                'on_audio_response': on_audio_response,
                'on_agent_thinking': on_agent_thinking,
                'on_agent_speaking': on_agent_speaking,
                'on_agent_done': on_agent_done,
                'on_error': on_error,
            },
            language='en'
        )
        
        if agent and agent.start():
            active_agents[session_id] = agent
            session_modes[session_id] = 'voice_agent'
            
            emit('call_started', {
                'session_id': session_id,
                'mode': 'voice_agent',
                'audio_format': 'linear16',
                'output_sample_rate': 24000
            })
            print(f"[OK] Voice Agent call started: {session_id}")
            return
        else:
            print(f"[WARNING] Voice Agent failed to start, falling back to legacy mode")
    
    # Fallback: Use Legacy mode (Deepgram STT + OpenAI LLM + Edge TTS)
    print(f"[Voice Call] Using Legacy mode (STT + LLM + TTS)")
    agent = VoiceAgent(session_id)
    agent.set_socketio(socketio)
    active_agents[session_id] = agent
    session_modes[session_id] = 'legacy'
    
    # Start voice agent (batch mode - always succeeds)
    if agent.start_streaming_stt():
        emit('call_started', {
            'session_id': session_id,
            'mode': 'legacy'
        })
        print(f"[OK] Legacy voice call started: {session_id}")
    else:
        emit('error', {'message': 'Failed to start voice agent.'})
        print(f"[ERROR] Failed to start voice agent for session: {session_id}")

@socketio.on('end_call')
def handle_end_call(data):
    """End voice call."""
    session_id = data.get('session_id')
    if session_id in active_agents:
        agent = active_agents.pop(session_id)
        mode = session_modes.pop(session_id, 'legacy')
        
        if mode == 'voice_agent' and hasattr(agent, 'stop'):
            agent.stop()
        elif hasattr(agent, 'cleanup'):
            agent.cleanup()
    
    emit('call_ended', {'session_id': session_id})
    print(f"[OK] Voice call ended: {session_id}")

@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    """Handle streaming audio chunk from browser (legacy WebM format)."""
    session_id = data.get('session_id')
    audio_b64 = data.get('audio')
    
    if not session_id or not audio_b64:
        return  # Silently ignore invalid data
    
    if session_id not in active_agents:
        return  # No active call
    
    try:
        # Decode audio
        audio_bytes = base64.b64decode(audio_b64)
        
        # Get agent and mode
        agent = active_agents[session_id]
        mode = session_modes.get(session_id, 'legacy')
        
        if mode == 'voice_agent' and isinstance(agent, DeepgramVoiceAgent):
            # Voice Agent mode: Send audio directly to Deepgram Voice Agent
            agent.send_audio(audio_bytes)
        else:
            # Legacy mode: Send audio to Deepgram STT via VoiceAgent
            # Don't check is_connected here - let process_audio_chunk handle it
            agent.process_audio_chunk(audio_bytes)
        
    except Exception as e:
        # Don't emit error for every audio chunk failure - too noisy
        print(f"[ERROR] Audio chunk error: {e}")

# Track warning state to avoid spam
_legacy_pcm_warned = set()

@socketio.on('pcm_audio_chunk')
def handle_pcm_audio_chunk(data):
    """Handle raw PCM audio chunk from browser (Linear16 format at 48kHz)."""
    session_id = data.get('session_id')
    audio_b64 = data.get('audio')
    
    if not session_id or not audio_b64:
        return  # Silently ignore invalid data
    
    if session_id not in active_agents:
        return  # No active call
    
    try:
        # Decode raw PCM audio (already Linear16 @ 48kHz from browser)
        pcm_bytes = base64.b64decode(audio_b64)
        
        # Get agent and mode
        agent = active_agents[session_id]
        mode = session_modes.get(session_id, 'legacy')
        
        if mode == 'voice_agent' and isinstance(agent, DeepgramVoiceAgent):
            # Voice Agent mode: Send raw PCM directly to Deepgram Voice Agent
            agent.send_raw_pcm(pcm_bytes)
        else:
            # Legacy mode doesn't support PCM - warn once per session
            if session_id not in _legacy_pcm_warned:
                print(f"[WARNING] Session {session_id} in legacy mode - PCM audio not supported, use Record button instead")
                _legacy_pcm_warned.add(session_id)
        
    except Exception as e:
        print(f"[ERROR] PCM audio chunk error: {e}")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=FLASK_DEBUG)
