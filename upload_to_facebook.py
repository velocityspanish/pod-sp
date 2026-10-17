"""
Facebook Page Video Upload Script - SINGLE META API CALL GUARANTEED
Publishes long-form and podcast videos to Facebook Page in exactly 1 direct multipart API call.
Zero chunking sessions, zero status polling loops, zero quota waste.
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()


def safe_print(msg: str):
    """Print message safely across all platforms and Windows code pages."""
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
      1. output/latest_video.json (longform & podcast)
      2. output/latest.json (podcast)
      3. output/longform_videos/* (longform)
      4. output/podcast_* (podcast)
      5. Any recent .mp4 under output/
    """
    import re
    base_dir = Path(__file__).resolve().parent
    search_roots = [base_dir, Path.cwd(), base_dir.parent]

    # 1. Check output/latest_video.json
    for root in search_roots:
        meta_json = root / "output" / "latest_video.json"
        if meta_json.exists():
            try:
                with open(meta_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                v_str = data.get("video_path") or data.get("video")
                if v_str:
                    v_path = Path(v_str)
                    if not v_path.is_absolute():
                        v_path = root / v_path
                    if v_path.exists():
                        t_str = data.get("thumbnail_path") or data.get("thumbnail")
                        t_path = Path(t_str) if t_str else None
                        if t_path and not t_path.is_absolute():
                            t_path = root / t_path
                        if not t_path or not t_path.exists():
                            cand_t = v_path.parent / "thumbnail.jpg"
                            if cand_t.exists():
                                t_path = cand_t
                        info_candidate = v_path.parent / "youtube_upload_info.txt"
                        safe_print(f"[Facebook] Discovered video via latest_video.json: {v_path.name}")
                        return {
                            "dir": v_path.parent,
                            "video": v_path,
                            "thumbnail": t_path if t_path and t_path.exists() else None,
                            "metadata": meta_json,
                            "info": info_candidate if info_candidate.exists() else None,
                            "direct_title": data.get("title") or data.get("selected_title"),
                            "direct_description": data.get("description"),
                            "category": data.get("category_english") or data.get("category")
                        }
            except Exception as e:
                safe_print(f"[Facebook] Notice reading latest_video.json: {e}")

    # 2. Check output/latest.json (podcast generator)
    for root in search_roots:
        latest_json = root / "output" / "latest.json"
        if latest_json.exists():
            try:
                with open(latest_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                v_str = data.get("video") or data.get("video_path")
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
                        safe_print(f"[Facebook] Discovered video via latest.json: {v_path.name}")
                        return {
                            "dir": v_path.parent,
                            "video": v_path,
                            "thumbnail": thumb if thumb.exists() else None,
                            "metadata": latest_json,
                            "direct_title": title,
                            "direct_description": data.get("description")
                        }
            except Exception as e:
                safe_print(f"[Facebook] Notice reading latest.json: {e}")

    # 3. Check output/longform_videos
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
                    safe_print(f"[Facebook] Discovered video in longform folder: {video_file.name}")
                    return {
                        "dir": latest_dir,
                        "video": video_file,
                        "thumbnail": thumbnail_file if thumbnail_file and thumbnail_file.exists() else None,
                        "metadata": metadata_file if metadata_file.exists() else None,
                        "info": info_file if info_file.exists() else None
                    }

    # 4. Check output/podcast_*
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
                        safe_print(f"[Facebook] Discovered video in podcast folder: {v_file.name}")
                        return {
                            "dir": p_dir,
                            "video": v_file,
                            "thumbnail": thumb if thumb.exists() else None,
                            "metadata": p_dir / "latest.json" if (p_dir / "latest.json").exists() else None,
                            "info": p_dir / "youtube_upload_info.txt" if (p_dir / "youtube_upload_info.txt").exists() else None
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
                safe_print(f"[Facebook] Discovered video file fallback: {v_file.name}")
                return {
                    "dir": v_file.parent,
                    "video": v_file,
                    "thumbnail": thumb if thumb.exists() else None,
                    "metadata": None,
                    "info": None
                }

    safe_print("[Facebook] Note: No video file found in output directory")
    return None


def parse_video_metadata(video_info: dict):
    """Extract clean title and description with rich fallbacks."""
    import re
    title = ""
    description = ""
    category = video_info.get("category", "")

    # 1. Direct metadata
    if video_info.get("direct_title"):
        title = video_info["direct_title"].strip()
    if video_info.get("direct_description"):
        description = video_info["direct_description"].strip()

    # 2. Check metadata JSON
    if (not title or not description) and video_info.get("metadata") and Path(video_info["metadata"]).exists():
        try:
            with open(video_info["metadata"], "r", encoding="utf-8") as f:
                meta = json.load(f)
                if not title:
                    title = meta.get("selected_title") or meta.get("title") or meta.get("topic_es") or meta.get("topic") or ""
                if not description:
                    description = meta.get("description", "")
                if not category:
                    category = meta.get("category_english") or meta.get("category") or ""
        except Exception as e:
            safe_print(f"[Facebook] Notice reading metadata JSON: {e}")

    # 3. Check youtube_upload_info.txt
    if (not title or not description) and video_info.get("info") and Path(video_info["info"]).exists():
        try:
            with open(video_info["info"], "r", encoding="utf-8") as f:
                content = f.read()
            if not title:
                m_title = re.search(r"SELECTED TITLE[^\n]*\n[-=\s]+(.+?)(?:\n\s*[-=]{10,}|\Z)", content, re.DOTALL)
                if m_title:
                    cand = m_title.group(1).strip().splitlines()[0].strip()
                    if cand:
                        title = cand
            if not description:
                m_desc = re.search(r"VIDEO DESCRIPTION:[^\n]*\n[-=\s]+(.+?)(?:\n\s*={10,}|\Z)", content, re.DOTALL)
                if m_desc:
                    description = m_desc.group(1).strip()
        except Exception as e:
            safe_print(f"[Facebook] Notice reading info file: {e}")

    # 4. Fallback title
    if not title or title.strip() == "Language Learning Video":
        if category:
            title = f"Daily Lesson: {category} | Essential Phrases"
        else:
            title = "Master Essential Everyday Phrases | Daily Language Practice"

    # 5. Rich fallback description
    if not description or len(description.strip()) < 20:
        cat_topic = category or "Daily Conversation"
        description = (
            f"🌟 {title}\n\n"
            f"Expand your vocabulary and speak naturally! In this lesson, we practice essential phrases covering {cat_topic}.\n\n"
            f"🎯 How to practice:\n"
            f"1. Listen carefully to each phrase\n"
            f"2. Repeat out loud during the pause\n"
            f"3. Practice daily for the best retention\n\n"
            f"🔔 Follow & Subscribe for daily vocabulary lessons!\n"
            f"💬 Let us know what topic you want to learn next in the comments.\n\n"
            f"#LanguageLearning #Vocabulary #DailyLesson #LearnLanguages #Phrases #SpeakNaturally"
        )

    # Trim to Meta Graph API description limit
    if len(description) > 5000:
        description = description[:4950] + "\n\n..."

    return title, description


def upload_to_facebook_page(video_path, title, description, thumbnail_path=None, page_id=None, access_token=None):
    """
    Uploads video to Facebook Page in EXACTLY ONE Meta Graph API call.
    Single direct multipart POST to https://graph-video.facebook.com/v21.0/{page_id}/videos
    Zero chunking sessions, zero status polling loops.
    """
    import requests

    access_token = access_token or os.getenv("FACEBOOK_ACCESS_TOKEN") or os.getenv("FB_ACCESS_TOKEN")
    page_id = page_id or os.getenv("FACEBOOK_PAGE_ID") or os.getenv("FB_PAGE_ID")

    if not access_token or not page_id:
        safe_print("[Facebook] Notice: FACEBOOK_ACCESS_TOKEN or FACEBOOK_PAGE_ID not provided. Skipping upload.")
        return None

    video_path = Path(video_path)
    if not video_path.exists():
        safe_print(f"[Facebook] Error: Video file not found: {video_path}")
        return None

    file_size_mb = video_path.stat().st_size / (1024 * 1024)

    safe_print("\n" + "=" * 60)
    safe_print("FACEBOOK PAGE VIDEO UPLOAD (SINGLE API CALL)")
    safe_print("=" * 60)
    safe_print(f"[Facebook] Page ID: {page_id}")
    safe_print(f"[Facebook] Token: {mask_secret(access_token)}")
    safe_print(f"[Facebook] Video: {video_path.name} ({file_size_mb:.2f} MB)")
    safe_print(f"[Facebook] Title: {title[:75]}...")
    safe_print(f"[Facebook] Description length: {len(description)} chars")
    if thumbnail_path and Path(thumbnail_path).exists():
        safe_print(f"[Facebook] Thumbnail: {Path(thumbnail_path).name}")

    # Meta Graph Video Endpoint (supports up to 1GB direct multipart upload)
    upload_url = f"https://graph-video.facebook.com/v21.0/{page_id}/videos"

    data = {
        "title": title,
        "description": description,
        "published": "true",
        "access_token": access_token
    }

    video_file_obj = None
    thumb_file_obj = None

    try:
        video_file_obj = open(video_path, "rb")
        files = {
            "source": (video_path.name, video_file_obj, "video/mp4")
        }

        if thumbnail_path and Path(thumbnail_path).exists():
            try:
                thumb_file_obj = open(thumbnail_path, "rb")
                files["thumb"] = (Path(thumbnail_path).name, thumb_file_obj, "image/jpeg")
            except Exception as te:
                safe_print(f"[Facebook] Warning opening thumbnail: {te}")

        safe_print(f"[Facebook] Sending single multipart POST request (API Call 1 of 1)...")
        # Single API call with 10-minute timeout for reliable direct upload
        res = requests.post(upload_url, data=data, files=files, timeout=600)

        if res.status_code in [200, 201]:
            res_data = res.json()
            video_id = res_data.get("id")
            if video_id:
                safe_print("\n" + "=" * 60)
                safe_print("SUCCESS: FACEBOOK VIDEO PUBLISHED (EXACTLY 1 API CALL)!")
                safe_print(f"[Facebook] Video ID: {video_id}")
                safe_print(f"[Facebook] Video URL: https://www.facebook.com/{video_id}")
                safe_print("=" * 60)
                return {
                    "success": True,
                    "video_id": video_id,
                    "url": f"https://www.facebook.com/{video_id}",
                    "page_id": page_id,
                    "title": title,
                    "status": "success",
                    "uploaded_at": datetime.now().isoformat(),
                    "api_calls_made": 1
                }

        # If not 200/201, log exact error and return None without retry loops
        safe_print(f"[Facebook] API Response ({res.status_code}): {res.text[:400]}")
        return None

    except requests.exceptions.Timeout:
        safe_print("[Facebook] Upload request timed out (connection too slow or video too large).")
        return None
    except Exception as e:
        safe_print(f"[Facebook] Upload exception: {e}")
        return None
    finally:
        if video_file_obj:
            try:
                video_file_obj.close()
            except Exception:
                pass
        if thumb_file_obj:
            try:
                thumb_file_obj.close()
            except Exception:
                pass


def upload_to_facebook(video_path, description, title="Language Learning Video", thumbnail_path=None):
    """Convenience function for compatibility."""
    return upload_to_facebook_page(
        video_path=video_path,
        title=title,
        description=description,
        thumbnail_path=thumbnail_path
    )


def main():
    """Main CLI entry point for workflow and local execution."""
    access_token = os.getenv("FACEBOOK_ACCESS_TOKEN") or os.getenv("FB_ACCESS_TOKEN")
    page_id = os.getenv("FACEBOOK_PAGE_ID") or os.getenv("FB_PAGE_ID")

    if not access_token or not page_id:
        safe_print("[Facebook] Notice: FACEBOOK_ACCESS_TOKEN or FACEBOOK_PAGE_ID not set. Skipping Facebook upload.")
        return 0

    video_info = get_latest_video()
    if not video_info:
        safe_print("[Facebook] Notice: No video found to upload. Skipping.")
        return 0

    title, description = parse_video_metadata(video_info)
    result = upload_to_facebook_page(
        video_path=video_info["video"],
        title=title,
        description=description,
        thumbnail_path=video_info.get("thumbnail"),
        page_id=page_id,
        access_token=access_token
    )

    if result:
        result_path = video_info["dir"] / "facebook_upload_result.json"
        try:
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            safe_print(f"[Facebook] Saved result to: {result_path}")
        except Exception as e:
            safe_print(f"[Facebook] Warning: Could not save result file: {e}")
        return 0
    else:
        safe_print("[Facebook] Warning: Video upload did not complete. Exiting cleanly to protect workflow.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
