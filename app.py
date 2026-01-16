from flask import Flask, render_template, request, jsonify, session, send_file, redirect
from ai.stt import speech_to_text
from ai.llm import ask_gemini
from ai.tts import speak, text_to_speech_file
import os
import subprocess
import tempfile
from pathlib import Path
import uuid
from datetime import datetime
from database import init_db, save_message, get_conversation_history, get_message_by_id
from storage import upload_to_s3, is_s3_configured

# Check for local ffmpeg first, then environment variable, then system PATH
_local_ffmpeg = Path(__file__).parent / "ffmpeg-8.0.1-essentials_build" / "bin" / "ffmpeg.exe"
if _local_ffmpeg.exists():
    FFMPEG_BIN = str(_local_ffmpeg)
else:
    FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

AUDIO_DIR = Path("audio")
AUDIO_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = AUDIO_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
RESPONSES_DIR = AUDIO_DIR / "responses"
RESPONSES_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Required for sessions

# Store conversation history in memory (fallback if database unavailable)
conversations = {}

# Initialize database on startup
_db_available = False
_s3_available = False

def initialize_services():
    """Initialize database and check S3 availability."""
    global _db_available, _s3_available
    _db_available = init_db()
    _s3_available = is_s3_configured()
    if _db_available:
        print("✅ Database connection successful")
    else:
        print("⚠️  Database not available. Using in-memory storage.")
    if _s3_available:
        print("✅ S3 configuration detected")
    else:
        print("⚠️  S3 not configured. Using local storage.")

# System prompt for AI
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

def build_prompt(user_message: str, conversation_history: list = None) -> str:
    """Build a prompt from user message and conversation history."""
    if conversation_history is None or len(conversation_history) == 0:
        # First message - include system prompt
        return SYSTEM_PROMPT + "\n\nUser: " + user_message
    else:
        # Build conversation context
        prompt_parts = [SYSTEM_PROMPT + "\n\nConversation:"]
        
        # Add conversation history (last 6 messages for context)
        for msg in conversation_history[-6:]:
            role = "User" if msg.get("role") == "user" else "Jarvis"
            content = msg.get("content", "")
            if content:
                prompt_parts.append(f"{role}: {content}")
        
        # Add current user message
        prompt_parts.append(f"User: {user_message}\nJarvis:")
        return "\n".join(prompt_parts)


