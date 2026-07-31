import os, sys, json, io
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

load_dotenv()

YT_CLIENT_ID = os.getenv("YT_CLIENT_ID") or os.getenv("YOUTUBE_CLIENT_ID", "")
YT_CLIENT_SECRET = os.getenv("YT_CLIENT_SECRET") or os.getenv("YOUTUBE_CLIENT_SECRET", "")
YT_REFRESH_TOKEN = os.getenv("YT_REFRESH_TOKEN") or os.getenv("YOUTUBE_REFRESH_TOKEN", "")


def get_authenticated_service():
    if not all([YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN]):
        raise ValueError("Missing YouTube credentials")
    creds = Credentials(
        None, refresh_token=YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET
    )
    creds.refresh(Request())
    service = build("youtube", "v3", credentials=creds)
    service._http.timeout = 600
    return service


def compress_thumbnail(img_path, max_size=2097152):
    img = Image.open(img_path)
    thumb_bytes = io.BytesIO()
    quality = 85
    img.save(thumb_bytes, format="JPEG", quality=quality)
    while thumb_bytes.tell() > max_size and quality > 10:
        quality -= 10
        thumb_bytes = io.BytesIO()
        img.save(thumb_bytes, format="JPEG", quality=quality)
    thumb_bytes.seek(0)
    return thumb_bytes


def upload_to_youtube():
    try:
        meta_path = Path("output") / "latest_video.json"
        if not meta_path.exists():
            print("[youtube] No latest_video.json found")
            return False

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        video_path = Path(meta["video_path"])
        if not video_path.exists():
            print(f"[youtube] Video not found: {video_path}")
            return False

        title = meta.get("title", "").strip()
        if not title:
            title = "Spanish Podcast | Learn Spanish Naturally"
        if len(title) > 97:
            title = title[:94] + "..."
        description = meta.get("description", "")
        if len(description) > 4900:
            description = description[:4900] + "\n\n#LearnSpanish #Spanish #SpanishPodcast"
            print(f"[youtube] Description truncated to {len(description)} chars")
        tags = meta.get("tags", ["Learn Spanish", "Spanish Podcast"])

        print(f"[youtube] Title: '{title[:80]}...' (len={len(title)})")
        print(f"[youtube] Video: {video_path}")

        youtube = get_authenticated_service()

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": "27"
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            }
        }

        media = MediaFileUpload(str(video_path), chunksize=1024*1024*10, resumable=True)
        request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"[youtube] Upload: {int(status.progress() * 100)}%")

        video_id = response["id"]
        print(f"[youtube] Uploaded! ID: {video_id}")
        print(f"[youtube] URL: https://youtube.com/watch?v={video_id}")

        thumbnail_path = Path(meta.get("thumbnail_path", ""))
        print(f"[youtube] Checking thumbnail: {thumbnail_path}")
        if thumbnail_path.exists():
            print(f"[youtube] Thumbnail file found ({thumbnail_path.stat().st_size // 1024}KB)")
            try:
                thumb_bytes = compress_thumbnail(str(thumbnail_path))
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaIoBaseUpload(thumb_bytes, mimetype="image/jpeg", resumable=False)
                ).execute()
                print(f"[youtube] Thumbnail uploaded!")
            except Exception as e:
                print(f"[youtube] Thumbnail upload failed: {e}")
        else:
            print(f"[youtube] Thumbnail NOT FOUND at: {thumbnail_path}")

        result = {
            "video_id": video_id,
            "url": f"https://youtube.com/watch?v={video_id}",
            "title": title,
            "uploaded_at": str(Path(meta_path).stat().st_mtime)
        }
        with open("output/upload_result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"[youtube] Success!")
        return True

    except Exception as e:
        print(f"[youtube] Failed: {e}")
        return False


if __name__ == "__main__":
    success = upload_to_youtube()
    sys.exit(0 if success else 1)
