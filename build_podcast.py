import base64, json, os, re, sys, urllib.request, urllib.error
from datetime import datetime
from email.utils import format_datetime
from zoneinfo import ZoneInfo
import google.auth
from google.auth.transport.requests import Request

BASE_URL = "https://mhlgp.github.io/NHL-morning-podcast"
VOICE = "en-US-Chirp3-HD-Charon"
PROJECT_ID = os.environ["GCP_PROJECT_ID"]
KEEP = 14
TZ = ZoneInfo("America/Chicago")


def chunk_text(text, limit=3500):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks, cur = [], ""
    for s in sentences:
        candidate = (cur + " " + s) if cur else s
        if cur and len(candidate.encode("utf-8")) > limit:
            chunks.append(cur)
            cur = s
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return chunks


def synthesize(text, token):
    audio = b""
    for c in chunk_text(text):
        body = json.dumps({
            "input": {"text": c},
            "voice": {"languageCode": "en-US", "name": VOICE},
            "audioConfig": {"audioEncoding": "MP3"},
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            data=body,
            headers={
                "Authorization": "Bearer " + token,
                "x-goog-user-project": PROJECT_ID,
                "Content-Type": "application/json",
            },
        )
        try:
            resp = json.load(urllib.request.urlopen(req))
        except urllib.error.HTTPError as e:
            print("TTS error", e.code, e.read().decode())
            sys.exit(1)
        audio += base64.b64decode(resp["audioContent"])
    return audio


creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
creds.refresh(Request())

text = open("script.txt", encoding="utf-8").read()
now = datetime.now(TZ)
stamp = now.strftime("%Y-%m-%d")
title = "NHL Rundown, " + now.strftime("%b") + " " + str(now.day)

os.makedirs("episodes", exist_ok=True)
audio = synthesize(text, creds.token)
with open("episodes/" + stamp + ".mp3", "wb") as f:
    f.write(audio)

meta_path = "episodes/index.json"
meta = json.load(open(meta_path)) if os.path.exists(meta_path) else []
meta = [m for m in meta if m["date"] != stamp]
meta.append({"date": stamp, "title": title, "published": format_datetime(now)})
meta.sort(key=lambda m: m["date"], reverse=True)
for old in meta[KEEP:]:
    p = "episodes/" + old["date"] + ".mp3"
    if os.path.exists(p):
        os.remove(p)
meta = meta[:KEEP]
json.dump(meta, open(meta_path, "w"), indent=2)

items = ""
for m in meta:
    p = "episodes/" + m["date"] + ".mp3"
    size = os.path.getsize(p)
    url = BASE_URL + "/" + p
    items += (
        "<item><title>" + m["title"] + "</title>"
        "<description>Daily NHL rundown.</description>"
        "<pubDate>" + m["published"] + "</pubDate>"
        '<enclosure url="' + url + '" length="' + str(size) + '" type="audio/mpeg"/>'
        "<guid isPermaLink=\"false\">" + url + "</guid></item>\n"
    )

feed = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">\n'
    "<channel>\n"
    "<title>NHL Morning Rundown</title>\n"
    "<link>" + BASE_URL + "/</link>\n"
    "<language>en-us</language>\n"
    "<description>A spoken daily recap of last night's NHL games.</description>\n"
    "<itunes:author>Matt</itunes:author>\n"
    "<itunes:explicit>false</itunes:explicit>\n"
    + items +
    "</channel>\n</rss>\n"
)
open("feed.xml", "w", encoding="utf-8").write(feed)
print("Built", title)