def check_ffmpeg():
    """Check if ffmpeg is available."""
    try:
        subprocess.run(
            [FFMPEG_BIN, "-version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def convert_to_wav(uploaded_file, target_path: Path) -> None:
    """Convert the uploaded audio to 16 kHz mono PCM WAV using ffmpeg."""
    # If uploaded_file is a file path (string), use it directly
    if isinstance(uploaded_file, (str, Path)):
        input_path = str(uploaded_file)
    else:
        # Otherwise, it's a FileStorage object, save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp_in:
            uploaded_file.save(tmp_in.name)
            input_path = tmp_in.name

    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i",
        input_path,
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(target_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def save_audio_file(uploaded_file, directory: Path) -> tuple[Path, str]:
    """Save uploaded audio file and return path and message_id."""
    message_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H-%M-%S")
    filename = f"{timestamp}_{message_id}.webm"
    file_path = directory / filename
    uploaded_file.save(str(file_path))
    return file_path, message_id

def convert_webm_to_mp3(input_path: Path, output_path: Path) -> None:
    """Convert WebM audio to MP3 using ffmpeg."""
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(input_path),
        "-acodec",
        "libmp3lame",
        "-ar",
        "22050",
        "-ac",
        "1",
        "-q:a",
        "2",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/conversation-history", methods=["GET"])
def get_conversation_history_route():
    """Get conversation history for current session."""
    session_id = session.get("session_id")
    if not session_id:
        return jsonify({"messages": []})
    
    # Get conversation history from database or memory (limit to 20 for faster loading)
    if _db_available:
        history = get_conversation_history(session_id, limit=20)
        # Convert S3 URLs to proxy URLs for frontend
        for msg in history:
            if msg.get("audio_url") and (msg["audio_url"].startswith("http://") or msg["audio_url"].startswith("https://")):
                # It's an S3 URL, convert to proxy URL
                msg["audio_url"] = f"/audio/{msg.get('message_id', '')}"
    else:
        history = conversations.get(session_id, [])
    
    return jsonify({"messages": history})


@app.route("/voice", methods=["POST"])
def voice():
    audio = request.files.get("audio")
    if not audio:
        return jsonify({"error": "No audio provided"}), 400

    # Get or create session ID for conversation history
    session_id = session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        session["session_id"] = session_id
        conversations[session_id] = []
    
    # Get conversation history from database or memory
    if _db_available:
        conversation_history = get_conversation_history(session_id, limit=10)
    else:
        conversation_history = conversations.get(session_id, [])
    
    wav_path = AUDIO_DIR / "input.wav"

    try:
        # Convert audio
        convert_to_wav(audio, wav_path)
        
        # Transcribe speech
        user_text = speech_to_text(str(wav_path))
        
        if not user_text or not user_text.strip():
            return jsonify({"error": "Could not transcribe audio. Please try again."}), 400
        
        # Build prompt and get AI response
        prompt = build_prompt(user_text, conversation_history)
        ai_response = ask_gemini(prompt)
        
        # Generate message IDs
        user_message_id = str(uuid.uuid4())
        ai_message_id = str(uuid.uuid4())
        
        # Save to database if available
        if _db_available:
            save_message(
                session_id=session_id,
                role="user",
                message_type="text",
                message_id=user_message_id,
                content=user_text
            )
            save_message(
                session_id=session_id,
                role="model",
                message_type="text",
                message_id=ai_message_id,
                content=ai_response
            )
        
        # Update conversation history (also keep in memory as fallback)
        conversation_history.append({"role": "user", "content": user_text})
        conversation_history.append({"role": "model", "content": ai_response})
        
        # Keep only last 10 messages to prevent context from growing too large
        if len(conversation_history) > 10:
            conversation_history = conversation_history[-10:]
        
        conversations[session_id] = conversation_history
        
        # Speak response asynchronously (doesn't block response)
        try:
            speak(ai_response)
        except Exception as tts_error:
            print(f"⚠️  TTS Warning: {tts_error}")
        
    except FileNotFoundError:
        return jsonify({"error": f"FFmpeg not found. Please install FFmpeg and add it to your PATH, or set FFMPEG_BIN environment variable. Current value: {FFMPEG_BIN}"}), 500
    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Audio conversion failed: {e}. Ensure ffmpeg is installed and working correctly."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"user": user_text, "jarvis": ai_response})


@app.route("/chat", methods=["POST"])
def chat():
    """Handle text chat messages."""
    data = request.get_json()
    user_message = data.get("message", "").strip()
    
    if not user_message:
        return jsonify({"error": "No message provided"}), 400
    
    # Get or create session ID for conversation history
    session_id = session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        session["session_id"] = session_id
        conversations[session_id] = []
    
    # Get conversation history from database or memory
    if _db_available:
        conversation_history = get_conversation_history(session_id, limit=10)
    else:
        conversation_history = conversations.get(session_id, [])
    
    try:
        # Build prompt and get AI response
        prompt = build_prompt(user_message, conversation_history)
        ai_response = ask_gemini(prompt)
        
        # Generate message IDs
        user_message_id = str(uuid.uuid4())
        ai_message_id = str(uuid.uuid4())
        
        # Save to database if available
        if _db_available:
            save_message(
                session_id=session_id,
                role="user",
                message_type="text",
                message_id=user_message_id,
                content=user_message
            )
            save_message(
                session_id=session_id,
                role="model",
                message_type="text",
                message_id=ai_message_id,
                content=ai_response
            )
        
        # Also update in-memory history (fallback)
        conversation_history.append({
            "role": "user",
            "type": "text",
            "content": user_message,
            "timestamp": datetime.now().isoformat()
        })
        conversation_history.append({
            "role": "model",
            "type": "text",
            "content": ai_response,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last 10 messages
        if len(conversation_history) > 10:
            conversation_history = conversation_history[-10:]
        
        conversations[session_id] = conversation_history
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    return jsonify({"user": user_message, "jarvis": ai_response})

@app.route("/voice-message", methods=["POST"])
def voice_message():
    """Handle voice message uploads."""
    audio = request.files.get("audio")
    if not audio:
        return jsonify({"error": "No audio provided"}), 400
    
    # Get or create session ID
    session_id = session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        session["session_id"] = session_id
        conversations[session_id] = []
    
    conversation_history = conversations.get(session_id, [])
    
    try:
        # Save audio file locally first
        file_path, message_id = save_audio_file(audio, UPLOADS_DIR)
        
        # Convert to WAV for transcription
        wav_path = AUDIO_DIR / f"temp_{message_id}.wav"
        
        # Need to reset file pointer before converting
        audio.seek(0)
        convert_to_wav(audio, wav_path)
        
        # Transcribe speech
        transcription = speech_to_text(str(wav_path))
        
        # Clean up temp WAV file
        if wav_path.exists():
            wav_path.unlink()
        
        # Upload to S3 if configured
        s3_url_stored = None
        audio_url = f"/audio/{message_id}"  # Always use /audio/<message_id> for frontend
        if _s3_available:
            s3_url_stored = upload_to_s3(file_path, key=f"uploads/{file_path.name}")
            if not s3_url_stored:
                print(f"⚠️  S3 upload failed for {message_id}, using local storage")
        
        # Save to database if available (store S3 URL in DB, but return /audio/<message_id> to frontend)
        if _db_available:
            save_message(
                session_id=session_id,
                role="user",
                message_type="voice",
                message_id=message_id,
                content=transcription or "",
                audio_url=s3_url_stored or audio_url
            )
        
        # Also update in-memory history (fallback)
        conversation_history.append({
            "role": "user",
            "type": "voice",
            "content": transcription or "",
            "audio_url": audio_url,
            "message_id": message_id,
            "timestamp": datetime.now().isoformat()
        })
        conversations[session_id] = conversation_history
        
        return jsonify({
            "audio_url": audio_url,
            "transcription": transcription or "",
            "message_id": message_id
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/audio/<message_id>")
def serve_audio(message_id):
    """Serve audio files from S3 or local storage."""
    # First, try to get from database
    if _db_available:
        message = get_message_by_id(message_id)
        if message and message.get("audio_url"):
            audio_url = message["audio_url"]
            # If it's an S3 URL, serve through proxy with CORS headers
            if audio_url.startswith("http://") or audio_url.startswith("https://"):
                # Import requests for fetching S3 file
                try:
                    import requests
                    from flask import Response
                    # Fetch from S3
                    response = requests.get(audio_url, stream=True)
                    if response.status_code == 200:
                        # Determine content type
                        content_type = response.headers.get('Content-Type', 'audio/mpeg')
                        # Return with CORS headers
                        return Response(
                            response.content,
                            mimetype=content_type,
                            headers={
                                'Access-Control-Allow-Origin': '*',
                                'Access-Control-Allow-Methods': 'GET',
                                'Access-Control-Allow-Headers': 'Content-Type'
                            }
                        )
                except ImportError:
                    # If requests not available, redirect
                    return redirect(audio_url, code=302)
                except Exception as e:
                    print(f"⚠️  Error fetching from S3: {e}")
                    # Fall through to local storage
    
    # Fallback to local storage
    import glob
    # Try uploads first (user messages)
    audio_file = UPLOADS_DIR / f"*_{message_id}.webm"
    matches = glob.glob(str(audio_file))
    
    if not matches:
        # Try responses (AI messages)
        audio_file = RESPONSES_DIR / f"*_{message_id}.mp3"
        matches = glob.glob(str(audio_file))
    
    if not matches:
        # Try WAV format too
        audio_file = RESPONSES_DIR / f"*_{message_id}.wav"
        matches = glob.glob(str(audio_file))
    
    if matches:
        mimetype = "audio/webm" if matches[0].endswith(".webm") else "audio/mpeg" if matches[0].endswith(".mp3") else "audio/wav"
        return send_file(matches[0], mimetype=mimetype)
    
    return jsonify({"error": "Audio file not found"}), 404

@app.route("/transcribe/<message_id>", methods=["POST"])
def transcribe_message(message_id):
    """Transcribe an existing voice message."""
    session_id = session.get("session_id")
    if not session_id:
        return jsonify({"error": "No session found"}), 400
    
    # Try to get message from database first
    message = None
    if _db_available:
        message = get_message_by_id(message_id)
    
    # Fallback to in-memory conversation history
    if not message:
        conversation_history = conversations.get(session_id, [])
        for msg in conversation_history:
            if msg.get("message_id") == message_id and msg.get("type") == "voice":
                message = msg
                break
    
    if not message:
        return jsonify({"error": "Message not found"}), 404
    
    # If already transcribed, return it
    if message.get("content"):
        return jsonify({"transcription": message["content"]})
    
    try:
        import glob
        # Try uploads first (user messages)
        audio_file = UPLOADS_DIR / f"*_{message_id}.webm"
        matches = glob.glob(str(audio_file))
        
        if not matches:
            # Try responses (AI messages)
            audio_file = RESPONSES_DIR / f"*_{message_id}.mp3"
            matches = glob.glob(str(audio_file))
            
            if not matches:
                # Try WAV format too
                audio_file = RESPONSES_DIR / f"*_{message_id}.wav"
                matches = glob.glob(str(audio_file))
        
        if not matches:
            return jsonify({"error": "Audio file not found"}), 404
        
        # Convert to WAV for transcription
        wav_path = AUDIO_DIR / f"temp_transcribe_{message_id}.wav"
        convert_to_wav(None, wav_path)  # We need to read from the webm file
        
        # Convert webm to wav using ffmpeg
        try:
            cmd = [
                FFMPEG_BIN,
                "-y",
                "-i",
                matches[0],
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "wav",
                str(wav_path),
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            # If conversion fails, try reading the file differently
            return jsonify({"error": f"Audio conversion failed: {e}"}), 500
        
        transcription = speech_to_text(str(wav_path))
        
        # Clean up temp file
        if wav_path.exists():
            wav_path.unlink()
        
        # Update in database if available
        if _db_available:
            save_message(
                session_id=session_id,
                role=message.get("role", "user"),
                message_type="voice",
                message_id=message_id,
                content=transcription,
                audio_url=message.get("audio_url", "")
            )
        
        # Update conversation history (memory fallback)
        message["content"] = transcription
        if session_id in conversations:
            for msg in conversations[session_id]:
                if msg.get("message_id") == message_id:
                    msg["content"] = transcription
                    break
        
        return jsonify({"transcription": transcription})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/ai-response", methods=["POST"])
def ai_response():
    """Generate AI response (text + voice) for a voice message."""
    data = request.get_json()
    transcription = data.get("transcription", "").strip()
    user_message_id = data.get("message_id")
    
    if not transcription:
        return jsonify({"error": "No transcription provided"}), 400
    
    session_id = session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        session["session_id"] = session_id
        conversations[session_id] = []
    
    # Get conversation history from database or memory
    if _db_available:
        conversation_history = get_conversation_history(session_id, limit=10)
    else:
        conversation_history = conversations.get(session_id, [])
    
    try:
        # Build prompt and get AI text response
        prompt = build_prompt(transcription, conversation_history)
        ai_text_response = ask_gemini(prompt)
        
        # Check if response is an error message
        if ai_text_response.startswith("Sorry, I encountered an error") or ai_text_response.startswith("Sorry, I've reached"):
            # Return error without generating voice
            return jsonify({
                "text": ai_text_response,
                "error": True
            }), 200
        
        # Generate voice response
        message_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d_%H-%M-%S")
        audio_filename = f"{timestamp}_{message_id}.mp3"
        audio_path = RESPONSES_DIR / audio_filename
        
        # Convert text to speech file
        audio_url = None
        s3_url_stored = None  # S3 URL to store in DB
        try:
            text_to_speech_file(ai_text_response, str(audio_path), FFMPEG_BIN)  
            
            # Update filename if it was converted to WAV
            if not audio_path.exists():
                audio_path = RESPONSES_DIR / f"{timestamp}_{message_id}.wav"
                audio_filename = f"{timestamp}_{message_id}.wav"
            
            # Upload to S3 if configured
            if _s3_available and audio_path.exists():
                s3_url_stored = upload_to_s3(audio_path, key=f"responses/{audio_filename}")
                if s3_url_stored:
                    # Always use /audio/<message_id> for frontend, backend will proxy to S3
                    audio_url = f"/audio/{message_id}"
                else:
                    print(f"⚠️  S3 upload failed for {message_id}, using local storage")
                    audio_url = f"/audio/{message_id}"
            else:
                audio_url = f"/audio/{message_id}"
                
        except Exception as tts_err:
            print(f"⚠️  TTS Error: {tts_err}")
            # Continue without voice if TTS fails
            audio_url = None
        
        # Save to database if available (store S3 URL in DB, but return /audio/<message_id> to frontend)
        if _db_available:
            save_message(
                session_id=session_id,
                role="model",
                message_type="voice" if audio_url else "text",
                message_id=message_id,
                content=ai_text_response,
                audio_url=s3_url_stored or audio_url or ""
            )
        
        # Update conversation history (also keep in memory as fallback)
        conversation_history.append({
            "role": "model",
            "type": "voice" if audio_url else "text",
            "content": ai_text_response,
            "audio_url": audio_url or "",
            "message_id": message_id,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep only last 10 messages
        if len(conversation_history) > 10:
            conversation_history = conversation_history[-10:]
        
        conversations[session_id] = conversation_history
        
        return jsonify({
            "text": ai_text_response,
            "audio_url": audio_url or "",
            "message_id": message_id
        })
        
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower():
            error_msg = "API rate limit exceeded. Please try again in a few moments."
        return jsonify({"error": error_msg}), 500


if __name__ == "__main__":
    # Initialize database and check S3
    initialize_services()
    
    if not check_ffmpeg():
        print(f"⚠️  WARNING: FFmpeg not found at '{FFMPEG_BIN}'")
        print("   The voice assistant requires FFmpeg to convert audio files.")
        print("   Please install FFmpeg and add it to your PATH, or set the FFMPEG_BIN environment variable.")
        print("   Download from: https://ffmpeg.org/download.html")
        print()
    app.run(debug=True)