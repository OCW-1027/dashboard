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

# ── FRED API ──────────────────────────────────────────────────────
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

# ── Yahoo Finance ─────────────────────────────────────────────────
def fetch_yahoo(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        meta  = data["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        prev  = meta.get("chartPreviousClose") or meta.get("previousClose", price)
        chg   = price - prev
        pct   = (chg / prev) * 100 if prev else 0
        return {"price": price, "chg": chg, "pct": pct}
    except Exception as e:
        print(f"  Yahoo {symbol} 오류: {e}")
        return None

# ── Nikkei (FRED fallback) ────────────────────────────────────────
def fetch_nikkei():
    r = fetch_yahoo("^N225")
    if r: return r
    price = fetch_fred("NIKKEI225")
    if price: return {"price": price, "chg": None, "pct": None}
    return None

# ── Fear & Greed ──────────────────────────────────────────────────
def fetch_fear_greed():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return round(float(data["fear_and_greed"]["score"]))
    except Exception as e:
        print(f"  Fear&Greed 오류: {e}")
        return None

# ── 포맷 헬퍼 ─────────────────────────────────────────────────────
def fmt_num(v, fmt="USD"):
    if v is None: return "—"
    if fmt == "JPY" and v > 100:
        return f"{v:,.2f}"
    return f"{v:,.2f}"

def fmt_chg(chg, pct):
    if chg is None: return "—"
    sign = "+" if chg >= 0 else ""
    col = "#1fbd8a" if chg >= 0 else "#e8495a"
    return f'<span style="color:{col};font-weight:600;">{sign}{chg:.2f} ({sign}{pct:.2f}%)</span>'

def border_col(chg):
    if chg is None: return "rgba(28,35,51,1)"
    return "rgba(31,189,138,.35)" if chg >= 0 else "rgba(232,73,90,.35)"

# ── HTML 치환 ─────────────────────────────────────────────────────
def replace(html, pattern, new_val):
    new_html, n = re.subn(pattern, new_val, html, count=1, flags=re.DOTALL)
    if n == 0:
        print(f"  ⚠️  패턴 미매칭: {pattern[:60]}")
    return new_html

def update_index_card(html, idx_id, data, fmt="USD"):
    if not data: return html
    price_str = fmt_num(data["price"], fmt)
    chg_html  = fmt_chg(data.get("chg"), data.get("pct"))
    border    = border_col(data.get("chg"))
    # 수치 업데이트
    html = replace(html,
        rf'(id="v-{idx_id}"[^>]*>)[^<]*',
        rf'\g<1>{price_str}')
    # 등락 업데이트
    html = replace(html,
        rf'(id="c-{idx_id}"[^>]*>)[^<]*',
        rf'\g<1>{chg_html}')
    # 카드 테두리
    html = replace(html,
        rf'(id="idx-{idx_id}"[^>]*style=")[^"]*(")',
        rf'\g<1border-color:{border};\2')
    return html

# ── 메인 ──────────────────────────────────────────────────────────
def update_dashboard():
    print("=" * 55)
    print(f"대시보드 업데이트: {datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')}")
    print("=" * 55)

    print("\n[1] 지수 데이터 수집...")
    nk225   = fetch_nikkei()
    topix   = fetch_yahoo("1306.T")
    mothers = fetch_yahoo("2516.T")
    kospi   = fetch_yahoo("^KS11")
    kosdaq  = fetch_yahoo("^KQ11")
    spx     = fetch_yahoo("^GSPC")
    ndx     = fetch_yahoo("^NDX")
    dji     = fetch_yahoo("^DJI")
    rut     = fetch_yahoo("^RUT")
    sox     = fetch_yahoo("^SOX")

    for name, d in [("NKY",nk225),("TOPIX",topix),("Mothers",mothers),
                    ("KOSPI",kospi),("KOSDAQ",kosdaq),
                    ("SPX",spx),("NDX",ndx),
                    ("DJI",dji),("RUT",rut),("SOX",sox)]:
        if d:
            chg_str = f" ({'+' if d['chg']>=0 else ''}{d['chg']:.2f})" if d.get('chg') is not None else ""
            print(f"  {name}: {d['price']:,.2f}{chg_str}")
        else:
            print(f"  {name}: 수집 실패")

    print("\n[2] 거시지표 수집...")
    vix    = fetch_fred("VIXCLS")
    y10    = fetch_fred("DGS10")
    y2     = fetch_fred("DGS2")
    y30    = fetch_fred("DGS30")
    wti    = fetch_fred("DCOILWTICO")
    brent  = fetch_fred("DCOILBRENTEU")
    fg     = fetch_fear_greed()
    spread = round(y10 - y2, 2) if y10 and y2 else None

    print(f"  VIX:{vix}  10Y:{y10}  2Y:{y2}  30Y:{y30}")
    print(f"  WTI:${wti}  Brent:${brent}  F&G:{fg}  Spread:{spread:+.2f}" if spread else "")

    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    print("\n[3] HTML 업데이트...")
    today_kr = datetime.now(JST).strftime("%Y년 %m월 %d일")
    today    = datetime.now(JST).strftime("%Y.%m.%d")

    # ── 지수 카드 업데이트 ──
    html = update_index_card(html, "nk225",   nk225,   "JPY")
    html = update_index_card(html, "topix",   topix,   "JPY")
    html = update_index_card(html, "mothers", mothers, "JPY")
    html = update_index_card(html, "kospi",   kospi,   "KRW")
    html = update_index_card(html, "kosdaq",  kosdaq,  "KRW")
    html = update_index_card(html, "spx",     spx,     "USD")
    html = update_index_card(html, "ndx",     ndx,     "USD")
    html = update_index_card(html, "dji",     dji,     "USD")
    html = update_index_card(html, "rut",     rut,     "USD")
    html = update_index_card(html, "sox",     sox,     "USD")

    # ── 타임스탬프 ──
    ts_str = datetime.now(JST).strftime("%Y.%m.%d %H:%M JST")
    html = replace(html,
        r'(id="idx-timestamp"[^>]*>)[^<]*',
        rf'\g<1>📊 GitHub Actions 종가 · {ts_str}')

    # ── VIX ──
    if vix:
        html = replace(html,
            r'(📊 VIX — 공포지수.*?<div class="bval"[^>]+>)[0-9.]+',
            rf'\g<1>{vix:.2f}')
        html = replace(html,
            r'(VIX — 공포지수.*?<div class="blabel">)[^<]+',
            rf'\g<1>{today} 종가')
        print(f"  ✅ VIX: {vix:.2f}")

    # ── 수익률 곡선 ──
    if spread is not None:
        spread_str = f"{spread:+.2f}%p"
        html = replace(html,
            r'(📉 미국 수익률 곡선.*?<div class="bval"[^>]+>)[^<]+',
            rf'\g<1>{spread_str}')
        print(f"  ✅ 스프레드: {spread_str}")

    if y2:
        html = replace(html,
            r'(<td>2년</td><td class="mono">)[0-9.]+(%</td>)',
            rf'\g<1>{y2:.2f}\2')
    if y10:
        html = replace(html,
            r'(<td>10년</td><td class="mono">)[0-9.]+(%</td>)',
            rf'\g<1>{y10:.2f}\2')
    if y30:
        html = replace(html,
            r'(<td>30년</td><td class="mono">)[0-9.]+(%</td>)',
            rf'\g<1>{y30:.2f}\2')

    # ── Fear & Greed ──
    if fg:
        fg_labels = {(0,24):"EXTREME FEAR",(25,44):"FEAR",(45,55):"NEUTRAL",(56,75):"GREED",(76,100):"EXTREME GREED"}
        fg_lbl = next(v for (lo,hi),v in fg_labels.items() if lo <= fg <= hi)
        fg_col = "#e8495a" if fg <= 24 else "#e8a030" if fg <= 44 else "#dde3ee" if fg <= 55 else "#1fbd8a"
        html = replace(html, r'(gauge-num" style="color:)[^"]+(">[0-9]+)', rf'\g<1>{fg_col}\2')
        html = replace(html, r'(gauge-num" style="color:[^"]+">)[0-9]+', rf'\g<1>{fg}')
        html = replace(html, r'(class="gauge-status" style="color:)[^"]+(">[^<]+)', rf'\g<1>{fg_col}\2')
        html = replace(html, r'(gauge-status" style="color:[^"]+">)[^<]+', rf'\g<1>{fg_lbl}')
        html = replace(html, r'(현재 \()\d+/\d+(\))', rf'\g<1>{datetime.now(JST).strftime("%-m/%-d")}\2')
        html = replace(html, r'(pbar-fill" style="width:)[0-9]+(%";background:var\(--red\))', rf'\g<1>{fg}\2')
        print(f"  ✅ Fear&Greed: {fg} ({fg_lbl})")

    # ── WTI / 브렌트 ──
    if wti:
        html = replace(html, r'(WTI 원유</div><div class="sv"[^>]+>\$)[0-9.]+', rf'\g<1>{wti:.2f}')
        print(f"  ✅ WTI: ${wti:.2f}")
    if brent:
        html = replace(html, r'(브렌트유</div><div class="sv"[^>]+>\$)[0-9.]+', rf'\g<1>{brent:.0f}')
        print(f"  ✅ Brent: ${brent:.0f}")

    # ── 요약표 ──
    if nk225:  html = replace(html, r'(<td>닛케이225</td><td class="mono">)[0-9,]+', rf'\g<1>{nk225["price"]:,.0f}')
    if vix:    html = replace(html, r'(<td>VIX 공포지수</td><td class="mono">)[0-9.]+', rf'\g<1>{vix:.2f}')
    if spread: html = replace(html, r'(<td>수익률 곡선 10Y-2Y</td><td class="mono">)[+\-0-9.]+%p', rf'\g<1>{spread:+.2f}%p')
    if wti:    html = replace(html, r'(<td>WTI 원유</td><td class="mono">\$)[0-9.]+', rf'\g<1>{wti:.2f}')
    if brent:  html = replace(html, r'(<td>브렌트유</td><td class="mono">\$)[0-9.]+', rf'\g<1>{brent:.0f}')

    # ── 푸터 ──
    html = replace(html, r'최종 [자동수동]+ 업데이트: [0-9년월일 ]+', f'최종 자동 업데이트: {today_kr}')

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ 저장 완료: {html_path}")
    print("=" * 55)

if __name__ == "__main__":
    update_dashboard()
