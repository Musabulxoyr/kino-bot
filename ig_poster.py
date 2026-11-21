"""Instagram auto-poster (Instagram API with Instagram Login).

Env variables (Railway > Variables):
  IG_TOKEN        Instagram User access token (from App Dashboard)
  GEMINI_API_KEY  same key your bot uses
  GEMINI_MODEL    same model name your bot uses (default below)
  POST_HOUR       hour of day to post, Tashkent time (default 19)
  AI_LABEL        1 = mark posts as AI-generated (default 1)
  DRY_RUN         1 = only print the caption, do not post
  QUEUE_FILE      path to queue file (default queue.json)

Usage:
  python ig_poster.py          # run forever, post once a day
  python ig_poster.py --now    # post the next video right now
  python ig_poster.py --refresh  # print a refreshed 60-day token
"""
import json
import os
import sys
import time
import datetime as dt

import requests

API = "https://graph.instagram.com/v22.0"
TZ = dt.timezone(dt.timedelta(hours=5))  # Tashkent

IG_TOKEN = os.getenv("IG_TOKEN", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
POST_HOUR = int(os.getenv("POST_HOUR", "19"))
AI_LABEL = os.getenv("AI_LABEL", "1") == "1"
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
QUEUE_FILE = os.getenv("QUEUE_FILE", "queue.json")


def make_caption(topic: str) -> str:
    prompt = (
        "Instagram Reels uchun o'zbek tilida qisqa izoh yoz. "
        f"Mavzu: {topic}. "
        "2-3 gap, oxirida chaqiriq: 'Birinchi prezentatsiya bepul, havola bio'da'. "
        "Oxirida 5-8 ta tegli (#) so'z. Faqat izoh matnini qaytar."
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    )
    r = requests.post(
        url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def publish_reel(video_url: str, caption: str) -> str:
    # 1) create media container
    data = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": IG_TOKEN,
    }
    if AI_LABEL:
        data["is_ai_generated"] = "true"
    r = requests.post(f"{API}/me/media", data=data, timeout=60)
    r.raise_for_status()
    container_id = r.json()["id"]

    # 2) wait until Instagram finishes processing the video
    for _ in range(40):
        s = requests.get(
            f"{API}/{container_id}",
            params={"fields": "status_code", "access_token": IG_TOKEN},
            timeout=30,
        ).json()
        status = s.get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing failed: {s}")
        time.sleep(15)
    else:
        raise RuntimeError("Instagram processing timed out")

    # 3) publish
    r = requests.post(
        f"{API}/me/media_publish",
        data={"creation_id": container_id, "access_token": IG_TOKEN},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["id"]


def load_queue() -> list:
    with open(QUEUE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_queue(items: list) -> None:
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def post_next() -> bool:
    items = load_queue()
    item = next((i for i in items if not i.get("posted")), None)
    if not item:
        print("Navbat bo'sh: queue.json'ga yangi video qo'shing.")
        return False
    caption = make_caption(item["topic"])
    print("Izoh:\n", caption)
    if DRY_RUN:
        print("DRY_RUN: joylanmadi.")
        return False
    media_id = publish_reel(item["video_url"], caption)
    item["posted"] = True
    item["media_id"] = media_id
    save_queue(items)
    print("Joylandi:", media_id)
    return True


def refresh_token() -> None:
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": IG_TOKEN},
        timeout=30,
    )
    r.raise_for_status()
    print("Yangi token (Railway Variables'ga qo'ying):")
    print(r.json()["access_token"])


def main() -> None:
    if "--refresh" in sys.argv:
        refresh_token()
        return
    if "--now" in sys.argv:
        post_next()
        return
    last_day = None
    while True:
        now = dt.datetime.now(TZ)
        if now.hour == POST_HOUR and last_day != now.date():
            try:
                post_next()
            except Exception as e:  # keep the loop alive
                print("Xato:", e)
            last_day = now.date()
        time.sleep(60)


if __name__ == "__main__":
    main()
