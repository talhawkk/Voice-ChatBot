import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv()

# Scopes required
SCOPES = ['https://www.googleapis.com/auth/calendar']

def main():
    creds = None
    # Check if token already exists
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If not valid, log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("🔵 Opening browser for login... Please wait.")
            
            # Configuration for the auth flow
            client_config = {
                "installed": {
                    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                    "project_id": "voice-chatbot",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                    "redirect_uris": ["http://localhost:8080/"]
                }
            }
            
            # Run local server specifically on port 8080
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=8080)
            
        # Save the token
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            print("✅ Success! 'token.json' created.")

if __name__ == '__main__':
    if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
        print("❌ Error: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET missing in .env")
    else:
        main()