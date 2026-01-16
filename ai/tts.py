import pyttsx3
import threading
import queue
import subprocess
import os

def speak(text: str) -> None:
    """Speak the given text using pyttsx3 asynchronously."""
    def _speak_thread(text_to_speak):
        try:
            # Create a new engine instance each time
            engine = pyttsx3.init()
            
            # Set speech properties
            engine.setProperty('rate', 160)  # Slightly faster
            engine.setProperty('volume', 0.9)
            
            # Speak the text
            engine.say(text_to_speak)
            engine.runAndWait()
            
        except Exception as e:
            print(f"⚠️  TTS Error in thread: {e}")
    
    # Run TTS in a separate thread so it doesn't block the HTTP response
    thread = threading.Thread(target=_speak_thread, args=(text,), daemon=True)
    thread.start()

def text_to_speech_file(text: str, output_path: str, ffmpeg_bin: str = None) -> None:
    """Convert text to speech and save as MP3 file."""
    try:
        # Create engine
        engine = pyttsx3.init()
        
        # Set speech properties
        engine.setProperty('rate', 160)
        engine.setProperty('volume', 0.9)
        
        # Save to temporary WAV first
        temp_wav = output_path.replace('.mp3', '_temp.wav')
        engine.save_to_file(text, temp_wav)
        engine.runAndWait()
        
        # Convert WAV to MP3 using ffmpeg
        if ffmpeg_bin is None:
            ffmpeg_bin = os.getenv("FFMPEG_BIN", "ffmpeg")
        
        try:
            cmd = [
                ffmpeg_bin,
                "-y",
                "-i",
                temp_wav,
                "-acodec",
                "libmp3lame",
                "-ar",
                "22050",
                "-ac",
                "1",
                "-q:a",
                "2",
                output_path,
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Remove temp WAV
            if os.path.exists(temp_wav):
                os.remove(temp_wav)
        except Exception as conv_err:
            # If conversion fails, use WAV format instead
            wav_path = output_path.replace('.mp3', '.wav')
            if os.path.exists(temp_wav):
                if os.path.exists(wav_path):
                    os.remove(wav_path)
                os.rename(temp_wav, wav_path)
            # Update output_path for the caller
            output_path = wav_path
            print(f"⚠️  MP3 conversion failed, using WAV: {conv_err}")
            
    except Exception as e:
        raise RuntimeError(f"TTS Error: Failed to create audio file - {e}")