"""Voice, visuals, subtitles, music, FFmpeg assembly and thumbnail."""
import asyncio
import math
import os
import pathlib
import random
import re
import shutil
import subprocess
import textwrap
import time

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Noto Sans Devanagari is required for Hindi. DejaVu Sans lacks these glyphs
# and silently renders tofu boxes (\u25a1) in Pillow and libass.
FONT_DIR = "/usr/share/fonts/truetype/noto"
FONT_NAME = "Noto Sans Devanagari"
FONT_BOLD = [
    f"{FONT_DIR}/NotoSansDevanagari-Bold.ttf",
    f"{FONT_DIR}/NotoSansDevanagariUI-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]

def _font_path():
    for candidate in FONT_BOLD:
        if os.path.exists(candidate):
            return candidate
    raise RuntimeError("Hindi font missing. Install the fonts-noto-core system package.")


def sh(cmd, cwd=None):
    p = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd[0]}\n{(p.stderr or '')[-1800:]}")
    return p


def ffmpeg(*args, cwd=None):
    return sh(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], cwd=cwd)


def duration(path):
    p = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    return float(p.stdout.strip())


def dims(cfg):
    return (1080, 1920) if cfg["video"].get("orientation") == "portrait" else (1920, 1080)


def font(size):
    path = _font_path()
    # RAQM enables proper shaping of Devanagari conjuncts and vowel marks.
    engine = getattr(ImageFont, "Layout", None)
    layout = engine.RAQM if engine and hasattr(engine, "RAQM") else ImageFont.Layout.BASIC
    return ImageFont.truetype(path, size, layout_engine=layout)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ----------------------------------------------------------------------------
# VOICE
# ----------------------------------------------------------------------------
async def _edge_save(text, voice, rate, pitch, path):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(path)


def tts_edge(text, cfg, path):
    v = cfg["voice"]
    last = None
    for attempt in range(4):
        try:
            asyncio.run(_edge_save(text, v["edge_voice"], v.get("rate", "+0%"), v.get("pitch", "+0Hz"), str(path)))
            if os.path.getsize(path) > 1000:
                return
            last = "empty audio"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"edge-tts failed: {last}")


def tts_espeak(text, cfg, path):
    sh(["espeak-ng", "-v", "hi", "-s", "190", "-w", path, text])


def tts_fake(text, cfg, path):
    d = max(1.5, len(text.split()) * 0.4)
    ffmpeg("-f", "lavfi", "-i", f"sine=frequency=180:duration={d}", path)


def synth_voice(text, cfg, base, fake):
    """Returns (path, engine). Tries engines in order from config."""
    engines = ["fake"] if fake else cfg["voice"].get("engines", ["edge", "espeak"])
    errors = []
    for eng in engines:
        ext = {"edge": ".mp3", "espeak": ".wav", "fake": ".wav"}[eng]
        path = str(base) + ext
        try:
            {"edge": tts_edge, "espeak": tts_espeak, "fake": tts_fake}[eng](text, cfg, path)
            return path, eng
        except Exception as e:
            errors.append(f"{eng}: {str(e)[:200]}")
            print(f"[voice] {eng} failed, trying next engine...")
    raise RuntimeError("All voice engines failed:\n" + "\n".join(errors))


