"""
Set the Velocity Spanish Podcast YouTube channel description (About section).
Run once, or whenever the channel description needs updating.
"""
import os, json
from pathlib import Path
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv()

CHANNEL_DESCRIPTION = """🎙️ Velocity Spanish Podcast - Aprende español de forma natural

Bienvenidos al podcast bilingüe para aprender español. Cada episodio es una conversación sencilla y relajada entre Carlos y María, a nivel A2, perfecta para principiantes.

Welcome to the bilingual Spanish podcast for learning Spanish naturally. Every episode is a simple, relaxed conversation between Carlos and Maria at A2 level - perfect for beginners.

📚 WHAT YOU'LL GET:
• Daily bilingual conversations (Spanish + English)
• Natural pronunciation from native speakers
• Practical vocabulary for everyday life
• Short, easy-to-follow episodes

🇪🇸 How to use this podcast:
1. Listen to the Spanish, try to understand
2. Check the English translation
3. Repeat the phrases out loud
4. Listen again the next day - it gets easier!

🔔 Subscribe and turn on notifications so you never miss a lesson.

📅 New episodes every day!

#LearnSpanish #SpanishPodcast #AprenderEspañol #SpanishForBeginners"""


def _get_creds():
    # 1. Prefer env vars (GitHub Actions)
    cid = os.getenv("YT_CLIENT_ID")
    csecret = os.getenv("YT_CLIENT_SECRET")
    refresh = os.getenv("YT_REFRESH_TOKEN")
    if cid and csecret and refresh:
        return Credentials(None, refresh_token=refresh,
                           token_uri="https://oauth2.googleapis.com/token",
                           client_id=cid, client_secret=csecret)
    # 2. Fallback: local token file (manual local runs)
    tok_file = Path(__file__).parent / "token.json"
    candidates = [
        tok_file,
        Path(r'C:\Users\kreg9\Downloads\kreggscode\open code\bots\youtube refresh tokens bot\token_Velocity Spanish podcast.json'),
    ]
    for c in candidates:
        if c.exists():
            tok = json.load(open(c, encoding='utf-8'))
            return Credentials(None, refresh_token=tok['refresh_token'],
                               token_uri="https://oauth2.googleapis.com/token",
                               client_id=tok['client_id'], client_secret=tok['client_secret'])
    raise ValueError("No YouTube credentials found (set YT_CLIENT_ID/YT_CLIENT_SECRET/YT_REFRESH_TOKEN env or a token.json)")


def main():
    creds = _get_creds()
    creds.refresh(Request())
    service = build("youtube", "v3", credentials=creds)

    # Get current channel
    channels = service.channels().list(part="brandingSettings", mine=True).execute()
    channel_id = channels["items"][0]["id"]
    branding = dict(channels["items"][0]["brandingSettings"])

    # Set description via brandingSettings.channel.description
    branding.setdefault("channel", {})
    branding["channel"]["description"] = CHANNEL_DESCRIPTION
    body = {"id": channel_id, "brandingSettings": branding}
    resp = service.channels().update(part="brandingSettings", body=body).execute()
    new_desc = resp["brandingSettings"]["channel"].get("description", "")
    print("Channel:", channel_id)
    print("Description set to", len(new_desc), "chars")
    print(new_desc[:200])


if __name__ == "__main__":
    main()
