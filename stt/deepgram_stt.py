"""
Deepgram streaming Speech-to-Text with real-time transcription.
Supports partial transcripts, multi-language detection (English, Urdu, Hindi).
Low latency (<500ms for partials).
"""
import os
import threading
import queue
from typing import Optional, Tuple, Callable
from pathlib import Path
from dotenv import load_dotenv
from deepgram import DeepgramClient
from deepgram.core.events import EventType

load_dotenv()

# Deepgram API key
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    print("[WARNING] Missing DEEPGRAM_API_KEY. Set it in .env file.")

# Language codes mapping
LANGUAGE_MAP = {
    "en": "en-US",  # English
    "ur": "ur-PK",  # Urdu (Pakistan)  
    "hi": "hi-IN",  # Hindi (India)
}

# Global Deepgram client (lazy loaded)
_deepgram_client: Optional[DeepgramClient] = None

def get_deepgram_client() -> Optional[DeepgramClient]:
    """Get or create Deepgram client."""
    global _deepgram_client
    
    if _deepgram_client is not None:
        return _deepgram_client
    
    if not DEEPGRAM_API_KEY:
        print("[WARNING] Deepgram API key not configured")
        return None
    
    try:
        _deepgram_client = DeepgramClient(api_key=DEEPGRAM_API_KEY)
        return _deepgram_client
    except Exception as e:
        print(f"[WARNING] Error initializing Deepgram client: {e}")
        return None

def detect_text_language(text: str) -> str:
    """
    Detect language from transcribed text.
    Uses utils.language for consistent detection across the application.
    """
    from utils.language import detect_text_language as _detect
    return _detect(text)

