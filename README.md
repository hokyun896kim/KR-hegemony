# 🇰🇷 한국 헤게모니 트리 (KR Hegemony Tree)

미국판 헤게모니 트리 v1.2의 **동결된 스코어러를 그대로** 한국 코스피·코스닥에
적용한 버전입니다. 헤게모니 스프레드 = **영업이익 증가율(YoY) − 매출 증가율(YoY)**
은 국적과 무관하므로 로직은 동일하고, **데이터 소스와 링크·통화만 현지화**했습니다.

| 항목 | 미국판 | 한국판 |
|---|---|---|
| 종목 | 미국 상장 | 코스피(.KS)·코스닥(.KQ) |
| 1차 자료 | SEC EDGAR · 8-K | **DART 전자공시** · 분기보고서 |
| 보조 링크 | Yahoo · Finviz · SeekingAlpha | **네이버 금융 · FnGuide · 한경 컨센서스** |
| 통화 | $ (USD/KRW 환산) | **₩ (환산 없음)** |
| AI 프롬프트 | SEC·영문 | **DART · K-IFRS 연결 영업이익 · 한국어 웹검색** |
| 벤치마크(RS) | S&P500(SPY) | **코스피(^KS11)** |

> 스코어러(`scoreCandidate` 등)는 미국판과 **한 줄도 다르지 않습니다.** 동결 원칙 유지.

---

## 🚀 사용법

### 1) 데모로 바로 보기 (네트워크 불필요)
```bash
cd kr_hegemony
python build_tree_kr.py --demo      # data/tree_kr.json (합성 데모) 생성
python -m http.server 8899          # 로컬 서버
# 브라우저에서 http://localhost:8899 접속
```
> `file://` 로 직접 열면 CORS로 데이터가 안 읽힙니다. 로컬 서버나 Netlify로 여세요.

### 2) yfinance 실시간 (인터넷 필요, API 키 불필요)
```bash
pip install yfinance
cd kr_hegemony
python build_tree_kr.py             # yfinance 재무·시세 → data/tree_kr.json
python -m http.server 8899
```
- 간단하지만 한국 종목은 yfinance 재무 커버리지가 들쭉날쭉해 일부 분기TTM·PER이
  빕니다(스크리너가 자동 `—` 처리).

### 3) ⭐ DART 연동 (가장 정확 — 권장)
DART 연결손익계산서에서 매출·영업이익을 직접 받아 헤게모니 스프레드를 정확히
산출합니다. 시세·PER 은 yfinance 로 보완하는 하이브리드입니다.

```bash
# 1) 무료 API 키 발급: https://opendart.fss.or.kr → 인증키 신청·관리
export DART_API_KEY="발급받은_40자리_키"     # Windows: set DART_API_KEY=...
pip install yfinance pykrx
cd kr_hegemony
python build_tree_kr.py --dart       # DART(재무) + yfinance(시세·PER)
python -m http.server 8899
```
- **연간 스프레드**: DART 사업보고서의 당기/전기 매출·영업이익으로 정확 산출(연결 우선).
- **분기 TTM**: DART 누적공시를 분기 단독으로 역산(Q4=연간−9M누적)해 **미국판과
  동일한 정밀 4분기 롤링 TTM** 산출(8분기 연속 확보 시). 부족하면 누적 YoY 근사치로 폴백.
- **GitHub Actions** 로 매주 자동 갱신하려면 `DART_API_KEY` 를 레포 Secret 으로
  등록하고 위 명령을 워크플로에 넣으면 됩니다.

> DART 모듈(`dart.py`)의 파싱·스프레드 로직은 `test_dart.py` 로 오프라인 검증됨.

**수급(외국인·기관) 자동 포함**: `--dart`/기본 모드에서 `pip install pykrx` 가 있으면 최근 20거래일 외국인·기관 순매수와 외국인 지분율을 자동으로 받아 tree.json 에 넣고, 트레이드 카드·AI 프롬프트에 "🟢쌍끌이 매집 / 🔴외국인 이탈" 신호로 표시합니다. (pykrx 미설치 시 자동 생략)

### 4) 배포 (Netlify)
`kr_hegemony` 폴더(= `index.html` + `data/tree_kr.json`)를 통째로 드래그&드롭.

### 5) 🤖 자동 갱신 (GitHub Actions — 권장)
매주 자동으로 DART+pykrx 데이터를 새로 받아 `tree_kr.json` 을 갱신·커밋합니다.
워크플로 파일은 이미 들어있습니다: `.github/workflows/update_kr_tree.yml`

**준비 (딱 한 번):**
1. GitHub 레포 → **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `DART_API_KEY` / Value: opendart 무료 인증키
2. (선택) **Netlify 를 이 GitHub 레포에 연결** → Base directory `kr_hegemony`
   - 이러면 Actions 가 커밋할 때마다 사이트가 **자동 재배포**됩니다.
3. 끝. 매주 토요일 오전(KST) 자동 실행되고, **Actions 탭에서 "Run workflow"** 로
   수동 실행도 가능합니다.

> `DART_API_KEY` 가 없으면 yfinance 모드로 폴백합니다(커버리지 낮음).
> 워크플로는 빌드 전에 `pytest` 로 파싱 로직을 먼저 검증합니다.

---

## 📁 구성
```
kr_hegemony/
├── index.html            # 한국판 도구 (스코어러는 미국판 v1.2와 동일)
├── data/tree_kr.json     # 데이터 (build_tree_kr.py 로 생성)
├── build_tree_kr.py      # 빌더 (--demo 합성 / 기본 yfinance / --dart DART연동)
├── dart.py               # DART OpenAPI 백엔드 (연결재무 → 스프레드)
├── supply.py             # 수급 백엔드 (pykrx: 외국인·기관 순매수·지분율)
├── test_dart.py          # DART 파싱·스프레드 오프라인 테스트
├── test_supply.py        # 수급 집계·라벨 오프라인 테스트
└── README_kr.md
```

## 🔧 유니버스 편집
`build_tree_kr.py` 의 `UNIVERSE` 리스트에 `(티커, 종목명, 대섹터, 세부산업, 코드)`를
추가/수정하면 됩니다. (예: `("042700.KS", "한미반도체", "IT·반도체", "반도체 장비·소재", "SEMIEQ")`)

## 🧱 한계 & 메모
- **연간 스프레드**는 DART 연동 시 매우 정확합니다(연결 손익 직접 사용).
- **분기 q_op/q_spread**는 DART 누적 역산으로 정밀 4분기 TTM 을 씁니다(8분기 미확보
  시 누적 근사치 폴백). `dart.ttm_yoy` / `test_dart.py` 참고.
- **수급**은 pykrx 로 외국인·기관 순매수·지분율을 받아 표시(가격 반영도/선취매 판정과
  함께 보면 "선취매 권역인데 외국인 매집" 같은 강한 초기 신호를 잡습니다).
- **PER·시세**는 yfinance 의존(한국 PER 일부 결측 가능) → 스코어러가 forward PER
  폴백 후 결측이면 가벼운 검증 플래그(-4)로 처리.
- 스코어 로직은 **미국판 v1.2와 동일하게 동결** — n=작은 사후검증에 과적합하지
  않도록, 새 실패 유형이 실제로 나타날 때만 룰을 추가하세요.