# ----------------------------------------------------------------------------
# VISUALS
# ----------------------------------------------------------------------------
def pexels_clip(query, used, dest, W, H, key):
    orient = "portrait" if H > W else "landscape"
    r = requests.get("https://api.pexels.com/videos/search",
                     params={"query": query, "orientation": orient, "size": "medium", "per_page": 12},
                     headers={"Authorization": key}, timeout=30)
    r.raise_for_status()
    for v in r.json().get("videos", []):
        if v["id"] in used or v.get("duration", 0) < 4:
            continue
        files = [f for f in v.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")]
        good = [f for f in files if min(f["width"], f["height"]) >= 720]
        if not good:
            continue
        f = sorted(good, key=lambda x: x["width"] * x["height"])[0]
        with requests.get(f["link"], stream=True, timeout=60) as resp:
            resp.raise_for_status()
            if int(resp.headers.get("Content-Length", 0)) > 80_000_000:
                continue
            with open(dest, "wb") as out:
                for chunk in resp.iter_content(1 << 20):
                    out.write(chunk)
        used.add(v["id"])
        return dest
    return None


PALETTES = [
    ((8, 12, 40), (40, 12, 90)),       # midnight violet
    ((5, 25, 45), (10, 80, 110)),      # deep ocean
    ((30, 8, 40), (110, 25, 80)),      # magenta dusk
    ((6, 30, 30), (12, 95, 80)),       # emerald circuit
    ((28, 18, 5), (105, 55, 12)),     # amber / bronze
    ((8, 20, 28), (15, 65, 75)),       # arctic teal
    ((24, 8, 18), (92, 24, 45)),      # crimson pulse
    ((14, 18, 38), (48, 65, 105)),    # steel blue
]


def make_card(path, W, H, idx, text, accent):
    w, h = int(W * 1.15), int(H * 1.15)
    c1, c2 = random.choice(PALETTES)
    mid = tuple((a + b) // 2 for a, b in zip(c1, c2))
    g = Image.new("RGB", (2, 2))
    g.putpixel((0, 0), c1); g.putpixel((1, 0), mid); g.putpixel((0, 1), mid); g.putpixel((1, 1), c2)
    img = g.resize((w, h), Image.BILINEAR).convert("RGBA")
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy, r = int(w * (0.25 + 0.5 * ((idx * 37) % 100) / 100)), int(h * 0.4), int(min(w, h) * 0.28)
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=hex_rgb(accent) + (90,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(120)))
    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(grid)
    step = 96
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=(255, 255, 255, 14), width=1)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=(255, 255, 255, 14), width=1)
    img = Image.alpha_composite(img, grid)

    # Pick one of six distinct layouts. Draw only that layout so motifs do not
    # all inherit the same chip/equalizer artwork underneath.
    hud = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hud)
    accent_rgba = hex_rgb(accent) + (170,)
    style = random.randrange(8)
    if style == 0:
        # Processor / circuit-board layout.
        cx, cy = w // 2, int(h * 0.68)
        radius = int(min(w, h) * 0.16)
        for rr, alpha, width in ((radius, 100, 5), (int(radius * 1.28), 65, 3), (int(radius * 1.55), 40, 2)):
            hd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=hex_rgb(accent) + (alpha,), width=width)
        chip = int(radius * 0.72)
        hd.rounded_rectangle([cx-chip, cy-chip, cx+chip, cy+chip], radius=22,
                             outline=accent_rgba, width=7, fill=(5, 15, 35, 150))
        for j in range(8):
            side = -1 if j % 2 == 0 else 1
            yy = cy - chip + (j // 2) * max(1, chip // 2)
            start_x = cx + side * chip
            end_x = start_x + side * int(w * (0.08 + 0.025 * (j % 3)))
            bend_y = yy + (1 if (j + idx) % 2 else -1) * int(h * 0.025)
            hd.line([(start_x, yy), (end_x, yy), (end_x, bend_y)], fill=accent_rgba, width=4)
            hd.ellipse([end_x-7, bend_y-7, end_x+7, bend_y+7], fill=accent_rgba)
        bar_base, bar_w = int(h * 0.87), max(8, int(w * 0.018))
        for j in range(9):
            bh = int(h * (0.018 + 0.012 * ((j * 7 + idx * 3) % 5)))
            bx = int(w * 0.27) + j * int(w * 0.055)
            hd.rounded_rectangle([bx, bar_base-bh, bx+bar_w, bar_base], radius=bar_w//2,
                                 fill=hex_rgb(accent) + (110 + (j % 3) * 40,))
    elif style == 1:
        # Diagonal energy rails and floating data nodes.
        for j in range(6):
            yy = int(h * (0.20 + j * 0.105))
            hd.line([(int(w * 0.08), yy), (int(w * 0.42), yy - int(h * 0.12))],
                    fill=hex_rgb(accent) + (105,), width=5)
            x = int(w * (0.62 + 0.045 * (j % 3)))
            hd.ellipse([x-16, yy-16, x+16, yy+16], fill=accent_rgba)
    elif style == 2:
        # Radar sweep / concentric target.
        rx, ry = int(w * 0.76), int(h * 0.67)
        for rr in (int(min(w,h)*0.10), int(min(w,h)*0.18), int(min(w,h)*0.27)):
            hd.arc([rx-rr, ry-rr, rx+rr, ry+rr], start=205, end=520,
                   fill=hex_rgb(accent) + (145,), width=7)
        hd.line([(rx, ry), (rx-int(w*.18), ry-int(h*.16))], fill=accent_rgba, width=8)
        hd.ellipse([rx-20, ry-20, rx+20, ry+20], fill=(255,255,255,220))
    elif style == 3:
        # Audio waveform bars.
        base = int(h * 0.73)
        for j in range(31):
            x = int(w * 0.12) + j * int(w * 0.025)
            bh = int(h * (0.025 + 0.075 * abs(math.sin((j + idx) * 0.72))))
            hd.rounded_rectangle([x, base-bh, x+max(5,int(w*.009)), base+bh],
                                 radius=8, fill=hex_rgb(accent) + (150,))
    elif style == 4:
        # Hexagonal data mesh.
        step = int(min(w, h) * 0.075)
        for row in range(5):
            for col in range(4):
                x = int(w * 0.16) + col * step + (row % 2) * (step // 2)
                y = int(h * 0.30) + row * step
                rr = max(10, step // 7)
                hd.ellipse([x-rr, y-rr, x+rr, y+rr], outline=accent_rgba, width=5)
                hd.ellipse([x-5, y-5, x+5, y+5], fill=(255,255,255,210))
                if col < 3:
                    hd.line([(x+rr, y), (x+step-rr, y)], fill=hex_rgb(accent)+(95,), width=3)
    elif style == 5:
        # Orbital paths and satellites.
        ox, oy = int(w * 0.70), int(h * 0.62)
        for j, angle in enumerate((0, 45, 90, 135)):
            rr = int(min(w, h) * (0.12 + j * 0.045))
            hd.ellipse([ox-rr, oy-rr//2, ox+rr, oy+rr//2],
                       outline=hex_rgb(accent)+(115,), width=5)
            rad = math.radians(angle + idx * 17)
            sx = ox + int(rr * math.cos(rad))
            sy = oy + int((rr//2) * math.sin(rad))
            hd.ellipse([sx-13, sy-13, sx+13, sy+13], fill=accent_rgba)
    img = Image.alpha_composite(img, hud)
    if text:
        d = ImageDraw.Draw(img)
        fs = int(min(W, H) * (0.082 if idx == 0 else 0.070))
        lines = textwrap.wrap(text.upper(), 13 if H > W else 22)[:3]
        f = font(fs)
        # Alternate title placement to create a deliberate scene-to-scene rhythm.
        if idx % 3 == 1:
            x0, y = int(w * 0.09), int(h * 0.22)
        elif idx % 3 == 2:
            x0, y = int(w * 0.09), int(h * 0.34)
        else:
            x0, y = int(w * 0.10), int(h * 0.27)
        for ln in lines:
            d.text((x0, y), ln, font=f, fill=(255, 255, 255, 245),
                   stroke_width=4, stroke_fill=(0, 0, 0, 175))
            y += int(fs * 1.18)
        d.rounded_rectangle([x0, y + 18, x0 + int(w * 0.34), y + 31],
                            radius=7, fill=hex_rgb(accent) + (255,))
    img.convert("RGB").save(path, quality=92)


def build_segment(visual, kind, dur, W, H, fps, out):
    enc = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(fps)]
    if kind == "clip":
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},"
              "eq=brightness=-0.06,format=yuv420p")
        ffmpeg("-stream_loop", "-1", "-i", visual, "-t", f"{dur:.3f}", "-vf", vf, *enc, out)
    else:
        # Vary camera movement per scene so animated cards do not all move alike.
        motion = random.choice(("zoom_in", "zoom_out", "pan_left", "pan_right"))
        frames = max(1, int(dur * fps))
        if motion == "zoom_out":
            z = "if(eq(on,1),1.08,max(zoom-0.0008,1.0))"
            x = "iw/2-(iw/zoom/2)"
        elif motion == "pan_left":
            z = "1.08"
            x = f"(iw-iw/zoom)*(1-on/{frames})"
        elif motion == "pan_right":
            z = "1.08"
            x = f"(iw-iw/zoom)*on/{frames}"
        else:
            z = "min(zoom+0.0008,1.08)"
            x = "iw/2-(iw/zoom/2)"
        vf = (f"zoompan=z='{z}':x='{x}':y='ih/2-(ih/zoom/2)':"
              f"d=1:s={W}x{H}:fps={fps},format=yuv420p")
        ffmpeg("-loop", "1", "-framerate", str(fps), "-i", visual, "-t", f"{dur:.3f}", "-vf", vf, *enc, out)


def join_visuals(work, timeline, count, fps):
    """Cross-dissolve scene clips while preserving the original total runtime."""
    if count == 1:
        ffmpeg("-i", "seg_00.mp4", "-c", "copy", "video_nosub.mp4", cwd=work)
        return
    transition = 0.35
    args = []
    for i in range(count):
        args += ["-i", f"seg_{i:02d}.mp4"]
    graph = []
    for i in range(count):
        graph.append(f"[{i}:v]settb=AVTB,format=yuv420p[v{i}]")
    previous = "v0"
    elapsed = timeline[0]["total"]
    for i in range(1, count):
        current = f"v{i}"
        if i == count - 1:
            extra = transition * (count - 1)
            graph.append(f"[v{i}]tpad=stop_mode=clone:stop_duration={extra:.3f},settb=AVTB,format=yuv420p[v{i}p]")
            current = f"v{i}p"
        offset = max(0.0, elapsed - transition * i)
        out_label = f"x{i}"
        graph.append(f"[{previous}][{current}]xfade=transition=fade:duration={transition:.3f}:offset={offset:.3f}[{out_label}]")
        previous = out_label
        elapsed += timeline[i]["total"]
    graph.append(f"[{previous}]fade=t=in:st=0:d=0.12,format=yuv420p[vout]")
    ffmpeg(*args, "-filter_complex", ";".join(graph), "-map", "[vout]",
           "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-r", str(fps), "video_nosub.mp4", cwd=work)


# ----------------------------------------------------------------------------
# SUBTITLES
# ----------------------------------------------------------------------------
def chunk_caption(text, max_chars):
    lines = textwrap.wrap(re.sub(r"\s+", " ", text), max_chars) or [""]
    return ["\n".join(lines[i:i + 2]) for i in range(0, len(lines), 2)]


def _ass_t(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _srt_t(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def build_subs(cfg, script, timeline, W, H, ass_path, srt_path, total):
    portrait = H > W
    maxc = cfg["subtitles"]["max_chars_per_line_portrait" if portrait else "max_chars_per_line_landscape"]
    fs = int(min(W, H) * 0.058)
    mv = 420 if portrait else 85
    wm = int(min(W, H) * 0.028)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{FONT_NAME},{fs},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,4,2,2,60,60,{mv},1
Style: Mark,{FONT_NAME},{wm},&H99FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,2,0,9,40,40,35,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    clean = lambda s: s.replace("{", "(").replace("}", ")").replace("\\", "").replace("\n", "\\N")
    ev = [f"Dialogue: 0,{_ass_t(0)},{_ass_t(total)},Mark,,0,0,0,,{clean(cfg['channel']['name'])}"]
    srt = []
    n = 0
    for sc, tl in zip(script["scenes"], timeline):
        chunks = chunk_caption(sc["caption"], maxc)
        weights = [max(len(c.replace("\n", " ")), 1) for c in chunks]
        t = tl["start"] + 0.05
        span = max(tl["speech"] - 0.05, 0.5)
        for c, wgt in zip(chunks, weights):
            d = span * wgt / sum(weights)
            ev.append(f"Dialogue: 1,{_ass_t(t)},{_ass_t(t + d)},Sub,,0,0,0,,{clean(c)}")
            n += 1
            srt.append(f"{n}\n{_srt_t(t)} --> {_srt_t(t + d)}\n{c}\n")
            t += d
    pathlib.Path(ass_path).write_text(header + "\n".join(ev) + "\n", encoding="utf-8")
    pathlib.Path(srt_path).write_text("\n".join(srt), encoding="utf-8")


# ----------------------------------------------------------------------------
# MUSIC (original synthesized pad, or your own licensed mp3 in /music)
# ----------------------------------------------------------------------------
def make_music(cfg, total, out_wav, root):
    mdir = pathlib.Path(root) / "music"
    mp3s = sorted(list(mdir.glob("*.mp3")) + list(mdir.glob("*.wav"))) if mdir.exists() else []
    T = total + 3
    fade = f"afade=t=in:d=2,afade=t=out:st={max(T - 3, 0):.2f}:d=3"
    if mp3s:
        pick = random.choice(mp3s)
        print(f"[music] using your file: {pick.name}")
        ffmpeg("-stream_loop", "-1", "-i", pick, "-t", f"{T:.2f}", "-ar", "44100", "-ac", "2", "-af", fade, out_wav)
        return
    A = "0.5*sin(2*PI*110*t)+0.3*sin(2*PI*164.81*t)+0.25*sin(2*PI*220*t)+0.2*sin(2*PI*261.63*t)"
    F = "0.5*sin(2*PI*87.31*t)+0.3*sin(2*PI*130.81*t)+0.25*sin(2*PI*174.61*t)+0.2*sin(2*PI*220*t)"
    w = "(0.5+0.5*sin(2*PI*t/16))"
    expr = f"0.25*({w}*({A})+(1-{w})*({F}))"
    ffmpeg("-f", "lavfi", "-i", f"aevalsrc=exprs='{expr}':s=44100:d={T:.2f}",
           "-af", f"lowpass=f=1400,aecho=0.8:0.6:700:0.3,{fade}", "-ac", "2", out_wav)


# ----------------------------------------------------------------------------
# THUMBNAIL
# ----------------------------------------------------------------------------
def best_split(words, n):
    """Split words into n lines with the most even length."""
    import itertools
    best = None
    for cuts in itertools.combinations(range(1, len(words)), n - 1):
        parts, prev = [], 0
        for c in list(cuts) + [len(words)]:
            parts.append(" ".join(words[prev:c]))
            prev = c
        score = max(len(p) for p in parts)
        if best is None or score < best[0]:
            best = (score, parts)
    return best[1] if best else [" ".join(words)]


def make_thumbnail(cfg, script, frame_video, out_path, work, bg_image=None):
    TW, TH = 1280, 720
    accent = hex_rgb(cfg["video"].get("accent_color", "#FFC400"))
    if bg_image:
        bg = Image.open(bg_image).convert("RGB")
    else:
        frame = pathlib.Path(work) / "thumb_frame.jpg"
        t = min(2.0, max(duration(frame_video) / 3, 0.2))
        ffmpeg("-ss", f"{t:.2f}", "-i", frame_video, "-frames:v", "1", "-q:v", "2", frame)
        bg = Image.open(frame).convert("RGB")
    s = max(TW / bg.width, TH / bg.height)
    bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1), Image.LANCZOS)
    l, tp = (bg.width - TW) // 2, (bg.height - TH) // 2
    bg = bg.crop((l, tp, l + TW, tp + TH)).convert("RGBA")

    # dark gradient on the left so text is readable
    ov = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for x in range(TW):
        od.line([(x, 0), (x, TH)], fill=(0, 0, 0, int(200 - 140 * x / TW)))
    img = Image.alpha_composite(bg, ov)

    # decorative glowing ring on the right
    ring = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    cx, cy = 1000, 330
    rd.ellipse([cx - 230, cy - 230, cx + 230, cy + 230], outline=accent + (255,), width=16)
    rd.ellipse([cx - 150, cy - 150, cx + 150, cy + 150], outline=(255, 255, 255, 200), width=6)
    rd.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=accent + (255,))
    for ang_x, ang_y in ((cx + 230, cy), (cx - 163, cy - 163), (cx - 163, cy + 163)):
        rd.ellipse([ang_x - 14, ang_y - 14, ang_x + 14, ang_y + 14], fill=(255, 255, 255, 255))
    glow = ring.filter(ImageFilter.GaussianBlur(18))
    img = Image.alpha_composite(img, glow)
    img = Image.alpha_composite(img, ring)
    d = ImageDraw.Draw(img)

    words = script["thumbnail_text"].upper().split() or ["AI"]
    max_w, max_h = int(TW * 0.58), int(TH * 0.64)
    lines, f, size = [" ".join(words)], font(40), 40
    done = False
    for size in range(180, 39, -6):
        f = font(size)
        for n in range(1, min(3, len(words)) + 1):
            cand = best_split(words, n)
            if max(d.textlength(x, font=f) for x in cand) <= max_w and len(cand) * size * 1.12 <= max_h:
                lines, done = cand, True
                break
        if done:
            break
    y = (TH - len(lines) * int(size * 1.12)) // 2 - 25
    for i, ln in enumerate(lines):
        col = accent if i == len(lines) - 1 else (255, 255, 255)
        d.text((60, y), ln, font=f, fill=col, stroke_width=max(6, size // 16), stroke_fill=(0, 0, 0))
        y += int(size * 1.12)

    bf = font(34)
    label = cfg["channel"]["name"]
    bw = int(d.textlength(label, font=bf)) + 50
    d.rounded_rectangle([50, TH - 105, 50 + bw, TH - 45], radius=14, fill=accent)
    d.text((75, TH - 98), label, font=bf, fill=(0, 0, 0))

    rgb = img.convert("RGB")
    for q in (92, 85, 75, 65):
        rgb.save(out_path, "JPEG", quality=q, optimize=True)
        if os.path.getsize(out_path) < 1_900_000:   # YouTube limit is 2 MB
            break


# ----------------------------------------------------------------------------
# MAIN BUILD
# ----------------------------------------------------------------------------
def build_all(cfg, script, work, out, root, fake_tts=False, use_pexels=True):
    work, out = pathlib.Path(work), pathlib.Path(out)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    W, H = dims(cfg)
    fps = int(cfg["video"].get("fps", 30))
    accent = cfg["video"].get("accent_color", "#FFC400")
    pexels_key = os.environ.get("PEXELS_API_KEY", "").strip()
    use_pexels = use_pexels and cfg["visuals"].get("use_pexels", True) and bool(pexels_key)
    print(f"[visuals] stock footage: {'ON' if use_pexels else 'OFF (animated cards)'}")
    scenes = script["scenes"]
    n = len(scenes)

    # 1) voice per scene
    timeline, t0, engines_used = [], 0.0, set()
    for i, sc in enumerate(scenes):
        raw, eng = synth_voice(sc["voice"], cfg, work / f"raw_{i:02d}", fake_tts)
        engines_used.add(eng)
        speech = duration(raw)
        total = speech + (1.2 if i == n - 1 else 0.35)
        wav = work / f"voice_{i:02d}.wav"
        ffmpeg("-i", raw, "-ar", "44100", "-ac", "2", "-af", f"apad=whole_dur={total:.3f}", "-t", f"{total:.3f}", wav)
        total = duration(wav)
        timeline.append({"start": t0, "speech": speech, "total": total})
        t0 += total
        print(f"[voice] scene {i + 1}/{n} via {eng}: {speech:.1f}s")
    total_dur = t0

    # 2) visuals per scene
    used_ids = set()
    first_is_card = True
    for i, sc in enumerate(scenes):
        seg = work / f"seg_{i:02d}.mp4"
        done = False
        if use_pexels:
            try:
                clip = pexels_clip(sc["visual_query"], used_ids, str(work / f"clip_{i:02d}.mp4"), W, H, pexels_key)
                if clip:
                    build_segment(clip, "clip", timeline[i]["total"], W, H, fps, seg)
                    done = True
            except Exception as e:
                print(f"[visuals] scene {i + 1}: stock clip failed ({type(e).__name__}), using card")
        if i == 0:
            first_is_card = not done
        if not done:
            card = work / f"card_{i:02d}.png"
            make_card(card, W, H, i, sc.get("card_text", ""), accent)
            build_segment(str(card), "card", timeline[i]["total"], W, H, fps, seg)
    (work / "segs.txt").write_text("".join(f"file 'seg_{i:02d}.mp4'\n" for i in range(n)))
    (work / "voices.txt").write_text("".join(f"file 'voice_{i:02d}.wav'\n" for i in range(n)))
    join_visuals(work, timeline, n, fps)
    ffmpeg("-f", "concat", "-safe", "0", "-i", "voices.txt", "-c", "copy", "voice.wav", cwd=work)

    # 3) subtitles
    build_subs(cfg, script, timeline, W, H, work / "subs.ass", out / "subtitles.srt", total_dur)

    # 4) music + mix (music ducks under the voice, then loudness-normalised for YouTube)
    if cfg["music"].get("enabled", True):
        make_music(cfg, total_dur, work / "music.wav", root)
        vol = float(cfg["music"].get("volume", 0.10))
        ffmpeg("-i", "voice.wav", "-i", "music.wav", "-filter_complex",
               f"[1:a]volume={vol}[m];[0:a]asplit=2[v][sc];"
               "[m][sc]sidechaincompress=threshold=0.02:ratio=10:attack=20:release=500[duck];"
               "[v][duck]amix=inputs=2:duration=first:dropout_transition=0,volume=2,"
               "loudnorm=I=-16:TP=-1.5:LRA=11[a]",
               "-map", "[a]", "-ar", "44100", "-ac", "2", "mix.wav", cwd=work)
    else:
        ffmpeg("-i", "voice.wav", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "mix.wav", cwd=work)

    # 5) final render: burn subtitles + watermark, encode
    ffmpeg("-i", "video_nosub.mp4", "-i", "mix.wav",
           "-vf", f"ass=subs.ass:fontsdir={FONT_DIR}",
           "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
           "-shortest", str(out / "video.mp4"), cwd=work)

    # 6) thumbnail
    bg = None
    if first_is_card:   # textless card so the headline is not printed twice
        bg = str(work / "thumb_bg.png")
        make_card(bg, W, H, 0, "", accent)
    make_thumbnail(cfg, script, str(work / "video_nosub.mp4"), str(out / "thumbnail.jpg"), work, bg_image=bg)
    return {"duration": total_dur, "engines": sorted(engines_used), "stock": use_pexels}
