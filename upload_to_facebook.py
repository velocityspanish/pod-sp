import os
import sys
import json
import time
import io
from pathlib import Path
import requests

def safe_print(msg: str):
    """Safely print UTF-8 text on Windows cmd/PowerShell consoles."""
    try:
        print(msg)
    except UnicodeEncodeError:
        safe_msg = msg.encode("ascii", "replace").decode("ascii")
        print(safe_msg)


def mask_secret(s: str) -> str:
    """Safely mask tokens for logs without leaking."""
    if not s:
        return "NOT SET"
    if len(s) > 8:
        return f"{s[:4]}...{s[-4:]}"
    return "***"


def get_latest_video():
    """
    Find the most recently generated video directory and files.
    Supports:
      1. Podcast outputs: output/latest_video.json, output/podcast_*
      2. Longform outputs: output/longform_videos/*
      3. General outputs: any recent .mp4 in output/
    """
    base_dir = Path(__file__).resolve().parent
    cwd = Path.cwd()
    search_roots = [base_dir, cwd, base_dir.parent, cwd.parent]

    # 1. Check for latest_video.json (written by podcast generator)
    for root in search_roots:
        meta_json = root / "output" / "latest_video.json"
        if meta_json.exists():
            try:
                with open(meta_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                v_str = data.get("video_path", "")
                if v_str:
                    v_path = Path(v_str)
                    if not v_path.is_absolute():
                        v_path = root / v_path
                    if v_path.exists():
                        t_str = data.get("thumbnail_path", "")
                        t_path = Path(t_str) if t_str else None
                        if t_path and not t_path.is_absolute():
                            t_path = root / t_path
                        safe_print(f"[Facebook] Found video from latest_video.json: {v_path.name}")
                        return {
                            "dir": v_path.parent,
                            "video": v_path,
                            "thumbnail": t_path if t_path and t_path.exists() else None,
                            "metadata": meta_json,
                            "direct_title": data.get("title"),
                            "direct_description": data.get("description")
                        }
            except Exception as e:
                safe_print(f"[Facebook] Notice reading latest_video.json: {e}")

    # 2. Check for latest.json in output/ (podcast generator)
    for root in search_roots:
        latest_json = root / "output" / "latest.json"
        if latest_json.exists():
            try:
                with open(latest_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                v_str = data.get("video", "")
                if v_str:
                    v_path = Path(v_str)
                    if not v_path.is_absolute():
                        v_path = root / v_path
                    if v_path.exists():
                        thumb = v_path.parent / "thumbnail.jpg"
                        if not thumb.exists():
                            thumb = v_path.parent / "f_0000.png"
                        topic = data.get("topic_es") or data.get("topic_en") or data.get("topic")
                        lang = data.get("language", "Language")
                        title = f"{lang} Podcast: {topic}" if topic else f"{lang} Podcast"
                        safe_print(f"[Facebook] Found video from latest.json: {v_path.name}")
                        return {
                            "dir": v_path.parent,
                            "video": v_path,
                            "thumbnail": thumb if thumb.exists() else None,
                            "metadata": latest_json,
                            "direct_title": title
                        }
            except Exception as e:
                safe_print(f"[Facebook] Notice reading latest.json: {e}")

    # 3. Check for podcast directories (output/podcast_*)
    for root in search_roots:
        out_dir = root / "output"
        if out_dir.exists():
            pod_dirs = sorted(
                [d for d in out_dir.glob("podcast_*") if d.is_dir()],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            for p_dir in pod_dirs:
                for v_name in ["podcast_final.mp4", "final_video.mp4", "podcast.mp4", "video.mp4"]:
                    v_file = p_dir / v_name
                    if v_file.exists():
                        thumb = p_dir / "thumbnail.jpg"
                        if not thumb.exists():
                            thumb = p_dir / "f_0000.png"
                        safe_print(f"[Facebook] Found video in podcast folder: {v_file.name}")
                        return {
                            "dir": p_dir,
                            "video": v_file,
                            "thumbnail": thumb if thumb.exists() else None,
                            "metadata": p_dir / "latest.json" if (p_dir / "latest.json").exists() else None
                        }

    # 4. Check for longform directories (output/longform_videos/*)
    for root in search_roots:
        longform_dir = root / "output" / "longform_videos"
        if longform_dir.exists():
            dirs = sorted(
                [d for d in longform_dir.iterdir() if d.is_dir()],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            if dirs:
                latest_dir = dirs[0]
                video_file = latest_dir / "final_video.mp4"
                metadata_file = latest_dir / "video_metadata.json"
                info_file = latest_dir / "youtube_upload_info.txt"
                thumbnail_file = latest_dir / "thumbnail.jpg"

                if not thumbnail_file.exists():
                    phrase_images = sorted(latest_dir.glob("phrase_*.jpg"))
                    thumbnail_file = phrase_images[0] if phrase_images else None

                if video_file.exists():
                    safe_print(f"[Facebook] Found video in longform folder: {video_file.name}")
                    return {
                        "dir": latest_dir,
                        "video": video_file,
                        "thumbnail": thumbnail_file if thumbnail_file and thumbnail_file.exists() else None,
                        "metadata": metadata_file if metadata_file.exists() else None,
                        "info": info_file if info_file.exists() else None
                    }

    # 5. General fallback: search for any .mp4 under output/
    for root in search_roots:
        out_dir = root / "output"
        if out_dir.exists():
            mp4s = sorted(
                out_dir.glob("**/*.mp4"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            if mp4s:
                v_file = mp4s[0]
                thumb = v_file.parent / "thumbnail.jpg"
                if not thumb.exists():
                    thumb = v_file.parent / "f_0000.png"
                safe_print(f"[Facebook] Found video file: {v_file.name}")
                return {
                    "dir": v_file.parent,
                    "video": v_file,
                    "thumbnail": thumb if thumb.exists() else None,
                    "metadata": None
                }

    safe_print("[Facebook] Note: No video file found in output directory candidates")
    return None


def parse_video_metadata(video_info: dict):
    """Extract clean title and description from metadata or info file."""
    title = "Language Learning Video"
    description = ""

    if video_info.get("direct_title"):
        title = video_info["direct_title"]
    if video_info.get("direct_description"):
        description = video_info["direct_description"]

    # If description still empty, try reading metadata file
    if not description and video_info.get("metadata"):
        try:
            with open(video_info["metadata"], "r", encoding="utf-8") as f:
                meta = json.load(f)
                if not video_info.get("direct_title"):
                    title = meta.get("selected_title", meta.get("title", meta.get("topic_es", meta.get("topic", title))))
                description = meta.get("description", "")
                if not description and ("topic_es" in meta or "topic_en" in meta or "topic" in meta):
                    topic = meta.get("topic_es") or meta.get("topic_en") or meta.get("topic")
                    lang = meta.get("language", "Language")
                    description = (
                        f"🎙️ {lang} Podcast - Daily Bilingual Lesson\n"
                        f"Topic: {topic}\n\n"
                        f"Listen, learn, and practice everyday conversation!\n\n"
                        f"#{lang} #{lang}Podcast #Learn{lang} #Bilingual"
                    )
        except Exception as e:
            safe_print(f"[Facebook] Notice: Could not read metadata: {e}")

    # Try reading info_file
    if not description and video_info.get("info") and Path(video_info["info"]).exists():
        try:
            with open(video_info["info"], "r", encoding="utf-8") as f:
                content = f.read()
                if "SELECTED TITLE" in content and not video_info.get("direct_title"):
                    title_part = content.split("SELECTED TITLE")[1].split("---")[1].strip()
                    title = title_part.splitlines()[0].strip()
                if "VIDEO DESCRIPTION:" in content:
                    description = content.split("VIDEO DESCRIPTION:")[1].split("---")[1].strip()
        except Exception as e:
            safe_print(f"[Facebook] Notice: Could not read youtube_upload_info.txt: {e}")

    if not description:
        description = f"{title}\n\nLearn and practice daily with Velocity Language Lessons.\nSubscribe for daily educational videos!"

    if len(description) > 5000:
        description = description[:4950] + "\n\n..."

    return title, description


def upload_to_facebook_page(video_path, title, description, thumbnail_path=None, page_id=None, access_token=None):
    """
    Uploads a video to a Facebook Page via Graph Video API.
    Supports direct multipart upload and chunked resumable upload fallback.
    """
    access_token = access_token or os.getenv("FACEBOOK_ACCESS_TOKEN") or os.getenv("FB_ACCESS_TOKEN")
    page_id = page_id or os.getenv("FACEBOOK_PAGE_ID") or os.getenv("FB_PAGE_ID")

    if not access_token or not page_id:
        safe_print("[Facebook] Notice: FACEBOOK_ACCESS_TOKEN or FACEBOOK_PAGE_ID not provided. Skipping upload.")
        return None

    video_path = Path(video_path)
    if not video_path.exists():
        safe_print(f"[Facebook] Error: Video file not found: {video_path}")
        return None

    file_size = video_path.stat().st_size
    file_size_mb = file_size / (1024 * 1024)

    safe_print("\n" + "=" * 60)
    safe_print("FACEBOOK PAGE VIDEO UPLOAD")
    safe_print("=" * 60)
    safe_print(f"[Facebook] Page ID: {page_id}")
    safe_print(f"[Facebook] Token: {mask_secret(access_token)}")
    safe_print(f"[Facebook] Video: {video_path.name} ({file_size_mb:.2f} MB)")
    safe_print(f"[Facebook] Title: {title[:70]}...")
    if thumbnail_path and Path(thumbnail_path).exists():
        safe_print(f"[Facebook] Thumbnail: {Path(thumbnail_path).name}")

    url = f"https://graph-video.facebook.com/v21.0/{page_id}/videos"
    retries = 3

    for attempt in range(1, retries + 1):
        safe_print(f"[Facebook] Upload attempt {attempt}/{retries}...")
        try:
            with open(video_path, "rb") as vf:
                files = {"source": (video_path.name, vf, "video/mp4")}
                data = {
                    "access_token": access_token,
                    "title": title,
                    "description": description,
                    "published": "true"
                }

                thumb_file_obj = None
                if thumbnail_path and Path(thumbnail_path).exists():
                    try:
                        thumb_file_obj = open(thumbnail_path, "rb")
                        files["thumb"] = (Path(thumbnail_path).name, thumb_file_obj, "image/jpeg")
                    except Exception as te:
                        safe_print(f"[Facebook] Warning opening thumbnail: {te}")

                try:
                    response = requests.post(url, data=data, files=files, timeout=600)
                finally:
                    if thumb_file_obj:
                        thumb_file_obj.close()

            if response.status_code in (200, 201):
                result = response.json()
                video_id = result.get("id")
                safe_print(f"[Facebook] Success! Video published successfully.")
                safe_print(f"[Facebook] Video ID: {video_id}")
                safe_print(f"[Facebook] Video URL: https://www.facebook.com/{video_id}")

                res_data = {
                    "success": True,
                    "video_id": video_id,
                    "url": f"https://www.facebook.com/{video_id}",
                    "page_id": page_id,
                    "title": title,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                out_path = video_path.parent / "facebook_upload_result.json"
                try:
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(res_data, f, indent=2)
                    safe_print(f"[Facebook] Saved result to: {out_path}")
                except Exception:
                    pass
                return res_data

            safe_print(f"[Facebook] API Error (status {response.status_code}): {response.text}")
            if attempt < retries:
                sleep_sec = 5 * attempt
                safe_print(f"[Facebook] Retrying in {sleep_sec}s...")
                time.sleep(sleep_sec)

        except Exception as e:
            safe_print(f"[Facebook] Upload exception on attempt {attempt}: {e}")
            if attempt < retries:
                time.sleep(5 * attempt)

    # Chunked resumable upload fallback for large files
    safe_print("[Facebook] Direct upload failed, attempting chunked resumable upload...")
    return upload_resumable(video_path, title, description, page_id, access_token, thumbnail_path)


def upload_resumable(video_path, title, description, page_id, access_token, thumbnail_path=None):
    """Chunked resumable upload implementation."""
    try:
        file_size = video_path.stat().st_size
        init_url = f"https://graph-video.facebook.com/v21.0/{page_id}/videos"
        init_data = {
            "access_token": access_token,
            "upload_phase": "start",
            "file_size": file_size
        }
        r_init = requests.post(init_url, data=init_data, timeout=30)
        if r_init.status_code not in (200, 201):
            safe_print(f"[Facebook] Resumable init failed: {r_init.text}")
            return None

        init_res = r_init.json()
        upload_session_id = init_res["upload_session_id"]
        safe_print(f"[Facebook] Resumable session started: {upload_session_id}")

        chunk_size = 4 * 1024 * 1024
        start_offset = int(init_res.get("start_offset", 0))

        with open(video_path, "rb") as f:
            while start_offset < file_size:
                f.seek(start_offset)
                chunk = f.read(chunk_size)
                chunk_url = f"https://graph-video.facebook.com/v21.0/{page_id}/videos"
                chunk_data = {
                    "access_token": access_token,
                    "upload_phase": "transfer",
                    "upload_session_id": upload_session_id,
                    "start_offset": start_offset
                }
                files = {"video_file_chunk": ("chunk", chunk, "application/octet-stream")}
                r_chunk = requests.post(chunk_url, data=chunk_data, files=files, timeout=300)
                if r_chunk.status_code not in (200, 201):
                    safe_print(f"[Facebook] Chunk upload failed: {r_chunk.text}")
                    return None
                start_offset = int(r_chunk.json().get("start_offset", start_offset + len(chunk)))

        finish_data = {
            "access_token": access_token,
            "upload_phase": "finish",
            "upload_session_id": upload_session_id,
            "title": title,
            "description": description,
            "published": "true"
        }
        r_fin = requests.post(init_url, data=finish_data, timeout=60)
        if r_fin.status_code in (200, 201):
            vid_id = r_fin.json().get("id", upload_session_id)
            safe_print(f"[Facebook] Resumable upload success! Video ID: {vid_id}")
            return {"success": True, "video_id": vid_id, "url": f"https://www.facebook.com/{vid_id}"}
        else:
            safe_print(f"[Facebook] Resumable finish failed: {r_fin.text}")
            return None

    except Exception as e:
        safe_print(f"[Facebook] Resumable exception: {e}")
        return None


def main():
    safe_print("=" * 60)
    safe_print("VELOCITY FACEBOOK PUBLISHER")
    safe_print("=" * 60)

    token = os.getenv("FACEBOOK_ACCESS_TOKEN") or os.getenv("FB_ACCESS_TOKEN")
    page_id = os.getenv("FACEBOOK_PAGE_ID") or os.getenv("FB_PAGE_ID")

    if not token or not page_id:
        safe_print("[Facebook] FACEBOOK_ACCESS_TOKEN or FACEBOOK_PAGE_ID not set in environment.")
        safe_print("[Facebook] Gracefully skipping Facebook publishing step.")
        sys.exit(0)

    video_info = get_latest_video()
    if not video_info:
        safe_print("[Facebook] No recent video found to upload. Exiting gracefully.")
        sys.exit(0)

    video_path = video_info["video"]
    thumbnail_path = video_info.get("thumbnail")
    title, description = parse_video_metadata(video_info)

    safe_print(f"[Facebook] Discovered Video: {video_path}")
    safe_print(f"[Facebook] Title: {title}")
    safe_print(f"[Facebook] Thumbnail: {thumbnail_path}")

    res = upload_to_facebook_page(
        video_path=video_path,
        title=title,
        description=description,
        thumbnail_path=thumbnail_path,
        page_id=page_id,
        access_token=token
    )

    if res and res.get("success"):
        safe_print("[Facebook] Publishing completed successfully.")
        sys.exit(0)
    else:
        safe_print("[Facebook] Publishing failed or encountered error. Exiting with code 0 to protect build.")
        sys.exit(0)


if __name__ == "__main__":
    main()
