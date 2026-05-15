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

## 일일 업데이트 워크플로우 (수동 데이터 갱신)

수동 입력 지표를 최신값으로 반영할 때 따르는 표준 절차. 위의 일반 "작업 워크플로우"보다 구체적인 순서·기준을 정의한다.

### 1. 검색 대상 지표

WebSearch로 공식 출처에서 확인할 지표:

| 지표 | 출처 | 발표 주기 |
|---|---|---|
| **CPI** (헤드라인/코어/MoM) | BLS | 매월 중순 |
| **PCE** (헤드라인/코어 YoY·MoM) | BEA | 매월 말 (대체로 마지막 주 금) |
| **NFP** (고용, 실업률, 임금) | BLS | 매월 첫 금요일 |
| **ISM 제조업 PMI** (세부 항목 포함) | ISM | 매월 1일 |
| **Michigan 소비자신뢰지수** | Umich / FRED | 예비치 매월 중순, 최종치 월말 |
| **Shiller CAPE** | Multpl / GuruFocus | 실시간 |
| **CNN Fear & Greed** | CNN | 실시간 |
| **BOJ 회의 결과** (정책금리, 표결, 다음 회의 일정) | BOJ 공식 | 부정기 (8회/년) |

### 2. 진행 순서

1. **현재값 추출**: `index.html`에서 지표별 현재 표시값을 `Grep`으로 먼저 추출 (검색하기 전에 무엇이 바뀔지 파악)
2. **웹 검색**: 각 출처에서 최신값·발표일자 확인. **반드시 연도(2026)를 쿼리에 포함**시켜 옛 데이터 혼입 방지
3. **비교표 작성**: `현재 / 신규 / 비고`로 변경 필수·선택·없음을 분리. 부수적으로 발견한 데이터 불일치(KR↔JA, 표↔노트 등)도 함께 보고
4. **사용자 확인 대기**: 비교표를 제시하고 진행 옵션(예: CAPE 미세 갱신 여부, PCE 불일치 동시 수정 여부)에 대한 명시적 결정을 받는다. **확인 없이 편집 진행 금지**
5. **편집** (KR ↔ JA 동시):
   - 표 셀 값, 라벨(N월 YoY), 진행바 width %·표기, 색상(`var(--red)`/`var(--amber)`/`var(--green)`), delta·tag 텍스트, note-a (시장 영향 한 줄), note-b, `data-written` 속성, 그리고 line 1127 인근 캘린더 표까지 일관 갱신
   - **반드시 양 파일에서 동일 line 부근에 대응되는 변경을 적용**
6. **검증** (다음 절 「검증 기준」)
7. **커밋·푸시**: 사용자 OK 확인 후 진행

### 3. 검증 기준

모든 항목이 통과해야 커밋 가능:

- **태그 밸런스**: `grep -o '<div' | wc -l` == `grep -o '</div>' | wc -l` 그리고 KR과 JA의 카운트가 **서로 동일**해야 함. `<script>`도 동일
- **새 키워드 존재**: 갱신된 모든 값(예: `3.8%`, `2026.05.13`, `42.18`, `(4/28)`, `2026.06.16`)이 양 파일에 같은 횟수로 등장
- **옛 키워드 제거**: 교체 대상 옛 값(예: `2026.04.10`, `(3/19)`, `42.05`, `헤드라인 CPI (3월`)이 양 파일에서 **0건**
- **KR/JA 대칭**: `git diff --stat`에서 두 파일의 insertion/deletion 수가 거의 같고, `git diff` 패치 위치(@@ line @@)도 거의 일치해야 함
- **상호 정합**: 같은 카드 내 표 셀 값과 note 본문의 수치가 일치해야 함 (예: 표 `3.5%` ↔ 노트 `3.5%`)

### 4. 커밋 메시지 형식

- 형식: `"업데이트: <주요 지표> (<핵심 값>) + <부수 변경 요약>"`
- 데이터 갱신은 `업데이트:`, 버그/데이터 불일치 수정은 `수정:`, 신규 기능 추가는 `추가:` 접두어
- 예시:
  - `"업데이트: CPI 4월 (3.8%) + BOJ 캘린더 + CAPE 미세조정, PCE 표 정합화"`
  - `"업데이트: NFP 5월 (+139K) + 실업률 4.2%"`
  - `"수정: KR/JA 헤드라인 PCE 표 값 불일치 정합화"`
