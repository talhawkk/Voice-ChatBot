"""
Edge TTS (Microsoft Edge Neural Voices) - 100% free, no API key required.
Streaming TTS with multi-language support.
"""
import asyncio
import os
from pathlib import Path
from typing import Optional, Generator, Tuple
import edge_tts
import tempfile

# Language to voice mapping
VOICE_MAP = {
    "en": "en-US-AriaNeural",  # Natural English voice
    "ur": "ur-PK-AsadNeural",  # Urdu (Pakistan) - male voice
    "hi": "hi-IN-SwaraNeural",  # Hindi (India) - female voice
}

# Fallback voices if specific language not available
FALLBACK_VOICE = "en-US-AriaNeural"

def get_voice_for_language(lang: str) -> str:
    """Get Edge TTS voice for language."""
    return VOICE_MAP.get(lang, FALLBACK_VOICE)

async def list_voices():
    """List all available Edge TTS voices (for debugging)."""
    voices = await edge_tts.list_voices()
    return voices

async def text_to_speech_stream(text: str, lang: str = "en") -> Generator[bytes, None, None]:
    """
    Stream TTS audio chunks as bytes.
    
    Args:
        text: Text to convert to speech
        lang: Language code ('en', 'ur', 'hi')
    
    Yields:
        Audio chunks as bytes (MP3 format)
    """
    voice = get_voice_for_language(lang)
    
    try:
        communicate = edge_tts.Communicate(text, voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
    except Exception as e:
        raise RuntimeError(f"Edge TTS streaming error: {e}")

async def text_to_speech_file(text: str, output_path: str, lang: str = "en") -> None:
    """
    Convert text to speech and save to file.
    
    Args:
        text: Text to convert
        output_path: Output file path (will be saved as MP3)
        lang: Language code
    """
    voice = get_voice_for_language(lang)
    output_path_obj = Path(output_path)
    
    # Ensure MP3 extension
    if output_path_obj.suffix.lower() != '.mp3':
        output_path = str(output_path_obj.with_suffix('.mp3'))
    
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        
        # Verify file was created
        if not Path(output_path).exists():
            raise RuntimeError(f"TTS file was not created: {output_path}")
        
        file_size = Path(output_path).stat().st_size
        if file_size < 1024:  # Less than 1KB is suspicious
            raise RuntimeError(f"TTS generated suspiciously small file ({file_size} bytes)")
        
        print(f"✅ Generated Edge TTS audio: {output_path} ({file_size} bytes, voice: {voice})")
        
    except Exception as e:
        raise RuntimeError(f"Edge TTS error: {e}")

def text_to_speech_file_sync(text: str, output_path: str, lang: str = "en") -> None:
    """
    Synchronous wrapper for text_to_speech_file.
    """
    asyncio.run(text_to_speech_file(text, output_path, lang))

async def text_to_speech_bytes(text: str, lang: str = "en") -> bytes:
    """
    Convert text to speech and return as bytes.
    
    Args:
        text: Text to convert
        lang: Language code
    
    Returns:
        Audio bytes (MP3 format)
    """
    voice = get_voice_for_language(lang)
    audio_bytes = b""
    
    try:
        communicate = edge_tts.Communicate(text, voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        
        if len(audio_bytes) < 1024:
            raise RuntimeError(f"TTS generated suspiciously small audio ({len(audio_bytes)} bytes)")
        
        return audio_bytes
        
    except Exception as e:
        raise RuntimeError(f"Edge TTS error: {e}")

def text_to_speech_bytes_sync(text: str, lang: str = "en") -> bytes:
    """
    Synchronous wrapper for text_to_speech_bytes.
    """
    return asyncio.run(text_to_speech_bytes(text, lang))
