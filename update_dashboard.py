#!/usr/bin/env python3
"""
글로벌 투자 대시보드 자동 업데이트 스크립트
매일 15:30 JST (일본장 마감 후) 실행
"""

import urllib.request
import json
import re
import os
import sys
from datetime import datetime, timezone, timedelta

FRED_API_KEY = "83e6861e8b657ab00872c409fba12af7"
JST = timezone(timedelta(hours=9))

# ── FRED API 데이터 수집 ──────────────────────────────────────────
def fetch_fred(series_id, limit=1):
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={FRED_API_KEY}"
        f"&file_type=json&sort_order=desc&limit={limit}"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        obs = [o for o in data["observations"] if o["value"] != "."]
        return float(obs[0]["value"]) if obs else None
    except Exception as e:
        print(f"  FRED {series_id} 오류: {e}")
        return None

# ── Yahoo Finance 닛케이 수집 ─────────────────────────────────────
def fetch_nikkei():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EN225?interval=1d&range=2d"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return float(price)
    except Exception as e:
        print(f"  Nikkei 오류: {e}")
        return None

# ── CNN Fear & Greed 수집 ─────────────────────────────────────────
def fetch_fear_greed():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        score = data["fear_and_greed"]["score"]
        return round(float(score))
    except Exception as e:
        print(f"  Fear&Greed 오류: {e}")
        return None

# ── Fear & Greed 등급 ─────────────────────────────────────────────
def fg_label(score):
    if score is None:
        return "—"
    if score <= 24:
        return "EXTREME FEAR"
    elif score <= 44:
        return "FEAR"
    elif score <= 55:
        return "NEUTRAL"
    elif score <= 75:
        return "GREED"
    else:
        return "EXTREME GREED"

def fg_color(score):
    if score is None:
        return "var(--muted)"
    if score <= 24:
        return "var(--red)"
    elif score <= 44:
        return "var(--amber)"
    elif score <= 55:
        return "var(--text)"
    elif score <= 75:
        return "var(--green)"
    else:
        return "var(--green)"

# ── HTML 치환 헬퍼 ────────────────────────────────────────────────
def replace(html, pattern, new_val):
    new_html, n = re.subn(pattern, new_val, html, count=1, flags=re.DOTALL)
    if n == 0:
        print(f"  ⚠️  패턴 미매칭: {pattern[:60]}")
    return new_html

