"""
Deepgram Voice Agent - Full duplex voice conversation using Deepgram's Voice Agent API V1.
Uses raw WebSocket for Python 3.14 compatibility.

CRITICAL: Deepgram Voice Agent API requires LINEAR16 (PCM) audio input at 48000Hz.
Browser sends WebM/Opus which MUST be converted to PCM before sending.

Based on official Deepgram documentation:
https://developers.deepgram.com/docs/voice-agent
"""
import os
import threading
import time
import json
import io
import struct
from typing import Optional, Callable, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Set ffmpeg path for pydub (Windows)
FFMPEG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                           'ffmpeg-8.0.1-essentials_build', 'bin')
if os.path.exists(FFMPEG_PATH):
    os.environ['PATH'] = FFMPEG_PATH + os.pathsep + os.environ.get('PATH', '')
    print(f"[Voice Agent] ffmpeg path set: {FFMPEG_PATH}")

# Check for websockets
try:
    import websockets
    from websockets.sync.client import connect as ws_connect
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    print("[WARNING] websockets package not installed. Run: pip install websockets")
    WEBSOCKETS_AVAILABLE = False

# Check for pydub (audio conversion)
PYDUB_AVAILABLE = False
try:
    from pydub import AudioSegment
    # Configure pydub to use local ffmpeg
    if os.path.exists(FFMPEG_PATH):
        AudioSegment.converter = os.path.join(FFMPEG_PATH, 'ffmpeg.exe')
        AudioSegment.ffprobe = os.path.join(FFMPEG_PATH, 'ffprobe.exe')
    PYDUB_AVAILABLE = True
    print("[Voice Agent] pydub loaded for audio conversion")
except ImportError:
    print("[WARNING] pydub not available - WebM audio conversion disabled")
    print("[WARNING] Run: pip install pydub")

# API Keys
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not DEEPGRAM_API_KEY:
    print("[WARNING] Missing DEEPGRAM_API_KEY for Voice Agent")
if not OPENAI_API_KEY:
    print("[WARNING] Missing OPENAI_API_KEY for Voice Agent LLM")

# Deepgram Voice Agent WebSocket URL (V1 API)
VOICE_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"

# System prompt for the voice agent - MUST BE VERY SHORT
VOICE_AGENT_PROMPT = """You are Jarvis, a friendly voice assistant.

CRITICAL RULES:
- MAXIMUM 1-2 sentences per response
- Be EXTREMELY brief and concise
- Never give long explanations
- If asked a complex question, give a simple short answer first
- Only elaborate if user specifically asks for more details
- Sound natural and friendly

Example good responses:
- "Lambda is AWS's serverless compute service."
- "It lets you run code without managing servers."
- "Sure, what would you like to know?"

NEVER give responses longer than 2 sentences unless explicitly asked."""


def convert_webm_to_linear16(webm_bytes: bytes, target_sample_rate: int = 48000) -> Optional[bytes]:
    """
    Convert WebM/Opus audio to Linear16 PCM format.
    
    Args:
        webm_bytes: Raw WebM audio bytes from browser
        target_sample_rate: Target sample rate (48000 for Voice Agent input)
    
    Returns:
        Linear16 PCM bytes or None if conversion fails
    """
    if not PYDUB_AVAILABLE:
        return None
    
    try:
        # Load WebM audio
        audio = AudioSegment.from_file(io.BytesIO(webm_bytes), format="webm")
        
        # Convert to: mono, target sample rate, 16-bit
        audio = audio.set_channels(1)
        audio = audio.set_frame_rate(target_sample_rate)
        audio = audio.set_sample_width(2)  # 16-bit = 2 bytes
        
        # Return raw PCM data
        return audio.raw_data
        
    except Exception as e:
        print(f"[ERROR] Audio conversion failed: {e}")
        return None


