"""
Deepgram Voice Agent - Full duplex voice conversation using Deepgram's Voice Agent API V1.
Supports Function Calling for Local Calendar Booking.
"""
import os
import threading
import time
import json
import io
from typing import Optional, Callable, Dict, Any
from dotenv import load_dotenv

# --- Local Tools ---
from llm.tools import APPOINTMENT_TOOLS, check_availability_tool, book_appointment_tool

load_dotenv()

# Set ffmpeg path for pydub (Windows)
FFMPEG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                           'ffmpeg-8.0.1-essentials_build', 'bin')
if os.path.exists(FFMPEG_PATH):
    os.environ['PATH'] = FFMPEG_PATH + os.pathsep + os.environ.get('PATH', '')

# Check for websockets
try:
    import websockets
    from websockets.sync.client import connect as ws_connect
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    print("[WARNING] websockets package not installed. Run: pip install websockets")
    WEBSOCKETS_AVAILABLE = False

# Check for pydub
PYDUB_AVAILABLE = False
try:
    from pydub import AudioSegment
    if os.path.exists(FFMPEG_PATH):
        AudioSegment.converter = os.path.join(FFMPEG_PATH, 'ffmpeg.exe')
        AudioSegment.ffprobe = os.path.join(FFMPEG_PATH, 'ffprobe.exe')
    PYDUB_AVAILABLE = True
except ImportError:
    pass

# API Keys
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

VOICE_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"

# --- UPDATED PROMPT: Added Rule to NOT read URLs ---
VOICE_AGENT_PROMPT = """You are Jarvis, a professional assistant.

YOUR CAPABILITIES:
- You can chat normally about any topic.
- You can BOOK APPOINTMENTS if the user asks.

RULES:
- To book, ASK for Name, Email, and Time.
- ALWAYS use 'check_availability' before booking.
- Keep responses short and conversational (1-2 sentences).
- Do NOT start talking about appointments unless the user mentions them.
- NEVER read out HTTP links or URLs. Instead, say "I've sent the details to your email" or "Check your chat for the link".
"""

def convert_webm_to_linear16(webm_bytes: bytes, target_sample_rate: int = 48000) -> Optional[bytes]:
    """Convert WebM/Opus to Linear16 PCM."""
    if not PYDUB_AVAILABLE: return None
    try:
        audio = AudioSegment.from_file(io.BytesIO(webm_bytes), format="webm")
        audio = audio.set_channels(1)
        audio = audio.set_frame_rate(target_sample_rate)
        audio = audio.set_sample_width(2)
        return audio.raw_data
    except Exception as e:
        print(f"[ERROR] Audio conversion failed: {e}")
        return None

