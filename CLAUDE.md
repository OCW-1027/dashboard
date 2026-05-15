# 글로벌 투자지표 대시보드 프로젝트

## 개요
- 한국어/일본어 이중 언어 글로벌 투자 지표 대시보드
- 배포: GitHub Pages (https://ocw-1027.github.io/dashboard/) + Cloudflare Pages (https://everybody-investment.pages.dev/)
- 단일 HTML 파일 아키텍처 (모든 CSS/JS 인라인)

## 주요 파일
- `index.html` (한국어 메인 대시보드, ~106KB)
- `index_ja.html` (일본어 메인 대시보드, ~107KB)
- `ir.html` / `ir_ja.html` (IR 페이지, KR/JA ~85-86KB) — **이중언어 동시 업데이트 필요**
- `study.html` / `study_ja.html` (학습 페이지, KR/JA ~111-112KB) — **이중언어 동시 업데이트 필요**
- `docs.html` (문서 페이지, ~8KB) — 단일 파일 (언어 분리 없음)
- `update_dashboard.py` (FRED/Yahoo/Stooq/multpl.com 자동 데이터 수집)
- `fetch_news.py` (텔레그램 채널 → Google Translate → news_kr.json/news_ja.json)
- `.github/workflows/update_dashboard.yml` (cron, 하루 6회)
- `news_kr.json` / `news_ja.json` (뉴스 피드)

### 이중언어 동시 업데이트 대상 페이지
`index.html` ↔ `index_ja.html`, `ir.html` ↔ `ir_ja.html`, `study.html` ↔ `study_ja.html` 세 쌍은 한국어/일본어 파일을 **항상 함께** 수정해야 한다. 한쪽만 변경되면 두 사이트의 콘텐츠가 어긋난다.

## 자동 갱신 지표 (update_dashboard.py)
- 지수: S&P500, NASDAQ, KOSPI, KOSDAQ, Nikkei, TOPIX
- 환율: USD/JPY, USD/KRW
- 채권: 미국 10Y/2Y/30Y, VIX, 수익률곡선
- 매크로: Core PCE, ISM PMI, Michigan, NFP, F&G, FedWatch, 버핏지표
- 원자재: WTI, Brent
- Shiller CAPE (multpl.com 스크래핑)

## 수동 입력 지표 (HTML 직접 편집 필요)
- CPI 헤드라인/코어 (BLS 발표일 매월 중순)
- ISM 가격지수 세부항목 (FRED NAPM 차단됨)
- BOJ 회의 결과 (날짜·표결 결과)
- F&G 게이지 (자동이지만 색상/위치는 수동)

## 수집 텔레그램 채널 (fetch_news.py)
- `@firstsquaw` (k 없음! firstsquawk는 봇/개인계정 ❌) - First Squawk, lang en
- `@FinancialJuice` - Financial Juice, lang en
- `@aetherjapanresearch` - 에테르 리서치, lang ko

## 작업 워크플로우
1. 한국어와 일본어 파일을 **항상 동시에** 업데이트
2. 변경 후 검증:
   - HTML: `<div>`, `<script>` 태그 밸런스 카운트
   - Python: `python -c "import ast; ast.parse(open('update_dashboard.py').read())"`
   - JS: `node --check ...` (있다면)
3. 키워드 검증 (예: '3.2%', '42.05' 등 새 값이 정확히 들어갔는지)
4. git add → commit → push

## 검증 필수 키워드 패턴
- 코어 PCE, 헤드라인 PCE, NFP, ISM, Shiller CAPE, F&G, BOJ
- 일본어: コアPCE (공백 없음!), ヘッドラインPCE, 非農業, ISM製造業, Shiller CAPE
- BLS 발표일자, 다음 발표/次回 발표일자

## 알려진 함정
- TradingView 무료 임베드 = 15-20분 지연 데이터 (유료 계정과 무관)
- TradingView 임베드는 미국 시장만, 일본/한국은 외부 링크
- Cloudflare 이메일 난독화: 평문 이메일 주소 → JS 오류, `[at]` 표기 사용
- `update_dashboard.py`의 일본어 PCE 매칭: `コア PCE` 아닌 `コアPCE` (공백 없음)
- regex DOTALL 모드 위험 (텍스트 블록 통째 삭제 가능)
- 일본어 BOJ: "次回会合" vs "次回会議" 미세 차이 주의

## 커밋 메시지 스타일
- "업데이트: <지표명> 최신 데이터 반영"
- "수정: <버그/이슈명>"
- "추가: <신규 기능>"
