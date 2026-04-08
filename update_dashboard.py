#!/usr/bin/env python3
"""
글로벌 투자 대시보드 자동 업데이트
매일 6회 실행 (JST 기준)
"""

import urllib.request
import json
import re
import os
from datetime import datetime, timezone, timedelta

FRED_API_KEY = "83e6861e8b657ab00872c409fba12af7"
JST = timezone(timedelta(hours=9))

# ── Stooq ─────────────────────────────────────────────────────────
def fetch_stooq(sym, label=""):
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            lines = r.read().decode("utf-8").strip().split("\n")
        rows = [l for l in lines if l and not l.startswith("Date")]
        if len(rows) < 2:
            return None  # 조용히 실패 (Yahoo fallback으로 처리)
        today   = rows[-1].split(",")
        prev    = rows[-2].split(",")
        price   = float(today[4])
        prev_cl = float(prev[4])
        chg = price - prev_cl
        pct = (chg / prev_cl * 100) if prev_cl else 0
        print(f"  ✅ {label}: {price:,.2f}  {chg:+.2f} ({pct:+.2f}%)")
        return {"price": price, "chg": chg, "pct": pct}
    except Exception as e:
        return None  # 조용히 실패

# ── Yahoo Finance ──────────────────────────────────────────────────
def fetch_yahoo(symbol, label=""):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        result = data["chart"]["result"][0]
        meta   = result["meta"]
        price  = meta["regularMarketPrice"]
        chg = meta.get("regularMarketChange")
        pct = meta.get("regularMarketChangePercent")
        if chg is not None and pct is not None and abs(chg) > 0.01:
            print(f"  ✅ {label} (Yahoo): {price:,.2f}  {chg:+.2f} ({pct:+.2f}%)")
            return {"price": price, "chg": chg, "pct": pct}
        timestamps = result.get("timestamp", [])
        closes     = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        if timestamps and closes:
            daily = {}
            for ts, cl in zip(timestamps, closes):
                if cl is None: continue
                d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
                daily[d] = cl
            sorted_days = sorted(daily.keys())
            if len(sorted_days) >= 2:
                prev_close = daily[sorted_days[-2]]
                if prev_close and abs(price - prev_close) > 0.01:
                    chg = price - prev_close
                    pct = (chg / prev_close * 100)
                    print(f"  ✅ {label} (Yahoo ts): {price:,.2f}  {chg:+.2f} ({pct:+.2f}%)")
                    return {"price": price, "chg": chg, "pct": pct}
        prev_cl = meta.get("chartPreviousClose") or meta.get("previousClose")
        if prev_cl and abs(price - prev_cl) > 0.01:
            chg = price - prev_cl
            pct = (chg / prev_cl * 100)
            print(f"  ✅ {label} (Yahoo prev): {price:,.2f}  {chg:+.2f} ({pct:+.2f}%)")
            return {"price": price, "chg": chg, "pct": pct}
        print(f"  ⚠️  {label}: 가격만 ({price:,.2f})")
        return {"price": price, "chg": None, "pct": None}
    except Exception as e:
        print(f"  ❌ Yahoo {label} 오류: {e}")
        return None

def fetch_index(stooq_sym, yahoo_sym, label):
    r = fetch_stooq(stooq_sym, label)
    if r: return r
    return fetch_yahoo(yahoo_sym, label)

# ── TOPIX 전용 (Yahoo Finance에 TOPIX 지수 심볼 없음) ─────────────
def fetch_topix():
    """TOPIX: Stooq → 1308.T ETF (Yahoo) fallback
    1308.T (Amova TOPIX ETF)는 NAV ≈ TOPIX 지수값으로 1:1 추종"""
    # 1) Stooq
    r = fetch_stooq("^tpx", "TOPIX")
    if r:
        return r

    # 2) 1308.T ETF via Yahoo Finance (가격 ≈ TOPIX 지수)
    r = fetch_yahoo("1308.T", "TOPIX(1308.T)")
    if r:
        return r

    return None

# ── FRED ───────────────────────────────────────────────────────────
def fetch_fred(series_id, limit=1):
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={FRED_API_KEY}"
           f"&file_type=json&sort_order=desc&limit={limit}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        obs = [o for o in data["observations"] if o["value"] != "."]
        if limit == 1:
            return float(obs[0]["value"]) if obs else None
        return [float(o["value"]) for o in obs]
    except Exception as e:
        print(f"  FRED {series_id} 오류: {e}")
        return None if limit == 1 else []

