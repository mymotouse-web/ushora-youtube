"""Topic discovery + Hinglish script writing (Gemini free tier) + built-in test script."""
import calendar
import html
import json
import math
import os
import re
import time
from html.parser import HTMLParser

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; UshoraBot/1.0)"}
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


# ----------------------------------------------------------------------------
# Built-in test script (evergreen, no news facts -> safe for the first test run)
# ----------------------------------------------------------------------------
def sample_script(cfg):
    spoken = cfg["channel"]["spoken_name"]
    return {
        "title": "AI Kaise Seekhta Hai? Simple Hinglish Mein",
        "description": "AI kaise seekhta hai? Is test video mein hum bilkul aasaan Hinglish mein samajhte hain "
                       "ki machine learning aur training ka basic idea kya hota hai.",
        "tags": ["AI", "Artificial Intelligence", "Machine Learning", "Hinglish", "Technology",
                 "AI kya hai", "USHORA"],
        "thumbnail_text": "AI KAISE SEEKHTA HAI?",
        "scenes": [
            {"voice": "नमस्ते दोस्तों! क्या आपने कभी सोचा है कि AI आखिर सीखता कैसे है?",
             "caption": "Namaste doston! Kya aapne kabhi socha hai ki AI aakhir seekhta kaise hai?",
             "visual_query": "artificial intelligence neural network", "card_text": "AI KAISE SEEKHTA HAI?"},
            {"voice": f"आप देख रहे हैं {spoken}, और आज हम इसे बिल्कुल आसान भाषा में समझेंगे।",
             "caption": "Aap dekh rahe hain USHORA AI & TECHNOLOGY, aur aaj hum ise bilkul aasaan bhasha mein samjhenge.",
             "visual_query": "technology futuristic digital", "card_text": "USHORA AI & TECHNOLOGY"},
            {"voice": "AI इंसानों की तरह किताबें नहीं पढ़ता। वो बहुत सारे उदाहरण, यानी डेटा देखता है।",
             "caption": "AI insaano ki tarah kitaabein nahi padhta. Woh bahut saare udaaharan, yaani data dekhta hai.",
             "visual_query": "data center server lights", "card_text": "DATA = EXAMPLES"},
            {"voice": "जैसे आप किसी बच्चे को हज़ार बिल्लियों की फ़ोटो दिखाओ, तो वो धीरे-धीरे बिल्ली पहचानना सीख जाता है।",
             "caption": "Jaise aap kisi bachche ko hazaar billiyon ki photo dikhao, toh woh dheere-dheere billi pehchaanna seekh jaata hai.",
             "visual_query": "cat portrait", "card_text": "1000 BILLIYON KI PHOTO"},
            {"voice": "AI भी यही करता है। बस फ़र्क़ ये है कि वो लाखों उदाहरण बहुत तेज़ी से देख लेता है।",
             "caption": "AI bhi yahi karta hai. Bas farq ye hai ki woh lakhon udaaharan bahut tezi se dekh leta hai.",
             "visual_query": "computer code screen", "card_text": "LAKHON EXAMPLES"},
            {"voice": "हर बार गलती करने पर उसके अंदर के नंबर थोड़े बदलते हैं, और अगली बार जवाब बेहतर हो जाता है। इसे ट्रेनिंग कहते हैं।",
             "caption": "Har baar galti karne par uske andar ke numbers thode badalte hain, aur agli baar jawab behtar ho jaata hai. Ise training kehte hain.",
             "visual_query": "abstract technology network", "card_text": "TRAINING"},
            {"voice": "लेकिन ध्यान रखिए, AI कभी-कभी गलत भी हो सकता है। इसलिए हर जवाब को जाँच कर ही इस्तेमाल करें।",
             "caption": "Lekin dhyaan rakhiye, AI kabhi-kabhi galat bhi ho sakta hai. Isliye har jawab ko jaanch kar hi istemaal karein.",
             "visual_query": "person thinking laptop", "card_text": "JAANCH KARO"},
            {"voice": "अगर ये वीडियो आपको पसंद आया, तो चैनल को सब्सक्राइब करें और कमेंट में बताइए कि अगला टॉपिक क्या होना चाहिए।",
             "caption": "Agar ye video aapko pasand aaya, toh channel ko subscribe karein aur comment mein bataiye ki agla topic kya hona chahiye.",
             "visual_query": "technology abstract blue", "card_text": "SUBSCRIBE"},
        ],
    }


