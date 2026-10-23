#!/usr/bin/env python3
"""USHORA AI & TECHNOLOGY - video factory.

  python main.py --mode test            built-in script, no API keys needed
  python main.py --mode real            finds a topic + writes script with Gemini
  python main.py --mode real --upload   also uploads (Plan B; blocked unless enabled in config.yml)
"""
import argparse
import datetime
import json
import os
import pathlib
import shutil
import sys

import yaml

import content
import media

ROOT = pathlib.Path(__file__).resolve().parent
HISTORY = ROOT / "data" / "history.json"


def load_history():
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["test", "real"], default="test")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--fake-tts", action="store_true", help="developer option: beeps instead of speech")
    ap.add_argument("--out", default="out")
    ap.add_argument("--work", default="work")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
    out, work = ROOT / args.out, ROOT / args.work
    for d in (out, work):
        shutil.rmtree(d, ignore_errors=True)
    out.mkdir(parents=True)

    topic = None
    if args.mode == "test":
        print("== TEST MODE: using the built-in Hinglish script ==")
        script = content.sample_script(cfg)
    else:
        print("== REAL MODE: finding a topic and writing the script ==")
        topic, script = content.make_real_script(cfg, load_history())
        print(f"[topic] {topic['title']}")
    script = content.validate_script(script, cfg)

    info = media.build_all(cfg, script, work, out, ROOT, fake_tts=args.fake_tts)

    # ---- metadata ----
    tags = script["tags"]
    hashtags = " ".join("#" + "".join(ch for ch in t if ch.isalnum()) for t in tags[:3] if t)
    desc = script["description"]
    if topic:
        desc += f"\n\nSource / original story: {topic['link']}"
    desc += "\n\n" + cfg["upload"]["description_footer"].strip()
    if hashtags:
        desc += "\n\n" + hashtags
    meta = {"title": script["title"], "description": desc, "tags": tags,
            "thumbnail_text": script["thumbnail_text"], "source": topic["link"] if topic else None,
            "duration_seconds": round(info["duration"], 1), "voice_engines": info["engines"],
            "stock_footage": info["stock"], "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "mode": args.mode}
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    md = (f"## {meta['title']}\n\n**Length:** {meta['duration_seconds']}s | **Voice:** {', '.join(info['engines'])} "
          f"| **Stock footage:** {'yes' if info['stock'] else 'no (cards)'}\n\n"
          f"### Description (copy)\n```\n{desc}\n```\n### Tags (copy)\n```\n{', '.join(tags)}\n```\n")
    (out / "metadata.md").write_text(md, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md)

    # ---- Plan B: upload (heavily guarded) ----
    if args.upload:
        import youtube_upload
        if not cfg["upload"].get("enabled", False):
            print("[upload] SKIPPED: upload.enabled is false in config.yml (this is the safe default).")
        elif not youtube_upload.secrets_present():
            print("[upload] SKIPPED: YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN secrets are missing.")
        else:
            res = youtube_upload.upload(cfg, str(out / "video.mp4"), str(out / "thumbnail.jpg"), meta)
            (out / "upload_result.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    # ---- remember the topic (real mode only) ----
    if args.mode == "real" and topic:
        hist = load_history()
        hist.append({"date": meta["created"][:10], "title": topic["title"], "link": topic["link"]})
        HISTORY.parent.mkdir(exist_ok=True)
        HISTORY.write_text(json.dumps(hist[-300:], ensure_ascii=False, indent=1), encoding="utf-8")

    shutil.rmtree(work, ignore_errors=True)
    print("== DONE ==  files are in:", out)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
  
