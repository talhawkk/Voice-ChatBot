"""
Voice Agent orchestration - coordinates STT, LLM, TTS in streaming pipeline.
Event-driven architecture for real-time voice interactions.
"""
import asyncio
import threading
import uuid
import os
from datetime import datetime
from typing import Dict, Optional, List, Any
import base64
from pathlib import Path
import tempfile
import traceback

from stt.deepgram_stt import speech_to_text
from llm.openai_llm import generate_response
from tts.edge_tts import text_to_speech_bytes_sync, text_to_speech_stream
from storage.redis_client import (
    get_conversation_context,
    append_to_context,
    save_conversation_context,
)
import sys
from pathlib import Path
# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from storage import upload_to_s3
from database import save_message

class VoiceAgent:
    """
    Voice Agent - orchestrates STT, LLM, TTS for real-time voice interactions.
    Uses chunk buffering with batch transcription for reliable voice calls.
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.current_language = "en"
        self.is_streaming = False
        self.audio_buffer = []  # Buffer for audio chunks
        self.socketio = None  # Will be set by WebSocket handler
        self.deepgram_stt = None  # Not used in batch mode
        self.current_transcript = ""  # Accumulated transcript
        self._lock = threading.Lock()
        self._processing = False  # Flag to prevent overlapping processing
        self._last_audio_time = None  # Track when last audio was received
        self._silence_timer = None  # Timer for silence detection
        self._call_active = False  # Track if call is active
    
    def set_socketio(self, socketio_instance):
        """Set SocketIO instance for sending messages."""
        self.socketio = socketio_instance
    
    def start_streaming_stt(self):
        """
        Initialize for voice call. 
        Uses batch transcription instead of streaming for reliability.
        """
        with self._lock:
            self.audio_buffer = []
            self._call_active = True
            self._processing = False
        print(f"[OK] Voice agent ready for session: {self.session_id}")
        return True
        
    def process_audio_chunk(self, audio_bytes: bytes):
        """
        Process audio chunk from browser.
        Buffers audio and processes after silence detection.
        """
        if not self._call_active:
            return
        
        chunk_size = len(audio_bytes)
        with self._lock:
            self.audio_buffer.append(audio_bytes)
            self._last_audio_time = datetime.now()
            buffer_count = len(self.audio_buffer)
        
        # Log first chunk
        if buffer_count == 1:
            print(f"[AUDIO] First chunk received: {chunk_size} bytes")
        elif buffer_count % 10 == 0:
            print(f"[AUDIO] Chunks buffered: {buffer_count}")
        
        # Reset silence timer
        if self._silence_timer:
            self._silence_timer.cancel()
        
        # Process after 1.5 seconds of silence (speech likely ended)
        def check_silence():
            if not self._call_active:
                return
            with self._lock:
                if self.audio_buffer and not self._processing:
                    total_size = sum(len(c) for c in self.audio_buffer)
                    print(f"[SILENCE] Processing {len(self.audio_buffer)} chunks ({total_size} bytes)")
            self._process_buffered_audio()
        
        self._silence_timer = threading.Timer(1.5, check_silence)
        self._silence_timer.daemon = True
        self._silence_timer.start()
    
    def _process_buffered_audio(self):
        """Process accumulated audio buffer."""
        with self._lock:
            if not self.audio_buffer or self._processing:
                print(f"[SKIP] No buffer or already processing")
                return
            self._processing = True
            audio_data = b''.join(self.audio_buffer)
            self.audio_buffer = []
        
        print(f"[PROCESS] Got {len(audio_data)} bytes of audio")
        
        if len(audio_data) < 1000:  # Too small, likely noise
            print(f"[SKIP] Audio too small ({len(audio_data)} bytes)")
            with self._lock:
                self._processing = False
            return
        
        # Run in background thread
        def process():
            try:
                print(f"[STT] Saving audio to temp file...")
                # Save to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
                    tmp.write(audio_data)
                    tmp_path = tmp.name
                
                try:
                    print(f"[STT] Calling Deepgram transcribe...")
                    # Transcribe using Deepgram file API (reliable)
                    transcription, detected_lang = speech_to_text(tmp_path, self.current_language)
                    self.current_language = detected_lang
                    print(f"[STT] Result: '{transcription}' (lang: {detected_lang})")
                    
                    if transcription and transcription.strip():
                        # Send transcription to client
                        if self.socketio:
                            self.socketio.emit('transcription', {
                                'text': transcription,
                                'is_final': True
                            }, room=self.session_id)
                        
                        # Get LLM response
                        context = get_conversation_context(self.session_id)
                        response_text = generate_response(
                            transcription,
                            context,
                            self.current_language
                        )
                        
                        # Save to context
                        append_to_context(self.session_id, {
                            'role': 'user',
                            'content': transcription,
                            'timestamp': datetime.now().isoformat()
                        })
                        append_to_context(self.session_id, {
                            'role': 'model',
                            'content': response_text,
                            'timestamp': datetime.now().isoformat()
                        })
                        
                        # Generate TTS
                        audio_bytes = text_to_speech_bytes_sync(response_text, self.current_language)
                        
                        # Send to client
                        if self.socketio:
                            self.socketio.emit('response_text', {
                                'text': response_text
                            }, room=self.session_id)
                            
                            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
                            self.socketio.emit('audio_response', {
                                'audio': audio_b64
                            }, room=self.session_id)
                        
                        print(f"[OK] Processed: '{transcription[:50]}...' -> Response sent")
                    
                finally:
                    # Clean up temp file
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
            
            except Exception as e:
                print(f"[ERROR] Processing audio: {e}")
                import traceback
                traceback.print_exc()
            finally:
                with self._lock:
                    self._processing = False
        
        thread = threading.Thread(target=process, daemon=True)
        thread.start()
    
    def process_voice_message(self, audio_bytes: bytes) -> Dict[str, Any]:
        """
        Process complete voice message (record and send mode).
        Returns transcription, response, and audio.
        """
        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        try:
            # Transcribe
            transcription, detected_lang = speech_to_text(tmp_path, self.current_language)
            self.current_language = detected_lang
            
            if not transcription:
                return {
                    'transcription': '',
                    'response_text': '',
                    'response_audio_b64': '',
                    'message_id': '',
                    'language': detected_lang
                }
            
            # Get LLM response
            context = get_conversation_context(self.session_id)
            response_text = generate_response(
                transcription,
                context,
                self.current_language
            )
            
            # Generate message IDs
            user_message_id = str(uuid.uuid4())
            ai_message_id = str(uuid.uuid4())
            
            # Save to database
            save_message(
                session_id=self.session_id,
                role='user',
                message_type='voice',
                message_id=user_message_id,
                content=transcription
            )
            save_message(
                session_id=self.session_id,
                role='model',
                message_type='voice',
                message_id=ai_message_id,
                content=response_text
            )
            
            # Generate TTS audio
            audio_bytes = text_to_speech_bytes_sync(response_text, self.current_language)
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
            
            # Save to context
            append_to_context(self.session_id, {
                'role': 'user',
                'content': transcription,
                'timestamp': datetime.now().isoformat()
            })
            append_to_context(self.session_id, {
                'role': 'model',
                'content': response_text,
                'timestamp': datetime.now().isoformat()
            })
            
            return {
                'transcription': transcription,
                'response_text': response_text,
                'response_audio_b64': audio_b64,
                'message_id': ai_message_id,
                'language': detected_lang
            }
        
        finally:
            # Clean up temp file
            try:
                Path(tmp_path).unlink()
            except:
                pass
    
    def process_text_message(self, text: str) -> Dict[str, Any]:
        """
        Process text chat message.
        """
        # Detect language
        from utils.language import detect_text_language
        detected_lang = detect_text_language(text)
        self.current_language = detected_lang
        
        # Get LLM response
        context = get_conversation_context(self.session_id)
        response_text = generate_response(
            text,
            context,
            self.current_language
        )
        
        # Generate message IDs
        user_message_id = str(uuid.uuid4())
        ai_message_id = str(uuid.uuid4())
        
        # Save to database
        save_message(
            session_id=self.session_id,
            role='user',
            message_type='text',
            message_id=user_message_id,
            content=text
        )
        save_message(
            session_id=self.session_id,
            role='model',
            message_type='text',
            message_id=ai_message_id,
            content=response_text
        )
        
        # Save to context
        append_to_context(self.session_id, {
            'role': 'user',
            'content': text,
            'timestamp': datetime.now().isoformat()
        })
        append_to_context(self.session_id, {
            'role': 'model',
            'content': response_text,
            'timestamp': datetime.now().isoformat()
        })
        
        return {
            'response': response_text,
            'message_id': ai_message_id
        }
    
    def cleanup(self):
        """Clean up agent resources."""
        print(f"[CLEANUP] Cleaning up voice agent for {self.session_id}")
        
        # Process any remaining audio before cleanup
        if self.audio_buffer:
            print(f"[CLEANUP] Processing remaining {len(self.audio_buffer)} chunks before cleanup")
            self._process_buffered_audio()
        
        if self._silence_timer:
            self._silence_timer.cancel()
            self._silence_timer = None
        
        with self._lock:
            self._call_active = False
            self.audio_buffer = []
            self.is_streaming = False