# ----------------------------------------------------------------------------
# Topic discovery (RSS + Hacker News), all free, no keys
# ----------------------------------------------------------------------------
def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def fetch_candidates(cfg, history):
    import feedparser

    tcfg = cfg["topics"]
    seen_links = {h.get("link") for h in history}
    seen_titles = {_norm(h.get("title")) for h in history}
    keywords = [k.lower() for k in tcfg.get("keywords", [])]
    max_age = tcfg.get("max_age_days", 5) * 86400
    now = time.time()
    cands = []

    def add(title, link, summary, ts, bonus=0.0):
        if not title or not link or link in seen_links or _norm(title) in seen_titles:
            return
        text = f"{title} {summary}".lower()
        hits = sum(1 for k in keywords if k in text)
        age = now - ts if ts else max_age
        if age > max_age:
            return
        score = hits * 2 + bonus + max(0.0, 3.0 - age / 86400.0)
        cands.append({"title": _clean(title), "link": link, "summary": _clean(summary)[:900], "score": score})

    for url in tcfg.get("feeds", []):
        try:
            r = requests.get(url, headers=UA, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            for e in feed.entries[:15]:
                t = e.get("published_parsed") or e.get("updated_parsed")
                ts = calendar.timegm(t) if t else None
                add(e.get("title"), e.get("link"), e.get("summary", ""), ts)
        except Exception as ex:  # one broken feed must not stop the system
            print(f"[topics] skipped feed {url}: {type(ex).__name__}")

    if tcfg.get("use_hacker_news", True):
        try:
            r = requests.get("https://hn.algolia.com/api/v1/search",
                             params={"tags": "front_page", "hitsPerPage": 40}, headers=UA, timeout=20)
            r.raise_for_status()
            for h in r.json().get("hits", []):
                if h.get("url"):
                    ts = h.get("created_at_i")
                    add(h.get("title"), h["url"], "", ts, bonus=math.log10(max(h.get("points", 1), 1)))
        except Exception as ex:
            print(f"[topics] skipped Hacker News: {type(ex).__name__}")

    # Hacker News items without keyword hits are not useful -> require some relevance
    cands = [c for c in cands if c["score"] >= 2.5]
    cands.sort(key=lambda c: c["score"], reverse=True)
    return cands[:10]


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._skip, self._in_p = [], 0, False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "nav", "footer", "header"):
            self._skip += 1
        if tag == "p":
            self._in_p = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "nav", "footer", "header"):
            self._skip = max(0, self._skip - 1)
        if tag == "p":
            self._in_p = False

    def handle_data(self, data):
        if self._in_p and not self._skip and len(data.strip()) > 40:
            self.parts.append(data.strip())


def fetch_article_text(url, fallback):
    try:
        r = requests.get(url, headers=UA, timeout=25)
        r.raise_for_status()
        p = _TextExtractor()
        p.feed(r.text)
        text = " ".join(p.parts)
        if len(text) > 400:
            return text[:5000]
    except Exception as ex:
        print(f"[topics] could not read article page: {type(ex).__name__}")
    return fallback


# ----------------------------------------------------------------------------
# Gemini (free tier) helpers. The API key is sent in a header, never printed.
# ----------------------------------------------------------------------------
def _discover_model(key):
    r = requests.get(f"{GEMINI_BASE}/models", headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=30)
    r.raise_for_status()
    ok = []
    for m in r.json().get("models", []):
        name = m.get("name", "").replace("models/", "")
        if "flash" in name and "generateContent" in m.get("supportedGenerationMethods", []):
            bad = any(x in name for x in ("image", "tts", "live", "audio", "lite", "robotics", "embedding"))
            ok.append((bad, "preview" in name or "exp" in name, name))
    ok.sort()
    if not ok:
        raise RuntimeError("No usable Gemini Flash model found for this API key.")
    print(f"[llm] auto-selected model: {ok[0][2]}")
    return ok[0][2]


