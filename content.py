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
             "caption": "नमस्ते दोस्तों! क्या आपने कभी सोचा है कि AI आखिर सीखता कैसे है?",
             "visual_query": "artificial intelligence neural network", "card_text": "AI KAISE SEEKHTA HAI?"},
            {"voice": f"आप देख रहे हैं {spoken}, और आज हम इसे बिल्कुल आसान भाषा में समझेंगे।",
             "caption": "आप देख रहे हैं USHORA AI & TECHNOLOGY, और आज हम इसे बिल्कुल आसान भाषा में समझेंगे।",
             "visual_query": "technology futuristic digital", "card_text": "USHORA AI & TECHNOLOGY"},
            {"voice": "AI इंसानों की तरह किताबें नहीं पढ़ता। वो बहुत सारे examples और data को analyse करके patterns सीखता है।",
             "caption": "AI इंसानों की तरह किताबें नहीं पढ़ता। वो बहुत सारे उदाहरण, यानी डेटा देखता है।",
             "visual_query": "data center server lights", "card_text": "DATA = EXAMPLES"},
            {"voice": "जैसे आप किसी बच्चे को हज़ार बिल्लियों की फ़ोटो दिखाओ, तो वो धीरे-धीरे बिल्ली पहचानना सीख जाता है।",
             "caption": "जैसे आप किसी बच्चे को हज़ार बिल्लियों की फ़ोटो दिखाओ, तो वो धीरे-धीरे बिल्ली पहचानना सीख जाता है।",
             "visual_query": "cat portrait", "card_text": "1000 BILLIYON KI PHOTO"},
            {"voice": "AI भी यही करता है। बस फ़र्क़ ये है कि वो लाखों उदाहरण बहुत तेज़ी से देख लेता है।",
             "caption": "AI भी यही करता है। बस फ़र्क़ ये है कि वो लाखों उदाहरण बहुत तेज़ी से देख लेता है।",
             "visual_query": "computer code screen", "card_text": "LAKHON EXAMPLES"},
            {"voice": "जब AI गलत prediction करता है, तो training के दौरान उसके parameters update होते हैं। इससे अगली बार उसका result बेहतर हो सकता है।",
             "caption": "हर बार गलती करने पर उसके अंदर के नंबर थोड़े बदलते हैं, और अगली बार जवाब बेहतर हो जाता है। इसे ट्रेनिंग कहते हैं।",
             "visual_query": "abstract technology network", "card_text": "TRAINING"},
            {"voice": "लेकिन एक बात याद रखें—AI का हर answer सही नहीं होता। इसलिए important information को verify करना जरूरी है।",
             "caption": "लेकिन ध्यान रखिए, AI कभी-कभी गलत भी हो सकता है। इसलिए हर जवाब को जाँच कर ही इस्तेमाल करें।",
             "visual_query": "person thinking laptop", "card_text": "JAANCH KARO"},
            {"voice": "अगर ये वीडियो आपको पसंद आया, तो चैनल को सब्सक्राइब करें और कमेंट में बताइए कि अगला टॉपिक क्या होना चाहिए।",
             "caption": "अगर ये वीडियो आपको पसंद आया, तो चैनल को सब्सक्राइब करें और कमेंट में बताइए कि अगला टॉपिक क्या होना चाहिए।",
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


def _api_error_message(response):
    """Return a useful API error without ever exposing the API key."""
    try:
        data = response.json()
        err = data.get("error", {})
        message = str(err.get("message", "")).strip()
        status = str(err.get("status", "")).strip()
        reason = ""
        details = err.get("details", [])
        if isinstance(details, list):
            for item in details:
                if isinstance(item, dict):
                    reason = str(item.get("reason") or item.get("quotaMetric") or "")
                    if reason:
                        break
        parts = [f"HTTP {response.status_code}"]
        if status:
            parts.append(status)
        if reason:
            parts.append(reason)
        if message:
            parts.append(message[:700])
        return " | ".join(parts)
    except Exception:
        return f"HTTP {response.status_code}: {response.text[:300]}"


def gemini_json(cfg, prompt, temperature=0.8):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY secret is missing. Add it in GitHub > Settings > Secrets, "
                           "or run mode 'test' which needs no keys.")

    model = cfg["llm"]["model"]
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"}}
    last_error = ""
    discovered_after_404 = False

    for attempt in range(4):
        try:
            response = requests.post(
                f"{GEMINI_BASE}/models/{model}:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=body, timeout=180
            )
        except requests.RequestException as ex:
            last_error = f"Network error ({type(ex).__name__}): {str(ex)[:250]}"
            if attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            break

        if response.status_code == 404 and not discovered_after_404:
            try:
                model = _discover_model(key)
                discovered_after_404 = True
                print(f"[llm] retrying with available model: {model}")
                continue
            except Exception as ex:
                last_error = f"{_api_error_message(response)}; model discovery failed: {str(ex)[:250]}"
                break

        if response.status_code in (429, 500, 503):
            last_error = _api_error_message(response)
            if attempt < 3:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    wait_seconds = min(max(int(retry_after), 2), 30) if retry_after else min(5 * (attempt + 1), 20)
                except ValueError:
                    wait_seconds = min(5 * (attempt + 1), 20)
                print(f"[llm] temporary API error ({last_error}); retry {attempt + 1}/3 in {wait_seconds}s")
                time.sleep(wait_seconds)
                continue
            break

        if response.status_code != 200:
            raise RuntimeError(f"Gemini request failed: {_api_error_message(response)}")

        try:
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise RuntimeError(f"Gemini returned no usable text: {str(response.text)[:500]}")

        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            a, b = text.find("{"), text.rfind("}")
            if a >= 0 and b > a:
                try:
                    return json.loads(text[a:b + 1])
                except json.JSONDecodeError:
                    pass
            raise RuntimeError("Gemini returned text that was not valid JSON.")

    raise RuntimeError(f"Gemini request failed after retries: {last_error or 'unknown API error'}. "
                       "Check the exact message above for quota, billing, model access, or network issues.")