class DeepgramVoiceAgent:
    def __init__(self, session_id: str, on_transcription=None, on_response_text=None, 
                 on_audio_response=None, on_agent_thinking=None, on_agent_speaking=None, 
                 on_agent_done=None, on_error=None, language="en"):
        
        self.session_id = session_id
        self.language = language
        self.on_transcription = on_transcription
        self.on_response_text = on_response_text
        self.on_audio_response = on_audio_response
        self.on_agent_thinking = on_agent_thinking
        self.on_agent_speaking = on_agent_speaking
        self.on_agent_done = on_agent_done
        self.on_error = on_error
        
        self.ws = None
        self.is_connected = False
        self.is_running = False
        self.stream_buffer = bytearray()
        self.stream_buffer_size = 19200
        self._lock = threading.Lock()

    def start(self) -> bool:
        """Start the Voice Agent connection."""
        if not WEBSOCKETS_AVAILABLE or not DEEPGRAM_API_KEY:
            if self.on_error: self.on_error("Missing dependencies or API Key")
            return False
        
        try:
            headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
            print(f"[Voice Agent] Connecting to {VOICE_AGENT_URL}...")
            
            self.ws = ws_connect(VOICE_AGENT_URL, additional_headers=headers, open_timeout=10, close_timeout=5)
            
            with self._lock:
                self.is_connected = True
                self.is_running = True
            
            threading.Thread(target=self._receive_messages, daemon=True).start()
            threading.Thread(target=self._keep_alive, daemon=True).start()
            
            self._send_settings()
            
            print(f"[Voice Agent] Started for session: {self.session_id}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to start Voice Agent: {e}")
            if self.on_error: self.on_error(str(e))
            return False
    
    def _send_settings(self):
        """Send configuration with Function Calling enabled."""
        functions_config = [tool['function'] for tool in APPOINTMENT_TOOLS]

        settings = {
            "type": "Settings",
            "audio": {
                "input": {"encoding": "linear16", "sample_rate": 48000},
                "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"},
            },
            "agent": {
                "language": "en",
                "listen": {
                    "provider": {"type": "deepgram", "model": "nova-3", "smart_format": False}
                },
                "think": {
                    "provider": {"type": "open_ai", "model": "gpt-4o-mini"},
                    "prompt": VOICE_AGENT_PROMPT,
                    "functions": functions_config
                },
                "speak": {
                    "provider": {"type": "deepgram", "model": "aura-2-thalia-en"}
                },
                "greeting": "Hello! I'm Jarvis. How can I help you today?",
            },
        }
        self._send_json(settings)
        print(f"[Voice Agent] Settings sent with {len(functions_config)} tools enabled.")
    
    def _send_json(self, data: dict):
        if self.ws and self.is_connected:
            self.ws.send(json.dumps(data))
    
    def _receive_messages(self):
        """Receive loop."""
        while self.is_running:
            try:
                if not self.ws: break
                message = self.ws.recv()
                
                if isinstance(message, bytes):
                    self.stream_buffer.extend(message)
                    if len(self.stream_buffer) >= self.stream_buffer_size:
                        if self.on_audio_response: self.on_audio_response(bytes(self.stream_buffer))
                        self.stream_buffer = bytearray()
                    continue
                
                data = json.loads(message)
                self._handle_message(data)
                    
            except Exception as e:
                if self.is_running:
                    print(f"[Voice Agent] Receiver error: {e}")
                    with self._lock: self.is_connected = False
                break
    
    def _handle_message(self, data: dict):
        """Handle events from Deepgram."""
        msg_type = data.get("type")
        
        # --- Handle Function Calls ---
        if msg_type == "FunctionCallRequest":
            self._handle_function_call(data)
            return

        if msg_type == "ConversationText":
            role = data.get("role")
            content = data.get("content")
            if role == "user":
                print(f"[User]: {content}")
                if self.on_transcription: self.on_transcription(content, True)
            elif role == "assistant":
                print(f"[Agent]: {content}")
                if self.on_response_text: self.on_response_text(content)
        
        elif msg_type == "UserStartedSpeaking":
            self.stream_buffer = bytearray()
        
        elif msg_type == "AgentAudioDone":
            if len(self.stream_buffer) > 0:
                if self.on_audio_response: self.on_audio_response(bytes(self.stream_buffer))
                self.stream_buffer = bytearray()
            if self.on_agent_done: self.on_agent_done()

        elif msg_type == "Error":
            print(f"[ERROR] Deepgram: {data}")

    def _handle_function_call(self, data: dict):
        """Execute the local tool and send result back to Deepgram."""
        
        # FIX: Deepgram sends a LIST of functions
        functions = data.get("functions", [])
        
        for func in functions:
            call_id = func.get("id")
            func_name = func.get("name")
            arguments_json = func.get("arguments", "{}")
            
            print(f"[Voice Agent] Tool Call: {func_name}")
            
            result = "{}"
            try:
                if func_name == "check_availability":
                    result = check_availability_tool(arguments_json)
                elif func_name == "book_appointment":
                    result = book_appointment_tool(arguments_json, self.session_id)
                else:
                    result = json.dumps({"status": "error", "msg": f"Unknown function {func_name}"})
            except Exception as e:
                result = json.dumps({"status": "error", "msg": str(e)})

            print(f"[Voice Agent] Tool Result: {result}")

            # Send response back to Deepgram
            response_msg = {
                "type": "FunctionCallResponse",
                "function_call_id": call_id,
                "output": result
            }
            self._send_json(response_msg)

    def _keep_alive(self):
        while self.is_running:
            time.sleep(5)
            self._send_json({"type": "KeepAlive"})
    
    def send_audio(self, audio_bytes: bytes, is_webm: bool = True):
        if not self.ws or not self.is_connected: return
        try:
            if is_webm and PYDUB_AVAILABLE:
                pcm_data = convert_webm_to_linear16(audio_bytes)
                if pcm_data: self.ws.send(pcm_data)
            else:
                self.ws.send(audio_bytes)
        except Exception as e:
            print(f"[ERROR] Send Audio: {e}")

    def send_raw_pcm(self, pcm_bytes: bytes):
        if self.ws and self.is_connected:
            try: self.ws.send(pcm_bytes)
            except: pass

    def stop(self):
        print(f"[Voice Agent] Stopping...")
        with self._lock:
            self.is_running = False
            self.is_connected = False
        if self.ws:
            try: self.ws.close()
            except: pass
        
# Factory
def create_voice_agent(session_id: str, callbacks=None, language="en"):
    if not is_voice_agent_available(): return None
    return DeepgramVoiceAgent(session_id, **(callbacks or {}), language=language)

def is_voice_agent_available():
    return WEBSOCKETS_AVAILABLE and bool(DEEPGRAM_API_KEY) and PYDUB_AVAILABLE