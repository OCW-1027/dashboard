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
        note_fetch_fail("Fear & Greed", e)
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
    """ISM 제조업 PMI.
    FRED NAPM은 ISM 라이선스 문제로 폐지돼 HTTP 400을 반환한다.
    과거 MANEMP(제조업 고용, 천명)로 폴백했으나 12,638 같은 값이 PMI 자리에
    들어갈 수 있어 제거했다 — 대체 소스를 붙이기 전까지 수동 입력 유지."""
    v = fetch_fred("NAPM")
    if v:
        print(f"  ✅ ISM PMI: {v}")
        return v
    note_known_skip("ISM 제조업 PMI", "FRED NAPM 시리즈 폐지(HTTP 400) — 수동 입력 유지")
    return None

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
            mon = int(obs[0]["date"][5:7])
            print(f"  ✅ 코어 PCE YoY: {yoy:.1f}% ({mon}월분)")
            return (round(yoy, 1), mon)
    except Exception as e:
        note_fetch_fail("코어 PCE", e)
        return None
    note_fetch_fail("코어 PCE", "FRED 관측치 13개 미만 — YoY 계산 불가")
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
            # PAYEMS 단위는 천명 — 대시보드 표기도 K(천명)이므로 그대로 사용
            chg_k = round(float(obs[0]["value"]) - float(obs[1]["value"]))
            mon = int(obs[0]["date"][5:7])
            print(f"  ✅ NFP 전월比: {chg_k:+,}K ({mon}월분)")
            return (chg_k, mon)
    except Exception as e:
        note_fetch_fail("비농업 고용(NFP)", e)
        return None
    note_fetch_fail("비농업 고용(NFP)", "FRED 관측치 2개 미만 — 전월비 계산 불가")
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
        note_known_skip("FedWatch", f"CME 엔드포인트 차단 ({e}) — 수동 입력 유지")
        return None
    note_known_skip("FedWatch", "응답에 동결 확률 필드 없음 — 수동 입력 유지")
    return None

# ── 버핏 지표 (Wilshire5000 / GDP) ────────────────────────────────
def fetch_buffett():
    """버핏 지표 (시총 ÷ GDP).
    FRED의 WILL5000INDFC / WILL5000PRFC / WILL5000PR이 모두 폐지돼 HTTP 400을
    반환한다. 검증된 시총 시리즈를 확보하기 전까지 수동 입력을 유지한다
    (임의 시리즈로 대체하면 정의가 다른 값이 들어간다)."""
    try:
        wilshire = fetch_fred("WILL5000INDFC")
        gdp      = fetch_fred("GDP")
        if wilshire and gdp:
            ratio = round(wilshire / gdp * 100, 1)
            print(f"  ✅ 버핏 지표: {ratio}%")
            return ratio
        note_known_skip("버핏 지표", "FRED Wilshire 시리즈 폐지(HTTP 400) — 수동 입력 유지")
    except Exception as e:
        print(f"  ❌ 버핏 지표 오류: {e}")
    return None

