#!/usr/bin/env python3
"""
글로벌 투자 대시보드 자동 업데이트 스크립트
매일 15:30 JST (일본장 마감 후) 실행
"""

import urllib.request
import json
import re
import os
from datetime import datetime, timezone, timedelta

FRED_API_KEY = "83e6861e8b657ab00872c409fba12af7"
JST = timezone(timedelta(hours=9))

def fetch_fred(series_id):
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={FRED_API_KEY}"
           f"&file_type=json&sort_order=desc&limit=1")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        obs = [o for o in data["observations"] if o["value"] != "."]
        return float(obs[0]["value"]) if obs else None
    except Exception as e:
        print(f"  FRED {series_id} 오류: {e}")
        return None

def fetch_yahoo(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        meta  = data["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
        # Yahoo 자체 등락값 우선 사용 → 가장 정확
        chg   = meta.get("regularMarketChange")
        pct   = meta.get("regularMarketChangePercent")
        # 없으면 직접 계산 (fallback)
        if chg is None or pct is None:
            prev = meta.get("chartPreviousClose") or meta.get("previousClose") or price
            chg  = price - prev
            pct  = (chg / prev * 100) if prev else 0
        return {"price": price, "chg": chg, "pct": pct}
    except Exception as e:
        print(f"  Yahoo {symbol} 오류: {e}")
        return None

def fetch_topix_stooq():
    url = "https://stooq.com/q/d/l/?s=%5Etpx&i=d"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            lines = r.read().decode("utf-8").strip().split("\n")
        if len(lines) < 3:
            return None
        latest  = lines[-1].split(",")
        prev    = lines[-2].split(",")
        price   = float(latest[4])
        prev_cl = float(prev[4])
        chg     = price - prev_cl
        pct     = (chg / prev_cl * 100) if prev_cl else 0
        print(f"  TOPIX (stooq): {price:.2f} ({chg:+.2f} / {pct:+.2f}%)")
        return {"price": price, "chg": chg, "pct": pct}
    except Exception as e:
        print(f"  TOPIX stooq 오류: {e}")
        return None

def fetch_nikkei():
    r = fetch_yahoo("^N225")
    if r: return r
    price = fetch_fred("NIKKEI225")
    return {"price": price, "chg": None, "pct": None} if price else None

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

def fmt_num(v, fmt="USD"):
    if v is None: return "—"
    return f"{v:,.2f}"

def fmt_chg(chg, pct):
    if chg is None: return "—"
    sign = "+" if chg >= 0 else ""
    col = "#1fbd8a" if chg >= 0 else "#e8495a"
    return f'<span style="color:{col};font-weight:600;">{sign}{chg:.2f} ({sign}{pct:.2f}%)</span>'

def border_col(chg):
    if chg is None: return "rgba(28,35,51,1)"
    return "rgba(31,189,138,.35)" if chg >= 0 else "rgba(232,73,90,.35)"

# ── 핵심: lambda 방식으로 HTML 특수문자 충돌 완전 방지 ─────────────
def sub(html, pattern, repl_fn):
    new_html, n = re.subn(pattern, repl_fn, html, count=1, flags=re.DOTALL)
    if n == 0:
        print(f"  ⚠️  미매칭: {pattern[:60]}")
    return new_html

def set_text(html, el_id, text):
    """id 요소 내부 텍스트 교체 — 일반 텍스트 (태그 없음)"""
    return sub(html, rf'(id="{el_id}"[^>]*>).*?(?=<)',
               lambda m: m.group(1) + text)

def set_chg(html, el_id, content):
    """등락 요소 교체 — span 등 HTML 태그 포함. 여는태그 이후 닫는</div>까지 통째로 교체"""
    # 여는 div 태그 이후 모든 내용(중첩 span 포함)을 닫는 </div> 직전까지 교체
    return sub(html, rf'(<div[^>]*\bid="{el_id}"[^>]*>)(.*?)(</div>)',
               lambda m: m.group(1) + content + m.group(3))

def set_border(html, el_id, border):
    new_html, n = re.subn(
        rf'(id="idx-{el_id}"[^>]*style=")[^"]*(")',
        lambda m: m.group(1) + f'border-color:{border};' + m.group(2),
        html, count=1, flags=re.DOTALL)
    if n > 0:
        return new_html
    new_html, n = re.subn(
        rf'(id="idx-{el_id}")',
        lambda m: m.group(1) + f' style="border-color:{border};"',
        html, count=1)
    return new_html

def update_index_card(html, idx_id, data, fmt="USD"):
    if not data: return html
    html = set_text(html, f"v-{idx_id}", fmt_num(data["price"], fmt))
    html = set_chg(html,  f"c-{idx_id}", fmt_chg(data.get("chg"), data.get("pct")))
    html = set_border(html, idx_id, border_col(data.get("chg")))
    return html

def update_dashboard():
    print("=" * 55)
    print(f"대시보드 업데이트: {datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')}")
    print("=" * 55)

    print("\n[1] 지수 데이터 수집...")
    nk225   = fetch_nikkei()
    topix   = fetch_topix_stooq()
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
                    ("SPX",spx),("NDX",ndx),("DJI",dji),("RUT",rut),("SOX",sox)]:
        if d:
            s = f" ({'+' if d['chg']>=0 else ''}{d['chg']:.2f})" if d.get("chg") is not None else ""
            print(f"  {name}: {d['price']:,.2f}{s}")
        else:
            print(f"  {name}: 수집 실패")

    print("\n[2] 거시지표 수집...")
    vix   = fetch_fred("VIXCLS")
    y10   = fetch_fred("DGS10")
    y2    = fetch_fred("DGS2")
    y30   = fetch_fred("DGS30")
    wti   = fetch_fred("DCOILWTICO")
    brent = fetch_fred("DCOILBRENTEU")
    fg    = fetch_fear_greed()
    spread = round(y10 - y2, 2) if y10 and y2 else None
    print(f"  VIX:{vix}  10Y:{y10}  2Y:{y2}  30Y:{y30}")
    print(f"  WTI:${wti}  Brent:${brent}  F&G:{fg}  Spread:{spread}")

    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    print("\n[3] HTML 업데이트...")
    today_kr = datetime.now(JST).strftime("%Y년 %m월 %d일")
    today    = datetime.now(JST).strftime("%Y.%m.%d")
    now_str  = datetime.now(JST).strftime("%Y.%m.%d %H:%M JST")

    # 지수 카드
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
    print("  ✅ 지수 카드 완료")

    # 타임스탬프
    html = set_text(html, "idx-timestamp",
        f'📊 GitHub Actions 자동 업데이트 · {now_str}')

    # VIX
    if vix:
        html = sub(html, r'(📊 VIX — 공포지수.*?<div class="bval"[^>]+>)[0-9.]+',
                   lambda m: m.group(1) + f'{vix:.2f}')
        html = sub(html, r'(VIX — 공포지수.*?<div class="blabel">)[^<]+',
                   lambda m: m.group(1) + f'{today} 종가')
        print(f"  ✅ VIX: {vix:.2f}")

    # 수익률 곡선
    if spread is not None:
        html = sub(html, r'(📉 미국 수익률 곡선.*?<div class="bval"[^>]+>)[^<]+',
                   lambda m: m.group(1) + f'{spread:+.2f}%p')
    if y2:
        html = sub(html, r'(<td>2년</td><td class="mono">)[0-9.]+(%</td>)',
                   lambda m: m.group(1) + f'{y2:.2f}' + m.group(2))
    if y10:
        html = sub(html, r'(<td>10년</td><td class="mono">)[0-9.]+(%</td>)',
                   lambda m: m.group(1) + f'{y10:.2f}' + m.group(2))
    if y30:
        html = sub(html, r'(<td>30년</td><td class="mono">)[0-9.]+(%</td>)',
                   lambda m: m.group(1) + f'{y30:.2f}' + m.group(2))

    # Fear & Greed
    if fg:
        fg_map = {(0,24):"EXTREME FEAR",(25,44):"FEAR",(45,55):"NEUTRAL",
                  (56,75):"GREED",(76,100):"EXTREME GREED"}
        fg_lbl = next(v for (lo,hi),v in fg_map.items() if lo <= fg <= hi)
        fg_col = "#e8495a" if fg<=24 else "#e8a030" if fg<=44 else "#dde3ee" if fg<=55 else "#1fbd8a"
        html = sub(html, r'(gauge-num" style="color:)[^"]+',
                   lambda m: m.group(1) + fg_col)
        html = sub(html, r'(gauge-num" style="color:[^"]+">)\d+',
                   lambda m: m.group(1) + str(fg))
        html = sub(html, r'(gauge-status" style="color:)[^"]+',
                   lambda m: m.group(1) + fg_col)
        html = sub(html, r'(gauge-status" style="color:[^"]+">)[^<]+',
                   lambda m: m.group(1) + fg_lbl)
        html = sub(html, r'(현재 \()\d+/\d+(\))',
                   lambda m: m.group(1) + datetime.now(JST).strftime("%-m/%-d") + m.group(2))
        html = sub(html, r'(pbar-fill" style="width:)\d+(%";background:var\(--red\))',
                   lambda m: m.group(1) + str(fg) + m.group(2))
        print(f"  ✅ Fear&Greed: {fg} ({fg_lbl})")

    # WTI / 브렌트
    if wti:
        html = sub(html, r'(WTI 원유</div><div class="sv"[^>]+>\$)[0-9.]+',
                   lambda m: m.group(1) + f'{wti:.2f}')
        print(f"  ✅ WTI: ${wti:.2f}")
    if brent:
        html = sub(html, r'(브렌트유</div><div class="sv"[^>]+>\$)[0-9.]+',
                   lambda m: m.group(1) + f'{brent:.0f}')
        print(f"  ✅ Brent: ${brent:.0f}")

    # 요약표
    if nk225:
        html = sub(html, r'(<td>닛케이225</td><td class="mono">)[0-9,]+',
                   lambda m: m.group(1) + f'{nk225["price"]:,.0f}')
    if vix:
        html = sub(html, r'(<td>VIX 공포지수</td><td class="mono">)[0-9.]+',
                   lambda m: m.group(1) + f'{vix:.2f}')
    if spread:
        html = sub(html, r'(<td>수익률 곡선 10Y-2Y</td><td class="mono">)[+\-0-9.]+%p',
                   lambda m: m.group(1) + f'{spread:+.2f}%p')
    if wti:
        html = sub(html, r'(<td>WTI 원유</td><td class="mono">\$)[0-9.]+',
                   lambda m: m.group(1) + f'{wti:.2f}')
    if brent:
        html = sub(html, r'(<td>브렌트유</td><td class="mono">\$)[0-9.]+',
                   lambda m: m.group(1) + f'{brent:.0f}')

    # 푸터
    html = sub(html, r'최종 .{0,5}업데이트: [\d년월일 ]+',
               lambda m: f'최종 자동 업데이트: {today_kr}')

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ 저장 완료: {html_path}")
    print("=" * 55)

if __name__ == "__main__":
    update_dashboard()
