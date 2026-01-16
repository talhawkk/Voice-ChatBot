import speech_recognition as sr

recognizer = sr.Recognizer()

def speech_to_text(audio_path: str) -> str:
    with sr.AudioFile(audio_path) as source:
        audio = recognizer.record(source)
    try:
        return recognizer.recognize_google(audio)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        return f"[STT error: {e}]"