class DeepgramVoiceAgent:
    """
    Deepgram Voice Agent for real-time voice calls.
    Uses raw WebSocket for Python 3.14+ compatibility.
    
    IMPORTANT AUDIO FORMAT REQUIREMENTS:
    - Input: linear16 (PCM 16-bit), 48000 Hz, mono
    - Output: linear16 (PCM 16-bit), 24000 Hz, mono
    
    Based on official documentation:
    https://developers.deepgram.com/docs/voice-agent
    """
    
    def __init__(
        self,
        session_id: str,
        on_transcription: Optional[Callable[[str, bool], None]] = None,
        on_response_text: Optional[Callable[[str], None]] = None,
        on_audio_response: Optional[Callable[[bytes], None]] = None,
        on_agent_thinking: Optional[Callable[[], None]] = None,
        on_agent_speaking: Optional[Callable[[], None]] = None,
        on_agent_done: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        language: str = "en"
    ):
        """
        Initialize the Voice Agent.
        
        Args:
            session_id: Unique session identifier
            on_transcription: Callback for user transcriptions (text, is_final)
            on_response_text: Callback for agent response text
            on_audio_response: Callback for agent audio response (linear16 PCM bytes)
            on_agent_thinking: Callback when agent starts thinking
            on_agent_speaking: Callback when agent starts speaking
            on_agent_done: Callback when agent finishes speaking
            on_error: Callback for errors
            language: Language code ('en', 'ur', 'hi')
        """
        self.session_id = session_id
        self.language = language
        self.on_transcription = on_transcription
        self.on_response_text = on_response_text
        self.on_audio_response = on_audio_response
        self.on_agent_thinking = on_agent_thinking
        self.on_agent_speaking = on_agent_speaking
        self.on_agent_done = on_agent_done
        self.on_error = on_error
        
        # Connection state
        self.ws = None
        self.is_connected = False
        self.is_running = False
        
        # Audio buffer for collecting response
        self.audio_buffer = bytearray()
        self.file_counter = 0
        
        # Audio streaming buffer - accumulate before sending
        # Larger chunks = smoother playback (0.4 sec = 19200 bytes @ 24kHz 16-bit)
        self.stream_buffer = bytearray()
        self.stream_buffer_size = 19200  # Send every 0.4 sec for smoother streaming
        
        # Thread safety
        self._lock = threading.Lock()
        self._receiver_thread = None
        self._keep_alive_thread = None
        
    def start(self) -> bool:
        """
        Start the Voice Agent connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        if not WEBSOCKETS_AVAILABLE:
            if self.on_error:
                self.on_error("websockets package not available")
            return False
        
        if not DEEPGRAM_API_KEY:
            if self.on_error:
                self.on_error("DEEPGRAM_API_KEY not configured")
            return False
        
        # Retry logic for connection
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                # Connect to Voice Agent WebSocket
                headers = {
                    "Authorization": f"Token {DEEPGRAM_API_KEY}"
                }
                
                print(f"[Voice Agent] Connecting to {VOICE_AGENT_URL}... (attempt {attempt + 1}/{max_retries})")
                self.ws = ws_connect(
                    VOICE_AGENT_URL,
                    additional_headers=headers,
                    open_timeout=45,
                    close_timeout=15
                )
                
                with self._lock:
                    self.is_connected = True
                    self.is_running = True
                
                print(f"[Voice Agent] Connected for session: {self.session_id}")
                break  # Connection successful
                
            except Exception as e:
                error_msg = f"Connection attempt {attempt + 1} failed: {e}"
                print(f"[Voice Agent] {error_msg}")
                
                if attempt < max_retries - 1:
                    print(f"[Voice Agent] Retrying in {retry_delay} seconds...")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    error_msg = f"Failed to connect after {max_retries} attempts: {e}"
                    print(f"[ERROR] {error_msg}")
                    import traceback
                    traceback.print_exc()
                    if self.on_error:
                        self.on_error(error_msg)
                    return False
        
        try:
            
            # Start receiver thread
            self._receiver_thread = threading.Thread(
                target=self._receive_messages,
                daemon=True
            )
            self._receiver_thread.start()
            
            # Start keep-alive thread
            self._keep_alive_thread = threading.Thread(
                target=self._keep_alive,
                daemon=True
            )
            self._keep_alive_thread.start()
            
            # Send settings configuration
            self._send_settings()
            
            print(f"[Voice Agent] Started for session: {self.session_id}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to start Voice Agent: {e}"
            print(f"[ERROR] {error_msg}")
            import traceback
            traceback.print_exc()
            if self.on_error:
                self.on_error(error_msg)
            return False
    
    def _send_settings(self):
        """Send Voice Agent settings/configuration following official API."""
        
        # Build settings message matching official documentation
        # https://developers.deepgram.com/docs/voice-agent-settings
        settings = {
            "type": "Settings",
            "audio": {
                "input": {
                    "encoding": "linear16",   # REQUIRED: PCM 16-bit
                    "sample_rate": 48000,     # 48kHz input
                },
                "output": {
                    "encoding": "linear16",   # PCM 16-bit output
                    "sample_rate": 24000,     # 24kHz for playback
                    "container": "none",      # Raw PCM (no container)
                },
            },
            "agent": {
                "language": "en",  # English for both STT and TTS
                "listen": {
                    "provider": {
                        "type": "deepgram",
                        "model": "nova-3",    # Best STT model
                        "smart_format": False,
                    }
                },
                "think": {
                    "provider": {
                        "type": "open_ai",
                        "model": "gpt-4o-mini",
                    },
                    "prompt": VOICE_AGENT_PROMPT,
                },
                "speak": {
                    "provider": {
                        "type": "deepgram",
                        "model": "aura-2-thalia-en",  # English TTS voice
                    }
                },
                "greeting": "Hello! I'm Jarvis. How can I help you today?",
            },
        }
        
        # Send settings as JSON
        self._send_json(settings)
        print(f"[Voice Agent] Settings sent (linear16 @ 48kHz input, 24kHz output, English)")
    
    def _send_json(self, data: dict):
        """Send JSON message to WebSocket."""
        try:
            if self.ws and self.is_connected:
                self.ws.send(json.dumps(data))
        except Exception as e:
            print(f"[ERROR] Error sending JSON: {e}")
    
    def _receive_messages(self):
        """Receive and process messages from Voice Agent."""
        while self.is_running:
            try:
                if not self.ws or not self.is_connected:
                    break
                
                # Receive message (blocks until message received)
                message = self.ws.recv()
                
                # Handle binary audio data (linear16 PCM from agent)
                if isinstance(message, bytes):
                    self.audio_buffer.extend(message)
                    # Buffer audio and send in larger chunks for smoother playback
                    self.stream_buffer.extend(message)
                    if len(self.stream_buffer) >= self.stream_buffer_size:
                        if self.on_audio_response:
                            self.on_audio_response(bytes(self.stream_buffer))
                        self.stream_buffer = bytearray()
                    continue
                
                # Handle JSON messages
                try:
                    data = json.loads(message)
                    self._handle_message(data)
                except json.JSONDecodeError:
                    print(f"[WARNING] Invalid JSON: {message[:100]}")
                    
            except Exception as e:
                if self.is_running:
                    error_msg = str(e)
                    if "closed" not in error_msg.lower():
                        print(f"[ERROR] Receiver error: {e}")
                    with self._lock:
                        self.is_connected = False
                break
    
    def _handle_message(self, data: dict):
        """Handle JSON message from Voice Agent."""
        msg_type = data.get("type", "Unknown")
        
        print(f"[Voice Agent] Event: {msg_type}")
        
        if msg_type == "Welcome":
            print(f"[Voice Agent] Welcome received - connection established")
        
        elif msg_type == "SettingsApplied":
            print(f"[Voice Agent] Settings applied successfully")
        
        elif msg_type == "ConversationText":
            # User or agent text
            role = data.get("role", "")
            content = data.get("content", "")
            
            if role == "user" and content:
                # User's transcribed speech
                print(f"[Voice Agent] User said: {content}")
                if self.on_transcription:
                    self.on_transcription(content, True)
            
            elif role == "assistant" and content:
                # Agent's response text
                print(f"[Voice Agent] Agent says: {content}")
                if self.on_response_text:
                    self.on_response_text(content)
        
        elif msg_type == "UserStartedSpeaking":
            print(f"[Voice Agent] User started speaking - interrupting agent")
            # Clear ALL buffers when user interrupts (including stream buffer)
            self.audio_buffer = bytearray()
            self.stream_buffer = bytearray()  # Clear stream buffer to prevent partial chunks
        
        elif msg_type == "AgentThinking":
            print(f"[Voice Agent] Agent thinking...")
            if self.on_agent_thinking:
                self.on_agent_thinking()
        
        elif msg_type == "AgentStartedSpeaking":
            print(f"[Voice Agent] Agent started speaking")
            # Reset buffers for new response
            self.audio_buffer = bytearray()
            self.stream_buffer = bytearray()
            if self.on_agent_speaking:
                self.on_agent_speaking()
        
        elif msg_type == "AgentAudioDone":
            # Flush any remaining audio in stream buffer
            if len(self.stream_buffer) > 0:
                if self.on_audio_response:
                    self.on_audio_response(bytes(self.stream_buffer))
                self.stream_buffer = bytearray()
            
            print(f"[Voice Agent] Agent finished speaking ({len(self.audio_buffer)} bytes)")
            self.file_counter += 1
            if self.on_agent_done:
                self.on_agent_done()
            # Clear buffer after done
            self.audio_buffer = bytearray()
        
        elif msg_type == "Error":
            error_msg = data.get("description", data.get("message", "Unknown error"))
            error_code = data.get("code", "")
            print(f"[ERROR] Voice Agent error: {error_msg} (code: {error_code})")
            print(f"[ERROR] Full error data: {data}")
            if self.on_error:
                self.on_error(error_msg)
    
    def _keep_alive(self):
        """Send keep-alive messages every 5 seconds."""
        while self.is_running:
            try:
                time.sleep(5)
                if self.ws and self.is_connected:
                    self._send_json({"type": "KeepAlive"})
                    print("[Voice Agent] Keep-alive sent")
            except:
                break
    
    def send_audio(self, audio_bytes: bytes, is_webm: bool = True):
        """
        Send audio chunk to Voice Agent.
        
        CRITICAL: Voice Agent requires LINEAR16 PCM audio at 48kHz.
        WebM/Opus from browser MUST be converted before sending.
        
        Args:
            audio_bytes: Audio bytes (WebM or PCM)
            is_webm: True if WebM format (needs conversion), False if already PCM
        """
        if not audio_bytes or len(audio_bytes) == 0:
            return
        
        if not self.ws or not self.is_connected:
            print("[WARNING] Cannot send audio - not connected")
            return
        
        try:
            if is_webm:
                if PYDUB_AVAILABLE:
                    # Convert WebM to Linear16 PCM
                    pcm_data = convert_webm_to_linear16(audio_bytes)
                    if pcm_data:
                        self.ws.send(pcm_data)
                        print(f"[Voice Agent] Sent {len(pcm_data)} bytes PCM (converted from {len(audio_bytes)} bytes WebM)")
                    else:
                        print("[WARNING] Audio conversion failed - skipping chunk")
                else:
                    print("[ERROR] Cannot convert WebM - pydub not available!")
                    print("[ERROR] Voice Agent requires linear16 PCM audio")
                    if self.on_error:
                        self.on_error("Audio format incompatible - pydub required for conversion")
            else:
                # Assume already PCM
                self.ws.send(audio_bytes)
                print(f"[Voice Agent] Sent {len(audio_bytes)} bytes PCM")
                
        except Exception as e:
            print(f"[ERROR] Error sending audio: {e}")
    
    def send_raw_pcm(self, pcm_bytes: bytes):
        """
        Send raw PCM audio directly (already in Linear16 format at 48kHz).
        
        Args:
            pcm_bytes: Raw Linear16 PCM audio bytes (mono, 48kHz, 16-bit)
        """
        if not pcm_bytes or len(pcm_bytes) == 0:
            return
        
        if not self.ws or not self.is_connected:
            return
        
        try:
            self.ws.send(pcm_bytes)
        except Exception as e:
            print(f"[ERROR] Error sending PCM audio: {e}")
    
    def stop(self):
        """Stop the Voice Agent and clean up resources."""
        print(f"[Voice Agent] Stopping session: {self.session_id}")
        
        with self._lock:
            self.is_running = False
            self.is_connected = False
        
        try:
            if self.ws:
                try:
                    self.ws.close()
                except:
                    pass
        except:
            pass
        finally:
            self.ws = None
            self.audio_buffer = bytearray()
        
        # Wait for threads to finish (with timeout)
        import time
        time.sleep(0.5)  # Give threads time to exit
        
        print(f"[Voice Agent] Session stopped: {self.session_id}")
    
    @property
    def connected(self) -> bool:
        """Check if Voice Agent is connected."""
        with self._lock:
            return self.is_connected


# Factory function to create Voice Agent
def create_voice_agent(
    session_id: str,
    callbacks: Dict[str, Callable] = None,
    language: str = "en"
) -> Optional[DeepgramVoiceAgent]:
    """
    Create a new Deepgram Voice Agent instance.
    
    Args:
        session_id: Unique session ID
        callbacks: Dict of callback functions:
            - on_transcription(text, is_final)
            - on_response_text(text)
            - on_audio_response(bytes) - Linear16 PCM at 24kHz
            - on_agent_thinking()
            - on_agent_speaking()
            - on_agent_done()
            - on_error(error_msg)
        language: Language code
    
    Returns:
        DeepgramVoiceAgent instance or None if not available
    """
    if not is_voice_agent_available():
        print("[ERROR] Deepgram Voice Agent not available")
        return None
    
    callbacks = callbacks or {}
    
    agent = DeepgramVoiceAgent(
        session_id=session_id,
        on_transcription=callbacks.get('on_transcription'),
        on_response_text=callbacks.get('on_response_text'),
        on_audio_response=callbacks.get('on_audio_response'),
        on_agent_thinking=callbacks.get('on_agent_thinking'),
        on_agent_speaking=callbacks.get('on_agent_speaking'),
        on_agent_done=callbacks.get('on_agent_done'),
        on_error=callbacks.get('on_error'),
        language=language
    )
    
    return agent


def is_voice_agent_available() -> bool:
    """Check if Deepgram Voice Agent is available."""
    if not WEBSOCKETS_AVAILABLE:
        print("[WARNING] websockets not available")
        return False
    if not DEEPGRAM_API_KEY:
        print("[WARNING] DEEPGRAM_API_KEY not set")
        return False
    if not PYDUB_AVAILABLE:
        print("[WARNING] pydub not available - audio conversion will fail")
        # Still return True, but conversion will fail at runtime
    return True