def gemini_json(cfg, prompt, temperature=0.8):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY secret is missing. Add it in GitHub > Settings > Secrets, "
                           "or run mode 'test' which needs no keys.")
    model = cfg["llm"]["model"]
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"}}
    last = ""
    for attempt in range(5):
        r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent",
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                          json=body, timeout=180)
        if r.status_code == 404:
            model = _discover_model(key)
            continue
        if r.status_code in (429, 500, 503):
            last = f"HTTP {r.status_code}"
            time.sleep(15 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise RuntimeError(f"Gemini error HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            raise RuntimeError(f"Gemini returned no text: {str(data)[:300]}")
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            a, b = text.find("{"), text.rfind("}")
            return json.loads(text[a:b + 1])
    raise RuntimeError(f"Gemini kept failing ({last}). Free-tier limit may be reached; try again later.")


def make_real_script(cfg, history):
    cands = fetch_candidates(cfg, history)
    if not cands:
        raise RuntimeError("No fresh topics found. Try increasing topics.max_age_days in config.yml.")
    listing = "\n".join(f"{i}. {c['title']} -- {c['summary'][:200]}" for i, c in enumerate(cands))
    pick = gemini_json(cfg, (
        f"You are the editor of a Hinglish YouTube channel for {cfg['channel']['audience']}.\n"
        "Choose ONE story below that is most interesting, useful or surprising for them. "
        "Avoid rumours, politics, and anything sensitive or unverified.\n"
        f"{listing}\n\nReturn JSON: {{\"index\": <number>, \"reason\": \"<short>\"}}"), temperature=0.3)
    idx = int(pick.get("index", 0))
    topic = cands[idx if 0 <= idx < len(cands) else 0]
    article = fetch_article_text(topic["link"], topic["summary"])
    words = int(cfg["video"].get("target_minutes", 3) * 130)

    prompt = f"""You write scripts for the YouTube channel "{cfg['channel']['name']}" ({cfg['channel']['audience']}).
Narrator: a friendly, confident male presenter speaking natural Hinglish (Hindi + common English tech words).

SOURCE ARTICLE (facts you may use):
Title: {topic['title']}
Text: {article}

RULES
- Write an ORIGINAL explanation in your own words. Do not copy sentences from the source.
- Use ONLY facts present in the source text. Do not invent numbers, dates, names or quotes.
  If unsure, say "reports ke mutabik" (according to reports).
- Start with a strong hook in the first 5 seconds. End with a short call to action and a question for comments.
- About {words} spoken words in total, split into 10-16 short scenes (each scene = 1-2 short sentences, max 28 words).
- "voice": what the narrator says. Write Hindi words in DEVANAGARI script and keep English tech terms (AI, chip, app) in Latin letters.
  Spell out symbols (write "प्रतिशत", not "%").
- "caption": the SAME sentence written in ROMAN Hinglish for subtitles.
- "visual_query": 2-4 English words for stock video search (generic, safe, e.g. "server room", "smartphone screen").
- "card_text": 2-4 word ALL-CAPS Roman label for the on-screen card.
- "thumbnail_text": 2-5 word ALL-CAPS Roman Hinglish hook, no clickbait lies.
- "title": under 70 characters, Roman Hinglish/English, honest. No angle brackets.
- "description": 3-5 lines Roman Hinglish summary. Do not add links.
- "tags": 8-12 relevant tags.

Return ONLY JSON:
{{"title": "...", "description": "...", "tags": ["..."], "thumbnail_text": "...",
  "scenes": [{{"voice": "...", "caption": "...", "visual_query": "...", "card_text": "..."}}]}}"""
    script = gemini_json(cfg, prompt, temperature=0.8)
    return topic, script


# ----------------------------------------------------------------------------
def validate_script(script, cfg):
    spoken = cfg["channel"]["spoken_name"]
    if not isinstance(script, dict) or not script.get("scenes"):
        raise RuntimeError("Script has no scenes.")
    scenes = []
    for s in script["scenes"]:
        voice = str(s.get("voice", "")).replace("{channel_spoken}", spoken).strip()
        caption = str(s.get("caption", "")).strip()
        if not voice:
            continue
        scenes.append({
            "voice": voice,
            "caption": caption or voice,
            "visual_query": str(s.get("visual_query") or "technology").strip(),
            "card_text": str(s.get("card_text") or "").strip()[:40],
        })
    if len(scenes) < 3:
        raise RuntimeError("Script too short (fewer than 3 usable scenes).")
    strip_ang = lambda x: re.sub(r"[<>]", "", str(x))
    tags, total = [], 0
    for t in script.get("tags", []):
        t = strip_ang(t).strip()
        if t and total + len(t) + 1 < 450:
            tags.append(t)
            total += len(t) + 1
    thumb = strip_ang(script.get("thumbnail_text") or script.get("title", "AI NEWS")).upper().split()
    return {
        "title": strip_ang(script.get("title", "AI & Tech Update")).strip()[:95],
        "description": strip_ang(script.get("description", "")).strip(),
        "tags": tags,
        "thumbnail_text": " ".join(thumb[:5]),
        "scenes": scenes,
  }
  