def fetch_shiller_cape():
    """multpl.com에서 Shiller CAPE Ratio 스크래핑.
    주의: 이 파일은 requests를 임포트하지 않는다 (urllib만 사용).
    과거 requests.get을 쓰다 NameError가 except에 삼켜져 조용히 None을 반환했다."""
    try:
        req = urllib.request.Request(
            "https://www.multpl.com/shiller-pe",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode("utf-8", "replace")
        # <meta description>의 "Current Shiller PE Ratio is XX.XX" 패턴
        m = re.search(r'Current Shiller PE Ratio is\s*([\d.]+)', text)
        if not m:
            # 백업: 본문 표기 "Current Shiller PE Ratio: XX.XX"
            m = re.search(r'Current Shiller PE Ratio[:\s]+([\d]+\.[\d]+)', text)
        if m:
            cape = float(m.group(1))
            print(f"  ✅ Shiller CAPE: {cape}")
            return cape
        note_fetch_fail("Shiller CAPE", "multpl.com 응답에서 값 패턴 미발견 — 페이지 구조 변경 의심")
        return None
    except Exception as e:
        note_fetch_fail("Shiller CAPE", e)
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

# ── 실패 추적 (GitHub Actions 로그 경고용) ────────────────────────
# 조용히 넘어가면 다음에 깨져도 알 수 없으므로, 실패를 모아 실행 말미에
# GitHub Actions 주석(annotation)과 스텝 요약으로 올린다.
MATCH_FAILURES = []   # (지표명, 파일, 정규식) — 패턴 매칭 실패 = HTML 구조 변경 의심
FETCH_FAILURES = []   # (지표명, 사유)        — 수집 자체 실패 (예상 밖)
KNOWN_SKIPS    = []   # (지표명, 사유)        — 상류 폐지·차단 등 알려진 상태

IS_GHA = os.environ.get("GITHUB_ACTIONS") == "true"
CURRENT_FILE = "index.html"   # sub() 호출 시점의 대상 파일 (로그 구분용)

def gha(kind, msg):
    """GitHub Actions 주석 출력. Actions에서는 실행 요약 화면에 뜨고,
    로컬에서는 평문으로 보인다. kind: warning | error | notice"""
    if IS_GHA:
        # 주석 본문에 개행이 있으면 파싱이 깨지므로 한 줄로 정리
        one_line = " ".join(str(msg).split())
        print("::%s file=update_dashboard.py::%s" % (kind, one_line))
    else:
        icon = {"warning": "⚠️", "error": "❌", "notice": "ℹ️"}.get(kind, "·")
        print("  %s %s" % (icon, msg))

_LABEL_STOP = "\\[(<" + chr(34) + chr(39)

def _derive_label(pattern):
    """정규식에서 사람이 읽을 지표명을 추출 (명시 label이 없을 때)."""
    m = re.search(r'id="([a-zA-Z0-9_-]+)"', pattern)
    if m:
        return m.group(1)
    # class="xref">라벨 / <td>라벨</td> 형태
    m = re.search(r'(?:xref">|<td>)\s*([^' + _LABEL_STOP + r']{2,30}?)\s*(?:\\\(|</|<)', pattern)
    if m and m.group(1).strip():
        return m.group(1).strip()
    # 한글/일본어 덩어리
    m = re.search("([가-힣ぁ-ヿ一-鿿][^" + _LABEL_STOP + "]{1,28})", pattern)
    if m:
        return m.group(1).strip()
    # 영문 클래스명 등
    m = re.search(r'([a-zA-Z][a-zA-Z0-9 &;_-]{2,28})', pattern)
    if m:
        return m.group(1).strip()
    return pattern[:40]

def sub(html, pattern, repl_fn, label=None):
    new_html, n = re.subn(pattern, repl_fn, html, count=1, flags=re.DOTALL)
    if n == 0:
        name = label or _derive_label(pattern)
        MATCH_FAILURES.append((name, CURRENT_FILE, pattern))
        gha("warning", "[%s] 패턴 매칭 실패 — HTML 구조 변경 의심 (%s)" % (name, CURRENT_FILE))
    return new_html

def note_fetch_fail(name, reason):
    """수집기가 값을 못 가져온 경우 (예상 밖 — 경고)."""
    FETCH_FAILURES.append((name, str(reason)))
    gha("warning", "[%s] 수집 실패 — %s" % (name, reason))

def note_known_skip(name, reason):
    """상류 폐지·차단 등 이미 파악된 사유 (경고 아님 — 알림)."""
    KNOWN_SKIPS.append((name, str(reason)))
    gha("notice", "[%s] 자동 수집 건너뜀 — %s" % (name, reason))

def report_failures():
    """실행 말미 요약. Actions 실행 요약 화면($GITHUB_STEP_SUMMARY)에도 남긴다."""
    print("\n" + "=" * 55)
    if not MATCH_FAILURES and not FETCH_FAILURES:
        print("✅ 패턴 매칭·수집 실패 없음")
    else:
        if MATCH_FAILURES:
            print("⚠️  패턴 매칭 실패 %d건 — HTML 구조 변경 의심" % len(MATCH_FAILURES))
            for name, fname, pat in MATCH_FAILURES:
                print("     · [%s] (%s)" % (name, fname))
                print("       정규식: %s" % pat[:90])
        if FETCH_FAILURES:
            print("⚠️  수집 실패 %d건" % len(FETCH_FAILURES))
            for name, reason in FETCH_FAILURES:
                print("     · [%s] %s" % (name, reason))
    if KNOWN_SKIPS:
        print("ℹ️  알려진 건너뜀 %d건 (상류 폐지·차단 — 수동 유지)" % len(KNOWN_SKIPS))
        for name, reason in KNOWN_SKIPS:
            print("     · [%s] %s" % (name, reason))
    print("=" * 55)

    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("## 대시보드 자동 업데이트 결과\n\n")
            if MATCH_FAILURES:
                f.write("### ⚠️ 패턴 매칭 실패 %d건 — HTML 구조 변경 의심\n\n" % len(MATCH_FAILURES))
                f.write("| 지표 | 파일 | 정규식 |\n|---|---|---|\n")
                for name, fname, pat in MATCH_FAILURES:
                    f.write("| %s | %s | `%s` |\n" % (name, fname, pat[:80].replace("|", "\\|")))
                f.write("\n")
            if FETCH_FAILURES:
                f.write("### ⚠️ 수집 실패 %d건\n\n" % len(FETCH_FAILURES))
                f.write("| 지표 | 사유 |\n|---|---|\n")
                for name, reason in FETCH_FAILURES:
                    f.write("| %s | %s |\n" % (name, reason.replace("|", "\\|")))
                f.write("\n")
            if not MATCH_FAILURES and not FETCH_FAILURES:
                f.write("✅ 패턴 매칭·수집 실패 없음\n\n")
            if KNOWN_SKIPS:
                f.write("<details><summary>ℹ️ 알려진 건너뜀 %d건 (수동 유지)</summary>\n\n" % len(KNOWN_SKIPS))
                for name, reason in KNOWN_SKIPS:
                    f.write("- **%s** — %s\n" % (name, reason))
                f.write("\n</details>\n")
    except Exception as e:
        print("  (스텝 요약 기록 실패: %s)" % e)

def latest_written_month(html):
    """HTML 내 data-written 속성 중 가장 최신 날짜의 (연, 월)을 반환.
    수동 노트가 하나도 없으면 None."""
    dates = re.findall(r'data-written="(\d{4})-(\d{2})-\d{2}"', html)
    if not dates:
        return None
    y, m = max(dates)
    return int(y), int(m)

def update_written_month(html, ja=False):
    """헤더의 '경제지표 최신: N월 기준' 표기 갱신.
    이 표기는 '마지막으로 수동 지표를 손본 시점'을 뜻하므로 cron 실행일(오늘)이
    아니라 data-written 속성 중 최신 날짜의 '월'을 사용한다. 자동 수집 지표만
    갱신된 날에는 값이 그대로 유지된다."""
    ym = latest_written_month(html)
    if ym is None:
        print("  ⚠️  data-written 속성 없음 — 경제지표 최신 표기 건너뜀")
        return html
    y, m = ym
    if ja:
        html = sub(html, r'(経済指標最新: <span class="date">)\d{4}年\d{1,2}月基準',
                   lambda mt: mt.group(1) + f'{y}年{m}月基準', label="経済指標最新 표기 (JA)")
    else:
        html = sub(html, r'(경제지표 최신: <span class="date">)\d{4}년 \d{1,2}월 기준',
                   lambda mt: mt.group(1) + f'{y}년 {m}월 기준', label="경제지표 최신 표기")
    print(f"  ✅ 경제지표 최신: {y}년 {m}월 기준 (수동 노트 최신일 기준)")
    return html

def set_text(html, el_id, text):
    return sub(html, rf'(id="{el_id}"[^>]*>).*?(?=<)',
               lambda m: m.group(1) + text, label=el_id)

def set_chg(html, el_id, content):
    return sub(html, rf'(<div[^>]*\bid="{el_id}"[^>]*>)(.*?)(</div>)',
               lambda m: m.group(1) + content + m.group(3), label=el_id)

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
    global CURRENT_FILE
    CURRENT_FILE = "index.html"
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
    cape     = fetch_shiller_cape()

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
                   lambda m: m.group(1) + f'{vix:.2f}', label="VIX 카드 값")
        html = sub(html, r'(VIX — 공포지수.*?<div class="blabel">)[^<]+',
                   lambda m: m.group(1) + f'{today} 종가', label="VIX 카드 라벨")

    # 수익률 곡선
    if spread is not None:
        html = sub(html, r'(📉 미국 수익률 곡선.*?<div class="bval"[^>]+>)[^<]+',
                   lambda m: m.group(1) + f'{spread:+.2f}%p', label="수익률 곡선 카드 값")
    if y2:
        html = sub(html, r'(<td>2년</td><td class="mono">)[0-9.]+(%</td>)',
                   lambda m: m.group(1) + f'{y2:.2f}' + m.group(2), label="수익률 곡선 2Y")
    if y10:
        html = sub(html, r'(<td>10년</td><td class="mono">)[0-9.]+(%</td>)',
                   lambda m: m.group(1) + f'{y10:.2f}' + m.group(2), label="수익률 곡선 10Y")
    if y30:
        html = sub(html, r'(<td>30년</td><td class="mono">)[0-9.]+(%</td>)',
                   lambda m: m.group(1) + f'{y30:.2f}' + m.group(2), label="수익률 곡선 30Y")

    # Fear & Greed
    if fg:
        fg_map = {(0,24):"EXTREME FEAR",(25,44):"FEAR",(45,55):"NEUTRAL",
                  (56,75):"GREED",(76,100):"EXTREME GREED"}
        fg_lbl = next(v for (lo,hi),v in fg_map.items() if lo <= fg <= hi)
        fg_col = "#e8495a" if fg<=24 else "#e8a030" if fg<=44 else "#dde3ee" if fg<=55 else "#1fbd8a"
        fg_mmdd = datetime.now(JST).strftime("%m/%d").lstrip("0").replace("/0", "/")
        html = sub(html, r'(gauge-num" style="color:)[^"]+',
                   lambda m: m.group(1) + fg_col, label="F&G 게이지 색상")
        html = sub(html, r'(gauge-num" style="color:[^"]+">)\d+',
                   lambda m: m.group(1) + str(fg), label="F&G 게이지 수치")
        html = sub(html, r'(gauge-status" style="color:)[^"]+',
                   lambda m: m.group(1) + fg_col, label="F&G 상태 색상")
        html = sub(html, r'(gauge-status" style="color:[^"]+">)[^<]+',
                   lambda m: m.group(1) + fg_lbl, label="F&G 상태 라벨")
        # F&G 카드의 pbar는 배경이 hex(게이지 색)라 var(--red) 패턴으로는 잡히지 않았다.
        # pbar-wrap margin-top:14px 는 F&G 카드에만 있어 앵커로 쓴다.
        html = sub(html, r'(pbar-wrap" style="margin-top:14px;"><div class="pbar-track"><div class="pbar-fill" style="width:)\d+(%;background:)#[0-9a-fA-F]{6}',
                   lambda m: m.group(1) + str(fg) + m.group(2) + fg_col, label="F&G 진행바")
        html = sub(html, r'(pbar-wrap" style="margin-top:14px;".{0,220}?<span style="color:)#[0-9a-fA-F]{6}(;font-weight:700;">▲ )\d+',
                   lambda m: m.group(1) + fg_col + m.group(2) + str(fg), label="F&G 진행바 라벨")
        # 게이지 좌측 '현재 (M/D) NN' 행
        html = sub(html, r'(<div class="gauge-item"><span>현재 \()\d+/\d+(\)</span><span style="color:)[^"]+(">)\d+',
                   lambda m: m.group(1) + fg_mmdd + m.group(2) + fg_col + ";" + m.group(3) + str(fg), label="F&G 현재값 행")

    # WTI / 브렌트
    if wti:
        html = sub(html, r'(WTI 원유</div><div class="sv"[^>]+>\$)[0-9.]+',
                   lambda m: m.group(1) + f'{wti:.2f}', label="WTI 리스크카드(텍스트)")
    if brent:
        html = sub(html, r'(브렌트유</div><div class="sv"[^>]+>\$)[0-9.]+',
                   lambda m: m.group(1) + f'{brent:.0f}', label="브렌트 리스크카드(텍스트)")

    # ── 요약표 업데이트 ──────────────────────────────────────────
    # USD/JPY 요약표
    if usdjpy:
        html = sub(html, r'(id="summary-usdjpy"[^>]*>)¥[0-9,.]+',
                   lambda m: m.group(1) + f'¥{usdjpy:,.2f}', label="USD/JPY 요약표")
        print(f"  ✅ USD/JPY: ¥{usdjpy:,.2f}")

    # 닛케이225
    if nk225:
        html = sub(html, r'(class="xref">닛케이225</a></td><td class="mono">)[0-9,]+',
                   lambda m: m.group(1) + f'{nk225["price"]:,.0f}', label="닛케이225 요약표")

    # VIX
    if vix:
        html = sub(html, r'(class="xref">VIX 공포지수</a></td><td class="mono">)[0-9.]+',
                   lambda m: m.group(1) + f'{vix:.2f}', label="VIX 요약표")

    # 수익률 곡선
    if spread:
        html = sub(html, r'(class="xref">수익률 곡선 10Y-2Y</a></td><td class="mono">)[+\-0-9.]+%p',
                   lambda m: m.group(1) + f'{spread:+.2f}%p', label="수익률 곡선 요약표")
        # 노트 본문의 '스프레드 +X.XX%p'도 같이 갱신 (표↔노트 수치 불일치 방지)
        html = sub(html, r'(스티프닝 가속\. 스프레드 )[+\-0-9.]+%p',
                   lambda m: m.group(1) + f'{spread:+.2f}%p', label="수익률 곡선 노트 스프레드")

    # 코어 PCE — 요약표 (값 + 월 라벨을 FRED 관측월로 동기화)
    if pce_yoy:
        v, mon = pce_yoy
        html = sub(html, r'(class="xref">코어 PCE \()\d+(월\)</a></td><td class="mono">)[0-9.]+(%)',
                   lambda m: m.group(1) + str(mon) + m.group(2) + f'{v:.1f}' + m.group(3), label="코어 PCE 요약표")
        print(f"  ✅ 코어 PCE YoY: {v:.1f}% ({mon}월)")

    # ISM PMI — FRED NAPM 폐지로 현재 항상 None (수동 유지)
    if ism:
        html = sub(html, r'(class="xref">ISM 제조업 PMI[^<]*</a></td><td class="mono">)[0-9.]+',
                   lambda m: m.group(1) + f'{ism:.1f}', label="ISM 제조업 PMI 요약표")

    # 미시간 소비심리 — 자동 갱신하지 않는다.
    # FRED UMCSENT는 '최종치'만 월 1회 늦게 들어와 대시보드가 표시하는
    # '예비치'보다 1~2개월 뒤처진다. 자동 반영하면 최신 예비치(예: 9월 47.8)가
    # 과거 최종치(예: 7월 55.2)로 되돌아간다.
    if michigan:
        note_known_skip("미시간 소비심리", f"FRED 최종치 {michigan:.1f} — 대시보드 예비치와 시점 불일치로 자동 반영 안 함")

    # 비농업 고용 — 요약표 (K 단위 + 월 라벨 동기화)
    if nfp_chg is not None:
        chg_k, mon = nfp_chg
        html = sub(html, r'(class="xref">비농업 고용 \()\d+(월\)</a></td><td class="mono">)[+\-−][\d,]+K',
                   lambda m: m.group(1) + str(mon) + m.group(2) + f'{chg_k:+,}K', label="비농업 고용(NFP) 요약표")
        print(f"  ✅ NFP: {chg_k:+,}K ({mon}월)")

    # Fear & Greed 요약표
    if fg:
        html = sub(html, r'(class="xref">Fear &amp; Greed</a></td><td class="mono">)\d+',
                   lambda m: m.group(1) + str(fg), label="Fear & Greed 요약표")

    # FedWatch — CME 403으로 현재 항상 None (수동 유지)
    if fedwatch:
        html = sub(html, r'(class="xref">FedWatch[^<]*</a></td><td class="mono">)[0-9.]+%',
                   lambda m: m.group(1) + f'{fedwatch}%', label="FedWatch 요약표")
        print(f"  ✅ FedWatch 동결확률: {fedwatch}%")

    # WTI / 브렌트 요약표
    if wti:
        html = sub(html, r'(class="xref">WTI 원유</a></td><td class="mono">\$)[0-9.]+',
                   lambda m: m.group(1) + f'{wti:.0f}', label="WTI 요약표")
    if brent:
        html = sub(html, r'(class="xref">브렌트유</a></td><td class="mono">\$)[0-9.]+',
                   lambda m: m.group(1) + f'{brent:.0f}', label="브렌트 요약표")

    # 리스크 카드 (WTI, 브렌트, VIX 실시간 반영)
    if wti:
        html = sub(html, r'(id="risk-wti"[^>]*>)\$[0-9.]+',
                   lambda m: m.group(1) + f'${wti:.2f}', label="WTI 리스크카드(id)")
    if brent:
        html = sub(html, r'(id="risk-brent"[^>]*>)\$[0-9.]+',
                   lambda m: m.group(1) + f'${brent:.0f}', label="브렌트 리스크카드(id)")
    if vix:
        html = sub(html, r'(id="risk-vix"[^>]*>)[0-9.]+',
                   lambda m: m.group(1) + f'{vix:.2f}', label="VIX 리스크카드(id)")

    # 버핏 지표
    if buffett:
        html = sub(html, r'(class="xref">버핏 지표</a></td><td class="mono">)[0-9~.%]+',
                   lambda m: m.group(1) + f'{buffett}%', label="버핏 지표 요약표")
        print(f"  ✅ 버핏 지표: {buffett}%")

    # Shiller CAPE
    if cape:
        # bval 직접 매칭 (Shiller CAPE 카드 본문)
        html = sub(html, r'(Shiller CAPE \(P/E10\).*?<div class="bval"[^>]+>)[0-9.]+',
                   lambda m: m.group(1) + f'{cape}', label="Shiller CAPE 카드 값")
        # 카드 헤더의 날짜 갱신
        today_iso = datetime.now(JST).strftime("%Y.%m.%d")
        html = sub(html, r'(Shiller CAPE \(P/E10\).*?)20\d\d\.\d\d\.\d\d 기준',
                   lambda m: m.group(1) + f'{today_iso} 기준', label="Shiller CAPE 기준일")
        print(f"  ✅ Shiller CAPE: {cape}")

    print("  ✅ 요약표 완료")

    # 헤더 '경제지표 최신' 표기 (수동 노트 최신일 기준)
    html = update_written_month(html)

    # 푸터
    html = sub(html, r'최종 .{0,5}업데이트: [\d년월일 ]+',
               lambda m: f'최종 자동 업데이트: {today_kr}', label="푸터 갱신일")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ 저장 완료: {html_path}")

    # ── 일본어 버전 (index_ja.html) 업데이트 ──────────────────────
    ja_path = os.path.join(os.path.dirname(__file__), "index_ja.html")
    if os.path.exists(ja_path):
        print("\n[5] 일본어 버전 업데이트...")
        CURRENT_FILE = "index_ja.html"   # 이후 sub() 경고에 파일명이 함께 찍힌다
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
                     lambda m: m.group(1) + f'{vix:.2f}', label="VIX 카드 값 (JA)")
            ja = sub(ja, r'(VIX — 恐怖指数.*?<div class="blabel">)[^<]+',
                     lambda m: m.group(1) + f'{today} 終値', label="VIX 카드 라벨 (JA)")

        # 수익률 곡선 (텍스트 매칭)
        if spread is not None:
            ja = sub(ja, r'(📉 米国イールドカーブ.*?<div class="bval"[^>]+>)[^<]+',
                     lambda m: m.group(1) + f'{spread:+.2f}%p', label="수익률 곡선 카드 값 (JA)")
        if y2:
            ja = sub(ja, r'(<td>2年</td><td class="mono">)[0-9.]+(%</td>)',
                     lambda m: m.group(1) + f'{y2:.2f}' + m.group(2), label="수익률 곡선 2Y (JA)")
        if y10:
            ja = sub(ja, r'(<td>10年</td><td class="mono">)[0-9.]+(%</td>)',
                     lambda m: m.group(1) + f'{y10:.2f}' + m.group(2), label="수익률 곡선 10Y (JA)")
        if y30:
            ja = sub(ja, r'(<td>30年</td><td class="mono">)[0-9.]+(%</td>)',
                     lambda m: m.group(1) + f'{y30:.2f}' + m.group(2), label="수익률 곡선 30Y (JA)")

        # Fear & Greed
        if fg:
            fg_map = {(0,24):"EXTREME FEAR",(25,44):"FEAR",(45,55):"NEUTRAL",
                      (56,75):"GREED",(76,100):"EXTREME GREED"}
            fg_lbl = next(v for (lo,hi),v in fg_map.items() if lo <= fg <= hi)
            fg_col = "#e8495a" if fg<=24 else "#e8a030" if fg<=44 else "#dde3ee" if fg<=55 else "#1fbd8a"
            fg_mmdd = datetime.now(JST).strftime("%m/%d").lstrip("0").replace("/0", "/")
            ja = sub(ja, r'(gauge-num" style="color:)[^"]+',
                     lambda m: m.group(1) + fg_col, label="F&G 게이지 색상 (JA)")
            ja = sub(ja, r'(gauge-num" style="color:[^"]+">)\d+',
                     lambda m: m.group(1) + str(fg), label="F&G 게이지 수치 (JA)")
            ja = sub(ja, r'(gauge-status" style="color:)[^"]+',
                     lambda m: m.group(1) + fg_col, label="F&G 상태 색상 (JA)")
            ja = sub(ja, r'(gauge-status" style="color:[^"]+">)[^<]+',
                     lambda m: m.group(1) + fg_lbl, label="F&G 상태 라벨 (JA)")
            ja = sub(ja, r'(pbar-wrap" style="margin-top:14px;"><div class="pbar-track"><div class="pbar-fill" style="width:)\d+(%;background:)#[0-9a-fA-F]{6}',
                     lambda m: m.group(1) + str(fg) + m.group(2) + fg_col, label="F&G 진행바 (JA)")
            ja = sub(ja, r'(pbar-wrap" style="margin-top:14px;".{0,220}?<span style="color:)#[0-9a-fA-F]{6}(;font-weight:700;">▲ )\d+',
                     lambda m: m.group(1) + fg_col + m.group(2) + str(fg), label="F&G 진행바 라벨 (JA)")
            ja = sub(ja, r'(<div class="gauge-item"><span>現在 \()\d+/\d+(\)</span><span style="color:)[^"]+(">)\d+',
                     lambda m: m.group(1) + fg_mmdd + m.group(2) + fg_col + ";" + m.group(3) + str(fg), label="F&G 현재값 행 (JA)")

        # 리스크 카드 (ID 기반)
        if wti:   ja = sub(ja, r'(id="risk-wti"[^>]*>)\$[0-9.]+',
                           lambda m: m.group(1) + f'${wti:.2f}', label="WTI 리스크카드(id) (JA)")
        if brent: ja = sub(ja, r'(id="risk-brent"[^>]*>)\$[0-9.]+',
                           lambda m: m.group(1) + f'${brent:.0f}', label="브렌트 리스크카드(id) (JA)")
        if vix:   ja = sub(ja, r'(id="risk-vix"[^>]*>)[0-9.]+',
                           lambda m: m.group(1) + f'{vix:.2f}', label="VIX 리스크카드(id) (JA)")

        # 요약표 (일본어 텍스트 매칭)
        if usdjpy:
            ja = sub(ja, r'(id="summary-usdjpy"[^>]*>)¥[0-9,.]+',
                     lambda m: m.group(1) + f'¥{usdjpy:,.2f}', label="USD/JPY 요약표 (JA)")
        if nk225:
            ja = sub(ja, r'(class="xref">日経225</a></td><td class="mono">)[0-9,]+',
                     lambda m: m.group(1) + f'{nk225["price"]:,.0f}', label="닛케이225 요약표 (JA)")
        if vix:
            ja = sub(ja, r'(class="xref">VIX ?恐怖指数</a></td><td class="mono">)[0-9.]+',
                     lambda m: m.group(1) + f'{vix:.2f}', label="VIX 요약표 (JA)")
        if spread:
            ja = sub(ja, r'(class="xref">イールドカーブ[^<]*</a></td><td class="mono">)[+\-0-9.]+%p',
                     lambda m: m.group(1) + f'{spread:+.2f}%p', label="수익률 곡선 요약표 (JA)")
            ja = sub(ja, r'(スティープニング加速。スプレッド)[+\-0-9.]+%p',
                     lambda m: m.group(1) + f'{spread:+.2f}%p', label="수익률 곡선 노트 스프레드 (JA)")
        if pce_yoy:
            v, mon = pce_yoy
            ja = sub(ja, r'(class="xref">コアPCE \()\d+(月\)</a></td><td class="mono">)[0-9.]+(%)',
                     lambda m: m.group(1) + str(mon) + m.group(2) + f'{v:.1f}' + m.group(3), label="코어 PCE 요약표 (JA)")
        if ism:
            ja = sub(ja, r'(class="xref">ISM製造業PMI[^<]*</a></td><td class="mono">)[0-9.]+',
                     lambda m: m.group(1) + f'{ism:.1f}', label="ISM 제조업 PMI 요약표 (JA)")
        if michigan:
            pass  # 미시간: FRED 최종치와 대시보드 예비치의 시점 불일치로 자동 반영 안 함
        if nfp_chg is not None:
            chg_k, mon = nfp_chg
            ja = sub(ja, r'(class="xref">非農業雇用 \()\d+(月\)</a></td><td class="mono">)[+\-−][\d,]+K',
                     lambda m: m.group(1) + str(mon) + m.group(2) + f'{chg_k:+,}K', label="비농업 고용(NFP) 요약표 (JA)")
        if fg:
            ja = sub(ja, r'(class="xref">Fear &amp; Greed</a></td><td class="mono">)\d+',
                     lambda m: m.group(1) + str(fg), label="Fear & Greed 요약표 (JA)")
        if fedwatch:
            ja = sub(ja, r'(class="xref">FedWatch[^<]*</a></td><td class="mono">)[0-9.]+%',
                     lambda m: m.group(1) + f'{fedwatch}%', label="FedWatch 요약표 (JA)")
        if wti:
            ja = sub(ja, r'(class="xref">WTI原油</a></td><td class="mono">\$)[0-9.]+',
                     lambda m: m.group(1) + f'{wti:.0f}', label="WTI 요약표 (JA)")
        if brent:
            ja = sub(ja, r'(class="xref">ブレント原油</a></td><td class="mono">\$)[0-9.]+',
                     lambda m: m.group(1) + f'{brent:.0f}', label="브렌트 요약표 (JA)")
        if buffett:
            ja = sub(ja, r'(class="xref">バフェット指標</a></td><td class="mono">)[0-9~.%]+',
                     lambda m: m.group(1) + f'{buffett}%', label="버핏 지표 요약표 (JA)")
        if cape:
            # 일본어 Shiller CAPE 카드 본문 직접 매칭
            ja = sub(ja, r'(Shiller CAPE \(P/E10\).*?<div class="bval"[^>]+>)[0-9.]+',
                     lambda m: m.group(1) + f'{cape}', label="Shiller CAPE 카드 값 (JA)")
            today_iso = datetime.now(JST).strftime("%Y.%m.%d")
            ja = sub(ja, r'(Shiller CAPE \(P/E10\).*?)20\d\d\.\d\d\.\d\d基準',
                     lambda m: m.group(1) + f'{today_iso}基準', label="Shiller CAPE 기준일 (JA)")

        # 헤더 '経済指標最新' 표기 (수동 노트 최신일 기준)
        ja = update_written_month(ja, ja=True)

        # 푸터
        today_ja = datetime.now(JST).strftime("%Y年%m月%d日")
        ja = sub(ja, r'最終自動更新: [\d年月日 ]+',
                 lambda m: f'最終自動更新: {today_ja}', label="푸터 갱신일 (JA)")

        with open(ja_path, "w", encoding="utf-8") as f:
            f.write(ja)
        print(f"  ✅ 일본어 버전 저장 완료: {ja_path}")

    print("=" * 55)
    report_failures()

if __name__ == "__main__":
    update_dashboard()