# ── 메인 업데이트 함수 ────────────────────────────────────────────
def update_dashboard():
    print("=" * 50)
    print(f"대시보드 업데이트 시작: {datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')}")
    print("=" * 50)

    # ── 데이터 수집 ──
    print("\n[1] 데이터 수집 중...")

    vix       = fetch_fred("VIXCLS")
    y10       = fetch_fred("DGS10")
    y2        = fetch_fred("DGS2")
    y30       = fetch_fred("DGS30")
    wti       = fetch_fred("DCOILWTICO")
    brent     = fetch_fred("DCOILBRENTEU")
    usdjpy    = fetch_fred("DEXJPUS")   # JPY per USD
    nikkei    = fetch_nikkei()
    fg        = fetch_fear_greed()

    # 스프레드 계산
    spread = round(y10 - y2, 2) if y10 and y2 else None

    print(f"  VIX:        {vix}")
    print(f"  10Y:        {y10}%")
    print(f"  2Y:         {y2}%")
    print(f"  30Y:        {y30}%")
    print(f"  스프레드:   {spread:+.2f}%p" if spread else "  스프레드:  —")
    print(f"  WTI:        ${wti}")
    print(f"  Brent:      ${brent}")
    print(f"  USD/JPY:    ¥{usdjpy}")
    print(f"  닛케이225:  {nikkei:,.0f}" if nikkei else "  닛케이225:  —")
    print(f"  Fear&Greed: {fg} ({fg_label(fg)})")

    # ── HTML 로드 ──
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    if not os.path.exists(html_path):
        print(f"\n❌ index.html 없음: {html_path}")
        sys.exit(1)

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    print("\n[2] HTML 업데이트 중...")

    today = datetime.now(JST).strftime("%Y.%m.%d")
    today_kr = datetime.now(JST).strftime("%Y년 %m월 %d일")

    # ── VIX ──
    if vix:
        vix_color = "var(--red)" if vix >= 20 else "var(--amber)" if vix >= 15 else "var(--green)"
        html = replace(html,
            r'(<div class="sec-num">03</div>.*?<div class="bval" style="color:)[^"]+(">[0-9.]+</div>)',
            rf'\g<1>{vix_color}\2')
        html = replace(html,
            r'(class="sec-num">03</.*?class="bval"[^>]+>)[0-9.]+',
            rf'\g<1>{vix:.2f}')
        # VIX 설명줄
        html = replace(html,
            r'(📊 VIX — 공포지수.*?<div class="bval"[^>]+>)[0-9.]+',
            rf'\g<1>{vix:.2f}')
        html = replace(html,
            r'(VIX — 공포지수.*?<div class="blabel">)[^<]+',
            rf'\g<1>{today} 종가')
        print(f"  ✅ VIX: {vix:.2f}")

    # ── 수익률 곡선 스프레드 ──
    if spread is not None:
        spread_color = "var(--green)" if spread >= 0 else "var(--red)"
        spread_str = f"{spread:+.2f}%p"
        html = replace(html,
            r'(📉 미국 수익률 곡선.*?<div class="bval"[^>]+>)[^<]+',
            rf'\g<1>{spread_str}')
        print(f"  ✅ 스프레드: {spread_str}")

    # ── 국채 금리 테이블 ──
    if y2:
        html = replace(html,
            r'(<td>2년</td><td class="mono">)[0-9.]+(%</td>)',
            rf'\g<1>{y2:.2f}\2')
        print(f"  ✅ 2Y: {y2:.2f}%")
    if y10:
        html = replace(html,
            r'(<td>10년</td><td class="mono">)[0-9.]+(%</td>)',
            rf'\g<1>{y10:.2f}\2')
        print(f"  ✅ 10Y: {y10:.2f}%")
    if y30:
        html = replace(html,
            r'(<td>30년</td><td class="mono">)[0-9.]+(%</td>)',
            rf'\g<1>{y30:.2f}\2')
        print(f"  ✅ 30Y: {y30:.2f}%")

    # ── Fear & Greed ──
    if fg:
        fg_col = fg_color(fg)
        fg_lbl = fg_label(fg)
        html = replace(html,
            r'(① CNN Fear &amp; Greed Index.*?<div class="gauge-num" style="color:)[^"]+(">[0-9]+</div>)',
            rf'\g<1>{fg_col}\2')
        html = replace(html,
            r'(gauge-num" style="color:[^"]+">)[0-9]+',
            rf'\g<1>{fg}')
        html = replace(html,
            r'(class="gauge-status" style="color:[^"]+">)[^<]+',
            rf'\g<1>{fg_lbl}')
        html = replace(html,
            r'(현재 \()\d+/\d+(\).*?</span><span style="color:[^"]+">)[0-9]+',
            rf'\g<1>{datetime.now(JST).strftime("%-m/%-d")}\2{fg}')
        # 프로그레스바 너비
        html = replace(html,
            r'(gauge-num.*?pbar-fill" style="width:)[0-9]+(%";background:var\(--red\))',
            rf'\g<1>{fg}\2')
        print(f"  ✅ Fear&Greed: {fg} ({fg_lbl})")

    # ── WTI / 브렌트 (섹션 07) ──
    if wti:
        html = replace(html,
            r'(WTI 원유</div><div class="sv"[^>]+>\$)[0-9.]+',
            rf'\g<1>{wti:.2f}')
        print(f"  ✅ WTI: ${wti:.2f}")
    if brent:
        html = replace(html,
            r'(브렌트유</div><div class="sv"[^>]+>\$)[0-9.]+',
            rf'\g<1>{brent:.0f}')
        print(f"  ✅ Brent: ${brent:.0f}")

    # ── 요약표 (섹션 08) ──
    if usdjpy:
        html = replace(html,
            r'(<td>USD/JPY</td><td class="mono">¥)[0-9~.]+',
            rf'\g<1>{usdjpy:.2f}')
        print(f"  ✅ USD/JPY: ¥{usdjpy:.2f}")
    if nikkei:
        html = replace(html,
            r'(<td>닛케이225</td><td class="mono">)[0-9,]+',
            rf'\g<1>{nikkei:,.0f}')
        print(f"  ✅ 닛케이: {nikkei:,.0f}")
    if vix:
        html = replace(html,
            r'(<td>VIX 공포지수</td><td class="mono">)[0-9.]+',
            rf'\g<1>{vix:.2f}')
    if spread is not None:
        html = replace(html,
            r'(<td>수익률 곡선 10Y-2Y</td><td class="mono">)[+\-0-9.]+%p',
            rf'\g<1>{spread:+.2f}%p')
    if wti:
        html = replace(html,
            r'(<td>WTI 원유</td><td class="mono">\$)[0-9.]+',
            rf'\g<1>{wti:.2f}')
    if brent:
        html = replace(html,
            r'(<td>브렌트유</td><td class="mono">\$)[0-9.]+',
            rf'\g<1>{brent:.0f}')

    # ── 푸터 업데이트 날짜 ──
    html = replace(html,
        r'최종 수동 업데이트: [0-9년월일 ]+',
        f'최종 자동 업데이트: {today_kr}')
    print(f"  ✅ 업데이트 날짜: {today_kr}")

    # ── HTML 저장 ──
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ 완료: {html_path}")
    print("=" * 50)

if __name__ == "__main__":
    update_dashboard()