# ── Fear & Greed ───────────────────────────────────────────────────
def fetch_fear_greed():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://edition.cnn.com/markets/fear-and-greed",
        "Origin": "https://edition.cnn.com",
    }
    try:
        req = urllib.request.Request(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        score = round(float(data["fear_and_greed"]["score"]))
        print(f"  ✅ Fear&Greed: {score}")
        return score
    except Exception as e:
        print(f"  Fear&Greed 오류: {e}")
        return None

# ── USD/JPY (Stooq) ────────────────────────────────────────────────
def fetch_usdjpy():
    # Stooq 우선, 실패 시 Yahoo
    r = fetch_stooq("usdjpy", "USD/JPY")
    if r: return r["price"]
    r2 = fetch_yahoo("JPY=X", "USD/JPY")
    return r2["price"] if r2 else None

# ── ISM 제조업 PMI (FRED NAPM) ─────────────────────────────────────
def fetch_ism():
    # NAPM = ISM 제조업 PMI (구 시리즈명)
    v = fetch_fred("NAPM")
    if v:
        print(f"  ✅ ISM PMI: {v}")
        return v
    # fallback: Manufacturing ISM Report On Business
    v2 = fetch_fred("MANEMP")
    return v2

# ── 코어 PCE YoY (FRED 2개값으로 YoY 계산) ─────────────────────────
def fetch_core_pce_yoy():
    try:
        url = (f"https://api.stlouisfed.org/fred/series/observations"
               f"?series_id=PCEPILFE&api_key={FRED_API_KEY}"
               f"&file_type=json&sort_order=desc&limit=13")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        obs = [o for o in data["observations"] if o["value"] != "."]
        if len(obs) >= 13:
            latest    = float(obs[0]["value"])
            yr_ago    = float(obs[12]["value"])
            yoy = (latest - yr_ago) / yr_ago * 100
            print(f"  ✅ 코어 PCE YoY: {yoy:.1f}%")
            return round(yoy, 1)
    except Exception as e:
        print(f"  코어 PCE YoY 오류: {e}")
    return None

# ── NFP 전월대비 ───────────────────────────────────────────────────
def fetch_nfp_chg():
    try:
        url = (f"https://api.stlouisfed.org/fred/series/observations"
               f"?series_id=PAYEMS&api_key={FRED_API_KEY}"
               f"&file_type=json&sort_order=desc&limit=2")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        obs = [o for o in data["observations"] if o["value"] != "."]
        if len(obs) >= 2:
            chg = round((float(obs[0]["value"]) - float(obs[1]["value"])) * 1000)
            print(f"  ✅ NFP 전월比: {chg:+,}명")
            return chg
    except Exception as e:
        print(f"  NFP 오류: {e}")
    return None

# ── FedWatch (CME) ─────────────────────────────────────────────────
def fetch_fedwatch():
    """CME FedWatch — 다음 FOMC 동결 확률"""
    try:
        url = "https://www.cmegroup.com/CmeWS/mvc/MeetingList/monthlyMeetingListJson.do?meetingType=FOMC"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        meetings = data.get("meetings", [])
        for m in meetings:
            if m.get("isActive") or m.get("isNext"):
                probs = m.get("probabilityChart", [])
                for p in probs:
                    if "No Change" in p.get("description", "") or "Unchanged" in p.get("description", ""):
                        val = round(float(p.get("probability", 0)))
                        print(f"  ✅ FedWatch 동결확률: {val}%")
                        return val
    except Exception as e:
        print(f"  FedWatch 오류: {e}")
    return None

# ── 버핏 지표 (Wilshire5000 / GDP) ────────────────────────────────
def fetch_buffett():
    try:
        # Wilshire 5000 Full Cap (시총, 십억달러)
        wilshire = fetch_fred("WILL5000INDFC")
        gdp      = fetch_fred("GDP")
        if wilshire and gdp:
            ratio = round(wilshire / gdp * 100, 1)
            print(f"  ✅ 버핏 지표: {ratio}%")
            return ratio
    except Exception as e:
        print(f"  버핏 지표 오류: {e}")
    return None

# ── 포맷 함수 ──────────────────────────────────────────────────────
def fmt_num(v, fmt="USD"):
    if v is None: return "—"
    return f"{v:,.2f}"

def fmt_chg(chg, pct):
    if chg is None: return "—"
    sign = "+" if chg >= 0 else ""
    col  = "#1fbd8a" if chg >= 0 else "#e8495a"
    return f'<span style="color:{col};font-weight:600;">{sign}{chg:.2f} ({sign}{pct:.2f}%)</span>'

def border_col(chg):
    if chg is None: return "rgba(28,35,51,1)"
    return "rgba(31,189,138,.35)" if chg >= 0 else "rgba(232,73,90,.35)"

def sub(html, pattern, repl_fn):
    new_html, n = re.subn(pattern, repl_fn, html, count=1, flags=re.DOTALL)
    if n == 0:
        print(f"  ⚠️  미매칭: {pattern[:60]}")
    return new_html

def set_text(html, el_id, text):
    return sub(html, rf'(id="{el_id}"[^>]*>).*?(?=<)',
               lambda m: m.group(1) + text)

def set_chg(html, el_id, content):
    return sub(html, rf'(<div[^>]*\bid="{el_id}"[^>]*>)(.*?)(</div>)',
               lambda m: m.group(1) + content + m.group(3))

def set_border(html, el_id, border):
    new_html, n = re.subn(
        rf'(id="idx-{el_id}"[^>]*style=")[^"]*(")',
        lambda m: m.group(1) + f'border-color:{border};' + m.group(2),
        html, count=1, flags=re.DOTALL)
    if n > 0: return new_html
    new_html, n = re.subn(
        rf'(id="idx-{el_id}")',
        lambda m: m.group(1) + f' style="border-color:{border};"',
        html, count=1)
    return new_html

def update_index_card(html, idx_id, data, fmt="USD"):
    if not data: return html
    html = set_text(html,  f"v-{idx_id}", fmt_num(data["price"], fmt))
    html = set_chg(html,   f"c-{idx_id}", fmt_chg(data.get("chg"), data.get("pct")))
    html = set_border(html, idx_id,       border_col(data.get("chg")))
    return html

# ── 메인 ──────────────────────────────────────────────────────────
def update_dashboard():
    print("=" * 55)
    print(f"대시보드 업데이트: {datetime.now(JST).strftime('%Y-%m-%d %H:%M JST')}")
    print("=" * 55)

    print("\n[1] 지수 데이터 수집...")
    nk225   = fetch_index("^nkx",    "^N225",  "닛케이225")
    topix   = fetch_topix()
    mothers = fetch_index("2516.jp", "2516.T", "グロース250")
    kospi   = fetch_index("^kospi",  "^KS11",  "코스피")
    kosdaq  = fetch_yahoo("^KQ11",             "코스닥")
    spx     = fetch_index("^spx",    "^GSPC",  "S&P500")
    ndx     = fetch_index("^ndq",    "^NDX",   "나스닥100")
    dji     = fetch_index("^dji",    "^DJI",   "다우존스")
    rut     = fetch_yahoo("^RUT",              "러셀2000")
    sox     = fetch_yahoo("^SOX",              "필라반도체")

    print("\n[2] 거시지표 수집...")
    vix    = fetch_fred("VIXCLS")
    y10    = fetch_fred("DGS10")
    y2     = fetch_fred("DGS2")
    y30    = fetch_fred("DGS30")
    # WTI/브렌트 — Yahoo Finance로 직접 (Stooq 원자재 미지원, FRED 2일 지연)
    wti_r   = fetch_yahoo("CL=F",  "WTI")
    brent_r = fetch_yahoo("BZ=F",  "Brent")
    wti     = wti_r["price"]   if wti_r   else fetch_fred("DCOILWTICO")
    brent   = brent_r["price"] if brent_r else fetch_fred("DCOILBRENTEU")
    fg     = fetch_fear_greed()
    spread = round(y10 - y2, 2) if y10 and y2 else None
    print(f"  VIX:{vix}  10Y:{y10}  2Y:{y2}  Spread:{spread}")
    print(f"  WTI:${wti}  Brent:${brent}  F&G:{fg}")

    print("\n[3] 월별 지표 수집...")
    usdjpy   = fetch_usdjpy()
    michigan = fetch_fred("UMCSENT")
    ism      = fetch_ism()
    pce_yoy  = fetch_core_pce_yoy()
    nfp_chg  = fetch_nfp_chg()
    fedwatch = fetch_fedwatch()
    buffett  = fetch_buffett()

    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    print("\n[4] HTML 업데이트...")
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
        f'📊 전일 종가 기준 · 매일 6회 자동갱신 · 최종: {now_str}')

    # VIX
    if vix:
        html = sub(html, r'(📊 VIX — 공포지수.*?<div class="bval"[^>]+>)[0-9.]+',
                   lambda m: m.group(1) + f'{vix:.2f}')
        html = sub(html, r'(VIX — 공포지수.*?<div class="blabel">)[^<]+',
                   lambda m: m.group(1) + f'{today} 종가')

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
        html = sub(html, r'(pbar-fill" style="width:)\d+(%;background:var\(--red\);)',
                   lambda m: m.group(1) + str(fg) + m.group(2))

    # WTI / 브렌트
    if wti:
        html = sub(html, r'(WTI 원유</div><div class="sv"[^>]+>\$)[0-9.]+',
                   lambda m: m.group(1) + f'{wti:.2f}')
    if brent:
        html = sub(html, r'(브렌트유</div><div class="sv"[^>]+>\$)[0-9.]+',
                   lambda m: m.group(1) + f'{brent:.0f}')

    # ── 요약표 업데이트 ──────────────────────────────────────────
    # USD/JPY 요약표
    if usdjpy:
        html = sub(html, r'(id="summary-usdjpy"[^>]*>)¥[0-9,.]+',
                   lambda m: m.group(1) + f'¥{usdjpy:,.2f}')
        print(f"  ✅ USD/JPY: ¥{usdjpy:,.2f}")

    # 닛케이225
    if nk225:
        html = sub(html, r'(<td>닛케이225</td><td class="mono">)[0-9,]+',
                   lambda m: m.group(1) + f'{nk225["price"]:,.0f}')

    # VIX
    if vix:
        html = sub(html, r'(<td>VIX 공포지수</td><td class="mono">)[0-9.]+',
                   lambda m: m.group(1) + f'{vix:.2f}')

    # 수익률 곡선
    if spread:
        html = sub(html, r'(<td>수익률 곡선 10Y-2Y</td><td class="mono">)[+\-0-9.]+%p',
                   lambda m: m.group(1) + f'{spread:+.2f}%p')

    # 코어 PCE
    if pce_yoy:
        html = sub(html, r'(<td>코어 PCE[^<]*</td><td class="mono">)[0-9.]+%',
                   lambda m: m.group(1) + f'{pce_yoy:.1f}%')
        print(f"  ✅ 코어 PCE YoY: {pce_yoy:.1f}%")

    # ISM PMI
    if ism:
        html = sub(html, r'(<td>ISM 제조업 PMI[^<]*</td><td class="mono">)[0-9.]+',
                   lambda m: m.group(1) + f'{ism:.1f}')

    # 미시간 소비심리
    if michigan:
        html = sub(html, r'(<td>미시간 소비심리[^<]*</td><td class="mono">)[0-9.]+',
                   lambda m: m.group(1) + f'{michigan:.1f}')
        print(f"  ✅ 미시간: {michigan:.1f}")

    # 비농업 고용
    if nfp_chg is not None:
        html = sub(html, r'(<td>비농업 고용[^<]*</td><td class="mono">)[+\-,\d]+',
                   lambda m: m.group(1) + f'{nfp_chg:+,}')
        print(f"  ✅ NFP: {nfp_chg:+,}")

    # Fear & Greed 요약표
    if fg:
        html = sub(html, r'(<td>Fear &amp; Greed</td><td class="mono">)\d+',
                   lambda m: m.group(1) + str(fg))

    # FedWatch
    if fedwatch:
        html = sub(html, r'(<td>FedWatch[^<]*</td><td class="mono">)[0-9.]+%',
                   lambda m: m.group(1) + f'{fedwatch}%')
        print(f"  ✅ FedWatch 동결확률: {fedwatch}%")

    # WTI / 브렌트 요약표
    if wti:
        html = sub(html, r'(<td>WTI 원유</td><td class="mono">\$)[0-9.]+',
                   lambda m: m.group(1) + f'{wti:.2f}')
    if brent:
        html = sub(html, r'(<td>브렌트유</td><td class="mono">\$)[0-9.]+',
                   lambda m: m.group(1) + f'{brent:.0f}')

    # 리스크 카드 (WTI, 브렌트, VIX 실시간 반영)
    if wti:
        html = sub(html, r'(id="risk-wti"[^>]*>)\$[0-9.]+',
                   lambda m: m.group(1) + f'${wti:.2f}')
    if brent:
        html = sub(html, r'(id="risk-brent"[^>]*>)\$[0-9.]+',
                   lambda m: m.group(1) + f'${brent:.0f}')
    if vix:
        html = sub(html, r'(id="risk-vix"[^>]*>)[0-9.]+',
                   lambda m: m.group(1) + f'{vix:.2f}')

    # 버핏 지표
    if buffett:
        html = sub(html, r'(<td>버핏 지표</td><td class="mono">)[0-9~.%]+',
                   lambda m: m.group(1) + f'{buffett}%')
        print(f"  ✅ 버핏 지표: {buffett}%")

    print("  ✅ 요약표 완료")

    # 푸터
    html = sub(html, r'최종 .{0,5}업데이트: [\d년월일 ]+',
               lambda m: f'최종 자동 업데이트: {today_kr}')

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ 저장 완료: {html_path}")

    # ── 일본어 버전 (index_ja.html) 업데이트 ──────────────────────
    ja_path = os.path.join(os.path.dirname(__file__), "index_ja.html")
    if os.path.exists(ja_path):
        print("\n[5] 일본어 버전 업데이트...")
        with open(ja_path, "r", encoding="utf-8") as f:
            ja = f.read()

        # ID 기반 업데이트 (한국어와 동일 — ID는 같음)
        ja = update_index_card(ja, "nk225",   nk225,   "JPY")
        ja = update_index_card(ja, "topix",   topix,   "JPY")
        ja = update_index_card(ja, "mothers", mothers, "JPY")
        ja = update_index_card(ja, "kospi",   kospi,   "KRW")
        ja = update_index_card(ja, "kosdaq",  kosdaq,  "KRW")
        ja = update_index_card(ja, "spx",     spx,     "USD")
        ja = update_index_card(ja, "ndx",     ndx,     "USD")
        ja = update_index_card(ja, "dji",     dji,     "USD")
        ja = update_index_card(ja, "rut",     rut,     "USD")
        ja = update_index_card(ja, "sox",     sox,     "USD")

        # 타임스탬프
        ja = set_text(ja, "idx-timestamp",
                      f"📊 前日終値基準 · 毎日6回自動更新 · 最終: {now_str}")

        # VIX (텍스트 매칭 — ID 없음)
        if vix:
            ja = sub(ja, r'(📊 VIX — 恐怖指数.*?<div class="bval"[^>]+>)[0-9.]+',
                     lambda m: m.group(1) + f'{vix:.2f}')
            ja = sub(ja, r'(VIX — 恐怖指数.*?<div class="blabel">)[^<]+',
                     lambda m: m.group(1) + f'{today} 終値')

        # 수익률 곡선 (텍스트 매칭)
        if spread is not None:
            ja = sub(ja, r'(📉 米国イールドカーブ.*?<div class="bval"[^>]+>)[^<]+',
                     lambda m: m.group(1) + f'{spread:+.2f}%p')
        if y2:
            ja = sub(ja, r'(<td>2年</td><td class="mono">)[0-9.]+(%</td>)',
                     lambda m: m.group(1) + f'{y2:.2f}' + m.group(2))
        if y10:
            ja = sub(ja, r'(<td>10年</td><td class="mono">)[0-9.]+(%</td>)',
                     lambda m: m.group(1) + f'{y10:.2f}' + m.group(2))
        if y30:
            ja = sub(ja, r'(<td>30年</td><td class="mono">)[0-9.]+(%</td>)',
                     lambda m: m.group(1) + f'{y30:.2f}' + m.group(2))

        # Fear & Greed
        if fg:
            fg_map = {(0,24):"EXTREME FEAR",(25,44):"FEAR",(45,55):"NEUTRAL",
                      (56,75):"GREED",(76,100):"EXTREME GREED"}
            fg_lbl = next(v for (lo,hi),v in fg_map.items() if lo <= fg <= hi)
            fg_col = "#e8495a" if fg<=24 else "#e8a030" if fg<=44 else "#dde3ee" if fg<=55 else "#1fbd8a"
            ja = sub(ja, r'(gauge-num" style="color:)[^"]+',
                     lambda m: m.group(1) + fg_col)
            ja = sub(ja, r'(gauge-num" style="color:[^"]+">)\d+',
                     lambda m: m.group(1) + str(fg))
            ja = sub(ja, r'(gauge-status" style="color:)[^"]+',
                     lambda m: m.group(1) + fg_col)
            ja = sub(ja, r'(gauge-status" style="color:[^"]+">)[^<]+',
                     lambda m: m.group(1) + fg_lbl)
            ja = sub(ja, r'(pbar-fill" style="width:)\d+(%;background:var\(--red\);)',
                     lambda m: m.group(1) + str(fg) + m.group(2))

        # 리스크 카드 (ID 기반)
        if wti:   ja = sub(ja, r'(id="risk-wti"[^>]*>)\$[0-9.]+',
                           lambda m: m.group(1) + f'${wti:.2f}')
        if brent: ja = sub(ja, r'(id="risk-brent"[^>]*>)\$[0-9.]+',
                           lambda m: m.group(1) + f'${brent:.0f}')
        if vix:   ja = sub(ja, r'(id="risk-vix"[^>]*>)[0-9.]+',
                           lambda m: m.group(1) + f'{vix:.2f}')

        # 요약표 (일본어 텍스트 매칭)
        if usdjpy:
            ja = sub(ja, r'(id="summary-usdjpy"[^>]*>)¥[0-9,.]+',
                     lambda m: m.group(1) + f'¥{usdjpy:,.2f}')
        if nk225:
            ja = sub(ja, r'(<td>日経225</td><td class="mono">)[0-9,]+',
                     lambda m: m.group(1) + f'{nk225["price"]:,.0f}')
        if vix:
            ja = sub(ja, r'(<td>VIX恐怖指数</td><td class="mono">)[0-9.]+',
                     lambda m: m.group(1) + f'{vix:.2f}')
        if spread:
            ja = sub(ja, r'(<td[^>]*>イールドカーブ[^<]*</td><td class="mono">)[+\-0-9.]+%p',
                     lambda m: m.group(1) + f'{spread:+.2f}%p')
        if pce_yoy:
            ja = sub(ja, r'(<td>コア PCE[^<]*</td><td class="mono">)[0-9.]+%',
                     lambda m: m.group(1) + f'{pce_yoy:.1f}%')
        if ism:
            ja = sub(ja, r'(<td>ISM製造業PMI[^<]*</td><td class="mono">)[0-9.]+',
                     lambda m: m.group(1) + f'{ism:.1f}')
        if michigan:
            ja = sub(ja, r'(<td>ミシガン消費者心理[^<]*</td><td class="mono">)[0-9.]+',
                     lambda m: m.group(1) + f'{michigan:.1f}')
        if nfp_chg is not None:
            ja = sub(ja, r'(<td>非農業 雇用[^<]*</td><td class="mono">)[+\-,\d]+',
                     lambda m: m.group(1) + f'{nfp_chg:+,}')
        if fg:
            ja = sub(ja, r'(<td>Fear &amp; Greed</td><td class="mono">)\d+',
                     lambda m: m.group(1) + str(fg))
        if fedwatch:
            ja = sub(ja, r'(<td>FedWatch[^<]*</td><td class="mono">)[0-9.]+%',
                     lambda m: m.group(1) + f'{fedwatch}%')
        if wti:
            ja = sub(ja, r'(<td>WTI原油</td><td class="mono">\$)[0-9.]+',
                     lambda m: m.group(1) + f'{wti:.2f}')
        if brent:
            ja = sub(ja, r'(<td>ブレント原油</td><td class="mono">\$)[0-9.]+',
                     lambda m: m.group(1) + f'{brent:.0f}')
        if buffett:
            ja = sub(ja, r'(<td>バフェット指標</td><td class="mono">)[0-9~.%]+',
                     lambda m: m.group(1) + f'{buffett}%')

        # 푸터
        today_ja = datetime.now(JST).strftime("%Y年%m月%d日")
        ja = sub(ja, r'最終自動更新: [\d年月日 ]+',
                 lambda m: f'最終自動更新: {today_ja}')

        with open(ja_path, "w", encoding="utf-8") as f:
            f.write(ja)
        print(f"  ✅ 일본어 버전 저장 완료: {ja_path}")

    print("=" * 55)

if __name__ == "__main__":
    update_dashboard()
