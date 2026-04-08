#!/usr/bin/env python3
"""
텔레그램 공개 채널에서 뉴스를 수집하고 번역하여 news_kr.json / news_ja.json 생성
GitHub Actions에서 실행
"""
import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

# ── 수집 대상 채널 ──
CHANNELS = [
    {"username": "firstsquawk", "label": "First Squawk", "lang": "en"},
    {"username": "FinancialJuice", "label": "Financial Juice", "lang": "en"},
    {"username": "aetherjapanresearch", "label": "에테르 리서치", "lang": "ko"},
]

def fetch_telegram(username, limit=10):
    """공개 텔레그램 채널에서 최근 메시지 수집"""
    url = f"https://t.me/s/{username}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  ❌ @{username} 수집 실패: {e}")
        return []
    
    soup = BeautifulSoup(r.text, "html.parser")
    messages = []
    
    for msg in soup.select(".tgme_widget_message")[-limit:]:
        text_el = msg.select_one(".tgme_widget_message_text")
        date_el = msg.select_one(".tgme_widget_message_date time")
        link_el = msg.select_one(".tgme_widget_message_date")
        
        if not text_el:
            continue
        
        text = text_el.get_text(separator=" ").strip()
        # 너무 짧거나 미디어만 있는 메시지 스킵
        if len(text) < 15:
            continue
        
        date_str = date_el.get("datetime", "")[:16] if date_el else ""
        link = link_el.get("href", "") if link_el else ""
        
        messages.append({
            "text": text[:500],
            "date": date_str,
            "link": link,
        })
    
    return messages

def translate_google(text, target="ko"):
    """Google Translate 무료 API로 번역"""
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target,
            "dt": "t",
            "q": text[:500]
        }
        r = requests.get(url, params=params, timeout=10)
        result = r.json()
        translated = "".join(seg[0] for seg in result[0] if seg[0])
        return translated
    except Exception as e:
        print(f"  번역 실패: {e}")
        return text

def main():
    print("=" * 50)
    print("📰 뉴스 수집 시작")
    print("=" * 50)
    
    all_news_kr = []
    all_news_ja = []
    
    for ch in CHANNELS:
        username = ch["username"]
        label = ch["label"]
        lang = ch["lang"]
        
        print(f"\n📡 @{username} ({label}) 수집중...")
        messages = fetch_telegram(username, limit=8)
        print(f"  → {len(messages)}건 수집")
        
        for msg in messages:
            text = msg["text"]
            
            # 한국어 버전
            if lang == "en":
                text_kr = translate_google(text, "ko")
                text_ja = translate_google(text, "ja")
            elif lang == "ko":
                text_kr = text
                text_ja = translate_google(text, "ja")
            elif lang == "ja":
                text_kr = translate_google(text, "ko")
                text_ja = text
            else:
                text_kr = text
                text_ja = text
            
            base = {
                "date": msg["date"],
                "source": label,
                "link": msg["link"],
            }
            
            all_news_kr.append({**base, "text": text_kr[:300]})
            all_news_ja.append({**base, "text": text_ja[:300]})
    
    # 날짜 역순 정렬 (최신이 위)
    all_news_kr.sort(key=lambda x: x["date"], reverse=True)
    all_news_ja.sort(key=lambda x: x["date"], reverse=True)
    
    # 최대 20건
    all_news_kr = all_news_kr[:20]
    all_news_ja = all_news_ja[:20]
    
    # 저장
    with open("news_kr.json", "w", encoding="utf-8") as f:
        json.dump(all_news_kr, f, ensure_ascii=False, indent=2)
    with open("news_ja.json", "w", encoding="utf-8") as f:
        json.dump(all_news_ja, f, ensure_ascii=False, indent=2)
    
    now = datetime.now(JST).strftime("%Y.%m.%d %H:%M JST")
    print(f"\n✅ 저장 완료: news_kr.json ({len(all_news_kr)}건), news_ja.json ({len(all_news_ja)}건)")
    print(f"⏰ {now}")

if __name__ == "__main__":
    main()