def speech_to_text(audio_path: str, lang: str = "en") -> Tuple[str, str]:
    """
    Transcribe audio file using Deepgram with auto language detection.
    Supports English, Urdu, Hindi and more.
    
    Args:
        audio_path: Path to audio file (any format - WebM, MP3, WAV, etc.)
        lang: Language hint ('en', 'ur', 'hi') - used as fallback
    
    Returns:
        Tuple of (transcribed_text, detected_language)
    """
    client = get_deepgram_client()
    if not client:
        print("[ERROR] Deepgram client not available")
        return ("", lang)
    
    try:
        # Read audio file
        with open(audio_path, "rb") as audio_file:
            buffer_data = audio_file.read()
        
        print(f"[STT] Audio file size: {len(buffer_data)} bytes")
        
        # Transcribe using Deepgram SDK v5+ API with AUTO LANGUAGE DETECTION
        # detect_language=True enables multi-language auto detection
        response = client.listen.v1.media.transcribe_file(
            request=buffer_data,
            model="nova-2",
            detect_language=True,  # Auto detect language (English, Urdu, Hindi, etc.)
            smart_format=True,
            punctuate=True,
        )
        
        # Extract transcript and detected language - SDK v5 response structure
        if hasattr(response, 'results') and response.results:
            # Get detected language from metadata
            detected_lang = lang
            if hasattr(response.results, 'channels') and response.results.channels:
                channel = response.results.channels[0]
                
                # Get detected language code
                if hasattr(channel, 'detected_language') and channel.detected_language:
                    detected_lang_code = channel.detected_language
                    # Map to our language codes
                    if detected_lang_code.startswith('ur'):
                        detected_lang = 'ur'
                    elif detected_lang_code.startswith('hi'):
                        detected_lang = 'hi'
                    elif detected_lang_code.startswith('en'):
                        detected_lang = 'en'
                    print(f"[STT] Detected language: {detected_lang_code} -> {detected_lang}")
                
                if hasattr(channel, 'alternatives') and channel.alternatives:
                    transcript = channel.alternatives[0].transcript
                    
                    # Also detect from text as backup
                    if not detected_lang or detected_lang == lang:
                        detected_lang = detect_text_language(transcript) if transcript else lang
                    
                    print(f"[STT] Transcription ({detected_lang}): '{transcript[:100]}...' " if len(transcript) > 100 else f"[STT] Transcription ({detected_lang}): '{transcript}'")
                    return (transcript.strip(), detected_lang)
        
        print("[STT] No transcript in response")
        return ("", lang)
        
    except Exception as e:
        print(f"[ERROR] Deepgram STT error: {e}")
        print(f"[ERROR] Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return ("", lang)

class DeepgramStreamingSTT:
    """
    Deepgram streaming STT handler for real-time transcription.
    Thread-safe, supports partial and final transcripts.
    Uses v1 API with WebM Opus support (encoding and sample_rate specified).
    """
    
    def __init__(self, lang: str = "en", on_transcript: Optional[Callable[[str, bool], None]] = None):
        """
        Initialize streaming STT.
        
        Args:
            lang: Language hint
            on_transcript: Callback for transcripts (text, is_final)
        """
        self.client = get_deepgram_client()
        self.lang = lang
        self.on_transcript = on_transcript
        self.connection = None
        self.connection_context = None
        self.transcript_queue = queue.Queue()
        self.is_connected = False
        self.connection_thread = None
        self._lock = threading.Lock()
        self._audio_sent = False  # Track if we've sent any audio
        
    def start(self):
        """Start Deepgram WebSocket connection using context manager."""
        if not self.client:
            print("[ERROR] Deepgram client not available")
            return False
        
        try:
            # Use v1 API WITHOUT specifying encoding
            # Let Deepgram auto-detect the format from WebM container
            # This is more reliable than specifying encoding/sample_rate
            self.connection_context = self.client.listen.v1.connect(
                model="nova-2",
                language=LANGUAGE_MAP.get(self.lang, "en-US"),
                # Don't specify encoding - let Deepgram auto-detect from WebM container
                smart_format=True,
                punctuate=True,
                interim_results=True,  # Enable partial transcripts
            )
            
            # Set up event handlers BEFORE entering context (so we don't miss OPEN event)
            connection_ready = threading.Event()
            
            def on_open(event, **kwargs):
                with self._lock:
                    self.is_connected = True
                connection_ready.set()
                print("[OK] Deepgram streaming connection OPEN")
            
            def on_message(message, **kwargs):
                """Handle transcript messages from Deepgram."""
                try:
                    # Deepgram SDK v5 structure: message.channel.alternatives[]
                    # message has: channel (object), is_final (bool), speech_final (bool), etc.
                    transcript = None
                    is_final = False
                    
                    # Check if message has channel with alternatives
                    if hasattr(message, 'channel') and message.channel:
                        channel = message.channel
                        if hasattr(channel, 'alternatives') and channel.alternatives:
                            # Get first (best) alternative
                            alt = channel.alternatives[0]
                            if hasattr(alt, 'transcript') and alt.transcript:
                                transcript = alt.transcript
                    
                    # Get is_final from message (not from alternative)
                    if hasattr(message, 'is_final'):
                        is_final = message.is_final
                    elif hasattr(message, 'speech_final'):
                        is_final = message.speech_final
                    
                    # Process transcript if found
                    if transcript and transcript.strip():
                        self.transcript_queue.put((transcript, is_final))
                        
                        if self.on_transcript:
                            self.on_transcript(transcript, is_final)
                            
                except Exception as e:
                    print(f"[WARNING] Error processing transcript message: {e}")
                    import traceback
                    traceback.print_exc()
            
            def on_error(error, **kwargs):
                error_msg = str(error) if error else "Unknown error"
                print(f"[ERROR] Deepgram error: {error_msg}")
                with self._lock:
                    self.is_connected = False
                connection_ready.set()  # Unblock even on error
            
            def on_close(event, **kwargs):
                with self._lock:
                    self.is_connected = False
                print("[CLOSED] Deepgram connection closed")
            
            # Enter context to get actual connection object
            # This will trigger OPEN event, so handlers must be registered first
            self.connection = self.connection_context.__enter__()
            
            # Register handlers immediately after getting connection
            self.connection.on(EventType.OPEN, on_open)
            self.connection.on(EventType.MESSAGE, on_message)
            self.connection.on(EventType.ERROR, on_error)
            self.connection.on(EventType.CLOSE, on_close)
            
            # Start listening - MUST be called after handlers are registered
            try:
                if hasattr(self.connection, 'start_listening'):
                    self.connection.start_listening()
                    print("[OK] Deepgram start_listening() called")
            except Exception as e:
                print(f"[WARNING] start_listening error: {e}")
            
            # Wait for OPEN event with timeout
            # Give it a moment for async event to fire
            import time
            time.sleep(0.2)  # Small delay to let OPEN event fire if it's synchronous
            
            if not connection_ready.wait(timeout=2.8):
                print("[WARNING] OPEN event not received after 3 seconds")
                # Check if connection object exists and seems valid
                if self.connection:
                    # Try to send a keep-alive to test connection
                    try:
                        if hasattr(self.connection, 'send_keep_alive'):
                            self.connection.send_keep_alive()
                            print("[INFO] Keep-alive sent successfully - connection appears ready")
                            with self._lock:
                                self.is_connected = True
                        else:
                            # No keep-alive method, assume ready
                            with self._lock:
                                self.is_connected = True
                            print("[INFO] Manually set is_connected=True (no keep-alive method)")
                    except Exception as e:
                        print(f"[WARNING] Could not send keep-alive: {e}")
                        # Still set as connected - let audio sending test it
                        with self._lock:
                            self.is_connected = True
                else:
                    print("[ERROR] Connection object is None - cannot proceed")
                    return False
            else:
                print("[OK] OPEN event confirmed - connection ready")
            
            # Start keep-alive thread to maintain connection
            def keep_alive():
                import time
                # Send first keep-alive immediately to prevent timeout
                time.sleep(0.5)
                try:
                    with self._lock:
                        if self.connection and hasattr(self.connection, 'send_keep_alive'):
                            self.connection.send_keep_alive()
                            print("[OK] Initial keep-alive sent")
                except:
                    pass
                
                try:
                    # Keep connection alive - send keep-alive messages every 3 seconds
                    while True:
                        with self._lock:
                            if not self.is_connected and self.connection is None:
                                break
                            # Send keep-alive to prevent timeout
                            if self.connection and hasattr(self.connection, 'send_keep_alive'):
                                try:
                                    self.connection.send_keep_alive()
                                except:
                                    pass
                        time.sleep(3)  # Send keep-alive every 3 seconds (more frequent)
                except Exception as e:
                    print(f"[WARNING] Connection keep-alive error: {e}")
            
            self.connection_thread = threading.Thread(target=keep_alive, daemon=True)
            self.connection_thread.start()
            
            # Wait a bit more for connection to stabilize
            import time
            time.sleep(0.3)
            
            # Connection is now ready
            return self.is_connected
            
        except Exception as e:
            print(f"[ERROR] Error starting Deepgram connection: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def send_audio(self, audio_bytes: bytes):
        """Send audio chunk to Deepgram using send_media() method."""
        if not audio_bytes or len(audio_bytes) == 0:
            return
        
        # Get connection reference while holding lock
        with self._lock:
            if not self.connection:
                print("[WARNING] No Deepgram connection available")
                return
            
            # Check connection state
            if not self.is_connected:
                # Don't send if connection not ready yet
                return
            
            # Mark that we've sent audio (for debugging)
            if not self._audio_sent:
                self._audio_sent = True
                print(f"[OK] Sending first audio chunk to Deepgram ({len(audio_bytes)} bytes)")
            
            # Get connection reference (don't hold lock during send)
            connection = self.connection
        
        # Send outside of lock to avoid blocking
        try:
            if hasattr(connection, 'send_media'):
                # This is the correct method for Deepgram SDK v5
                # Send audio data - Deepgram expects raw Opus audio or WebM container
                connection.send_media(audio_bytes)
                
                # Track successful sends
                if not hasattr(self, '_successful_sends'):
                    self._successful_sends = 0
                self._successful_sends += 1
                
            else:
                # Fallback (shouldn't happen, but just in case)
                if not hasattr(self, '_method_warned'):
                    available = [x for x in dir(connection) if not x.startswith('_')]
                    print(f"[ERROR] send_media() not found. Available methods: {available[:10]}")
                    self._method_warned = True
        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] Error sending audio to Deepgram: {error_msg}")
            
            # Don't print full traceback for common errors
            if "timeout" not in error_msg.lower() and "closed" not in error_msg.lower():
                import traceback
                traceback.print_exc()
            
            # Mark connection as failed only if it's a connection error
            if "closed" in error_msg.lower() or "not connected" in error_msg.lower():
                with self._lock:
                    self.is_connected = False
    
    def finish(self):
        """Finish transcription and close connection."""
        try:
            if self.connection:
                # Finish stream using correct method
                if hasattr(self.connection, 'send_finalize'):
                    self.connection.send_finalize()
                elif hasattr(self.connection, 'finish_stream'):
                    self.connection.finish_stream()
                elif hasattr(self.connection, 'finish'):
                    self.connection.finish()
            
            # Exit context manager
            if self.connection_context:
                try:
                    self.connection_context.__exit__(None, None, None)
                except:
                    pass
        except Exception as e:
            print(f"[WARNING] Error finishing connection: {e}")
        finally:
            with self._lock:
                self.is_connected = False
                self.connection = None
                self.connection_context = None
    
    def get_transcripts(self):
        """Get transcripts from queue (generator)."""
        while True:
            try:
                transcript, is_final = self.transcript_queue.get(timeout=0.1)
                yield (transcript, is_final)
            except queue.Empty:
                with self._lock:
                    if not self.is_connected:
                        break
                continue