def _translate_sentence_to_hindi(sentence):
    """Translate public source text with MyMemory's free endpoint; fail closed."""
    response = requests.get(
        "https://api.mymemory.translated.net/get",
        params={"q": sentence[:450], "langpair": "en|hi"},
        headers=UA, timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    translated = _clean(data.get("responseData", {}).get("translatedText", ""))
    devanagari = len(re.findall(r"[ऀ-ॿ]", translated))
    if len(translated) < 18 or devanagari < 8:
        raise RuntimeError("Free Hindi translation returned incomplete text.")
    return translated


def _visual_query_for(text, index):
    lower = text.lower()
    topics = [
        (("chip", "processor", "semiconductor"), "computer processor semiconductor chip macro"),
        (("phone", "smartphone", "mobile"), "modern smartphone technology closeup"),
        (("cyber", "security", "hack", "data breach"), "cybersecurity digital network security"),
        (("robot", "automation"), "robotics automation laboratory"),
        (("model", "language", "chatbot", "artificial intelligence", " ai "), "artificial intelligence neural network"),
        (("cloud", "server", "data center"), "cloud computing server racks"),
    ]
    base = next((query for words, query in topics if any(word in lower for word in words)),
                "technology research workstation" if index % 2 else "digital data visualization")
    return f"{base} cinematic shot {index + 1}"


def _rule_based_script(topic, article, cfg):
    """Create a Hindi source-led script using a free translation endpoint, never guess."""
    raw = _clean(article or topic.get("summary", ""))
    sentences = [ " ".join(x.split()).strip(" -•") for x in re.split(r"(?<=[.!?।])\s+", raw)]
    candidates = [
        x for x in sentences
        if 45 <= len(x) <= 420 and len(x.split()) >= 8
        and not x.lower().startswith(("cookie", "subscribe", "sign in", "advertisement"))
    ][:7]
    if len(candidates) < 3:
        raise RuntimeError("Source has fewer than 3 usable factual sentences; refusing a generic news video.")

    translated = []
    for sentence in candidates:
        try:
            hi = _translate_sentence_to_hindi(sentence)
        except Exception as ex:
            raise RuntimeError(f"Free Hindi translation unavailable; no video made to avoid inaccurate narration ({type(ex).__name__}).")
        translated.append(hi)

    scenes = [{
        "voice": "नमस्ते! USHORA पर आज की टेक खबर को आसान हिंदी में समझते हैं।",
        "caption": "नमस्ते! USHORA पर आज की टेक खबर को आसान हिंदी में समझते हैं।",
        "visual_query": "technology news studio digital screens", "card_text": "आज की टेक खबर"
    }]
    for i, fact in enumerate(translated):
        lead = ("पहली अहम बात: " if i == 0 else "एक और जरूरी जानकारी: " if i == 1 else "")
        voice = lead + fact
        scenes.append({
            "voice": voice, "caption": voice,
            "visual_query": _visual_query_for(candidates[i], i),
            "card_text": f"खबर का पॉइंट {i + 1}"
        })
    scenes.append({
        "voice": "यह जानकारी दिए गए मूल स्रोत पर आधारित है। लिंक description में है।",
        "caption": "यह जानकारी दिए गए मूल स्रोत पर आधारित है। लिंक description में है।",
        "visual_query": "technology article source research laptop", "card_text": "मूल स्रोत description में"
    })
    scenes.append({
        "voice": "आपकी इस खबर पर क्या राय है? Comment में बताइए और USHORA को subscribe कीजिए।",
        "caption": "आपकी इस खबर पर क्या राय है? Comment में बताइए और USHORA को subscribe कीजिए।",
        "visual_query": "creator technology studio subscribe", "card_text": "आपकी राय?"
    })
    return {
        "title": topic["title"][:65],
        "description": f"इस वीडियो में मूल स्रोत के उपलब्ध तथ्यों का हिंदी सार दिया गया है। Original source: {topic['link']}",
        "tags": ["AI", "Technology", "Tech News", "Hindi", "USHORA", "AI Update"],
        "thumbnail_text": "आज की टेक खबर",
        "source_fact_count": len(translated),
        "scenes": scenes,
    }

def make_real_script(cfg, history):
    cands = fetch_candidates(cfg, history)
    if not cands:
        raise RuntimeError("No fresh topics found. Check topics.feeds/keywords or increase topics.max_age_days.")
    if os.environ.get("GEMINI_API_KEY", "").strip() and os.environ.get("USHORA_FORCE_FREE_SCRIPT") != "1":
        try:
            listing = "\n".join(f"{i}. {c['title']} -- {c['summary'][:200]}" for i, c in enumerate(cands))
            pick = gemini_json(cfg, (
                f"You are the editor of a Hinglish YouTube channel for {cfg['channel']['audience']}.\n"
                "Choose ONE useful, source-supported story. Avoid rumours and unverified claims.\n"
                f"{listing}\n\nReturn JSON: {{\"index\": <number>, \"reason\": \"<short>\"}}"), temperature=0.3)
            idx = int(pick.get("index", 0))
            topic = cands[idx if 0 <= idx < len(cands) else 0]
            article = fetch_article_text(topic["link"], topic["summary"])
            prompt = f"""Write an original, concise Hinglish script for {cfg['channel']['name']}.
Use ONLY source-supported facts. VOICE: natural professional Indian Hinglish in Devanagari script. Keep sentence structure Hindi, but naturally retain useful English technology words such as AI, update, feature, launch, performance, security, smartphone, app, software, data, processor, model, tool, platform, users, and impact. Do not force translations of common tech vocabulary. Avoid long full-English sentences, awkward literal translations, and romanized Hindi. Speak like a confident technology news presenter: crisp, engaging, clear, conversational, and consistent. CAPTIONS: match the spoken Hinglish exactly, preserving English tech terms in Latin script.
SOURCE TITLE: {topic['title']}
SOURCE TEXT: {article}
Return JSON with title, description, tags, thumbnail_text, source_fact_count and 8-12 scenes. Include 5-7 distinct factual points from the article. Every spoken line and caption must be natural Hindi in Devanagari with common English tech terms allowed. Do not use generic filler, tell viewers merely to read the source, or invent facts. Every factual scene must map to a source-supported point."""
            return topic, gemini_json(cfg, prompt, temperature=0.7)
        except Exception as ex:
            print(f"[llm] Gemini unavailable; using free source-led fallback ({type(ex).__name__}).")
    topic = cands[0]
    article = fetch_article_text(topic["link"], topic["summary"])
    print("[script] using no-API rule-based source-led brief.")
    return topic, _rule_based_script(topic, article, cfg)

# ----------------------------------------------------------------------------
def validate_script(script, cfg, require_source=False):
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
    if require_source:
        fact_count = int(script.get("source_fact_count", 0))
        if not 3 <= fact_count <= 7:
            raise RuntimeError("Content QA failed: expected 3-7 translated source facts.")
        generic = ("पूरी जानकारी के लिए", "read the source", "लेख अंग्रेज़ी में है", "original source पढ़ें")
        factual = [s for s in scenes if len(s["voice"].split()) >= 8
                   and not any(g in s["voice"].lower() for g in generic)]
        if len(factual) < 3:
            raise RuntimeError("Content QA failed: too few substantive narrated scenes.")
        if any(len(re.findall(r"[ऀ-ॿ]", s["voice"])) < 8 for s in factual):
            raise RuntimeError("Content QA failed: factual narration must be Hindi-first.")
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
  
