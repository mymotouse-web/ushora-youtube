"""PLAN B: upload with the official YouTube Data API v3 (resumable upload).

Safety rules built in:
  * Does nothing unless config upload.enabled is true AND the workflow box "upload" is ticked.
  * Default privacy is PRIVATE. "public" is refused unless upload.allow_public is true.
  * Secrets are read from environment variables only and are never printed.
"""
import json
import os
import re
import time

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
THUMB_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"


def secrets_present():
    return all(os.environ.get(k, "").strip() for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def access_token():
    r = requests.post(TOKEN_URL, data={
        "client_id": os.environ["YT_CLIENT_ID"].strip(),
        "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["YT_REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token",
    }, timeout=30)
    if r.status_code != 200:
        try:
            err = r.json()
            msg = f"{err.get('error')}: {err.get('error_description')}"
        except Exception:
            msg = f"HTTP {r.status_code}"
        raise RuntimeError(f"Could not get a YouTube access token ({msg}). "
                           "If it says invalid_grant, the refresh token expired - create a new one.")
    return r.json()["access_token"]


def _clean(s, limit):
    return re.sub(r"[<>]", "", s or "")[:limit]


def upload(cfg, video_path, thumb_path, meta):
    up = cfg["upload"]
    privacy = up.get("privacy", "private")
    if privacy not in ("private", "unlisted", "public"):
        privacy = "private"
    if privacy == "public" and not up.get("allow_public", False):
        print("[upload] 'public' requested but allow_public is false -> using PRIVATE instead.")
        privacy = "private"

    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": bool(up.get("made_for_kids", False)),
        "containsSyntheticMedia": bool(up.get("contains_synthetic_media", False)),
    }
    publish_at = (up.get("publish_at") or "").strip()
    if publish_at:
        status["privacyStatus"] = "private"      # required by YouTube for scheduled publishing
        status["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": _clean(meta["title"], 100),
            "description": _clean(meta["description"], 4900),
            "tags": meta["tags"],
            "categoryId": str(up.get("category_id", "28")),
            "defaultLanguage": up.get("language", "hi"),
            "defaultAudioLanguage": up.get("language", "hi"),
        },
        "status": status,
    }
    token = access_token()
    size = os.path.getsize(video_path)
    auth = {"Authorization": f"Bearer {token}"}

    init = requests.post(UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
                         headers={**auth, "Content-Type": "application/json; charset=UTF-8",
                                  "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
                         data=json.dumps(body), timeout=60)
    if init.status_code != 200:
        raise RuntimeError(f"YouTube refused the upload request (HTTP {init.status_code}): {init.text[:500]}")
    location = init.headers["Location"]

    resp = None
    for attempt in range(4):
        with open(video_path, "rb") as f:
            resp = requests.put(location, data=f, headers={"Content-Type": "video/mp4", "Content-Length": str(size)},
                                timeout=1800)
        if resp.status_code in (200, 201):
            break
        if resp.status_code >= 500:
            time.sleep(10 * (attempt + 1))
            continue
        raise RuntimeError(f"Upload failed (HTTP {resp.status_code}): {resp.text[:500]}")
    if resp is None or resp.status_code not in (200, 201):
        raise RuntimeError("Upload failed after several tries.")
    video_id = resp.json()["id"]

    thumb_ok = False
    try:
        with open(thumb_path, "rb") as f:
            tr = requests.post(THUMB_URL, params={"videoId": video_id}, headers={**auth, "Content-Type": "image/jpeg"},
                               data=f, timeout=120)
        thumb_ok = tr.status_code == 200
        if not thumb_ok:
            print(f"[upload] thumbnail not set (HTTP {tr.status_code}). Custom thumbnails need a phone-verified channel.")
    except Exception as e:
        print(f"[upload] thumbnail step failed: {type(e).__name__}")

    result = {"video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}",
              "privacy": status["privacyStatus"], "thumbnail_set": thumb_ok}
    print("[upload] done:", result["url"], "| privacy:", result["privacy"])
    return result
      
