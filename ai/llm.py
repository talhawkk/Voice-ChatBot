import os
import sys
from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError

# Load env
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    sys.exit("❌ Missing GEMINI_API_KEY. Set it in .env or environment variables.")

# Create client (force stable v1)
client = genai.Client(
    api_key=API_KEY,
    http_options={"api_version": "v1"},
)

# Free-tier friendly model priority (best → fallback)
MODEL_PRIORITY = [
    "models/gemini-2.5-flash-lite",  # best free quota
    "models/gemini-2.0-flash",       # fallback
    "models/gemini-1.5-flash",       # last safe fallback
]

def ask_gemini(prompt: str) -> str:
    last_error = None

    for model_name in MODEL_PRIORITY:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )

            if response and response.text:
                return response.text.strip()

        except APIError as e:
            last_error = e
            # try next model silently
            continue
        except Exception as e:
            last_error = e
            continue

    # If all models fail
    raise RuntimeError(
        f"All Gemini models failed. Last error: {last_error}"
    )

# Local test
if __name__ == "__main__":
    reply = ask_gemini("Hello, how are you?")
    print("Gemini:", reply)
