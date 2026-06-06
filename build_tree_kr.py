#!/usr/bin/env python3
"""한국판 헤게모니 트리 데이터 빌더 — tree_kr.json 생성.

헤게모니 스프레드(영업이익YoY − 매출YoY)는 국적과 무관하므로, 미국판과
동일한 분석 틀을 한국 코스피/코스닥 종목에 적용한다.

데이터 소스: yfinance (한국 종목은 .KS=코스피, .KQ=코스닥 접미사).
- 연간/분기 손익계산서 → spread, q_spread, accel
- 시세(종목 vs ^KS11 코스피) → rs3, rs6, gap
- info → pe, fpe, 시가총액

사용:
  python build_tree_kr.py            # 실시간(yfinance) — 인터넷 필요
  python build_tree_kr.py --demo     # 오프라인 데모(합성값) — 네트워크 불필요

출력: data/tree_kr.json  (HTML 도구가 ./data/tree_kr.json 을 읽음)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path

# ─────────────────────────── 한국 유니버스 ───────────────────────────
# (티커, 종목명, 대섹터, 세부산업, 세부산업코드)
# 코스피 대형주 + 코스닥 성장주 ~190종목. 세부산업당 동종업체 4~8개를 확보해
# "세부산업 내부 비교(중앙값·순위)"가 의미를 갖도록 구성. (.KS=코스피 / .KQ=코스닥)
# ※ DART 재무·pykrx 수급은 6자리 코드만 쓰므로 접미사가 틀려도 핵심 지표엔
#    영향 없음(접미사는 yfinance 시세·PER 조회에만 사용).
UNIVERSE = [
    # ── IT·반도체 ───────────────────────────────────────────────
    ("005930.KS", "삼성전자", "IT·반도체", "반도체", "SEMI"),
    ("000660.KS", "SK하이닉스", "IT·반도체", "반도체", "SEMI"),
    ("000990.KS", "DB하이텍", "IT·반도체", "반도체", "SEMI"),
    ("042700.KS", "한미반도체", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("058470.KQ", "리노공업", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("240810.KQ", "원익IPS", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("357780.KQ", "솔브레인", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("005290.KQ", "동진쎄미켐", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("036930.KQ", "주성엔지니어링", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("095340.KQ", "ISC", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("140860.KQ", "파크시스템스", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("064760.KQ", "티씨케이", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("104830.KQ", "원익머트리얼즈", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("222800.KQ", "심텍", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("178320.KQ", "서진시스템", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("095610.KQ", "테스", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("089030.KQ", "테크윙", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("067310.KQ", "하나마이크론", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("009150.KS", "삼성전기", "IT·반도체", "전자부품", "ELEC"),
    ("011070.KS", "LG이노텍", "IT·반도체", "전자부품", "ELEC"),
    ("066570.KS", "LG전자", "IT·반도체", "전자부품", "ELEC"),
    ("034220.KS", "LG디스플레이", "IT·반도체", "디스플레이", "DISP"),
    ("108320.KQ", "LX세미콘", "IT·반도체", "디스플레이", "DISP"),
    ("213420.KQ", "덕산네오룩스", "IT·반도체", "디스플레이", "DISP"),
    ("056190.KQ", "에스에프에이", "IT·반도체", "디스플레이", "DISP"),
    # ── 2차전지·소재 ────────────────────────────────────────────
    ("373220.KS", "LG에너지솔루션", "2차전지·소재", "2차전지 셀", "BATT"),
    ("006400.KS", "삼성SDI", "2차전지·소재", "2차전지 셀", "BATT"),
    ("051910.KS", "LG화학", "2차전지·소재", "2차전지 셀", "BATT"),
    ("247540.KQ", "에코프로비엠", "2차전지·소재", "2차전지 소재·장비", "BATTMAT"),
    ("086520.KQ", "에코프로", "2차전지·소재", "2차전지 소재·장비", "BATTMAT"),
    ("003670.KS", "포스코퓨처엠", "2차전지·소재", "2차전지 소재·장비", "BATTMAT"),
    ("020150.KS", "롯데에너지머티리얼즈", "2차전지·소재", "2차전지 소재·장비", "BATTMAT"),
    ("005070.KS", "코스모신소재", "2차전지·소재", "2차전지 소재·장비", "BATTMAT"),
    ("278280.KQ", "천보", "2차전지·소재", "2차전지 소재·장비", "BATTMAT"),
    ("348370.KQ", "엔켐", "2차전지·소재", "2차전지 소재·장비", "BATTMAT"),
    ("066970.KQ", "엘앤에프", "2차전지·소재", "2차전지 소재·장비", "BATTMAT"),
    ("137400.KQ", "피엔티", "2차전지·소재", "2차전지 소재·장비", "BATTMAT"),
    ("137950.KQ", "대주전자재료", "2차전지·소재", "2차전지 소재·장비", "BATTMAT"),
    # ── 바이오·헬스케어 ─────────────────────────────────────────
    ("207940.KS", "삼성바이오로직스", "바이오·헬스케어", "바이오", "BIO"),
    ("068270.KS", "셀트리온", "바이오·헬스케어", "바이오", "BIO"),
    ("196170.KQ", "알테오젠", "바이오·헬스케어", "바이오", "BIO"),
    ("028300.KQ", "HLB", "바이오·헬스케어", "바이오", "BIO"),
    ("326030.KS", "SK바이오팜", "바이오·헬스케어", "바이오", "BIO"),
    ("302440.KS", "SK바이오사이언스", "바이오·헬스케어", "바이오", "BIO"),
    ("145020.KQ", "휴젤", "바이오·헬스케어", "바이오", "BIO"),
    ("214450.KQ", "파마리서치", "바이오·헬스케어", "바이오", "BIO"),
    ("141080.KQ", "리가켐바이오", "바이오·헬스케어", "바이오", "BIO"),
    ("085660.KQ", "차바이오텍", "바이오·헬스케어", "바이오", "BIO"),
    ("000100.KS", "유한양행", "바이오·헬스케어", "제약", "PHARMA"),
    ("069620.KS", "대웅제약", "바이오·헬스케어", "제약", "PHARMA"),
    ("128940.KS", "한미약품", "바이오·헬스케어", "제약", "PHARMA"),
    ("185750.KS", "종근당", "바이오·헬스케어", "제약", "PHARMA"),
    ("170900.KS", "동아에스티", "바이오·헬스케어", "제약", "PHARMA"),
    ("001060.KS", "JW중외제약", "바이오·헬스케어", "제약", "PHARMA"),
    ("271980.KS", "제일약품", "바이오·헬스케어", "제약", "PHARMA"),
    ("087010.KQ", "펩트론", "바이오·헬스케어", "제약", "PHARMA"),
    ("145720.KS", "덴티움", "바이오·헬스케어", "의료기기", "MEDDEV"),
    ("287410.KQ", "제이시스메디칼", "바이오·헬스케어", "의료기기", "MEDDEV"),
    ("214150.KQ", "클래시스", "바이오·헬스케어", "의료기기", "MEDDEV"),
    ("041960.KQ", "코미팜", "바이오·헬스케어", "의료기기", "MEDDEV"),
    # ── 자동차 ──────────────────────────────────────────────────
    ("005380.KS", "현대차", "자동차", "완성차", "AUTO"),
    ("000270.KS", "기아", "자동차", "완성차", "AUTO"),
    ("012330.KS", "현대모비스", "자동차", "자동차 부품", "AUTOPART"),
    ("011210.KS", "현대위아", "자동차", "자동차 부품", "AUTOPART"),
    ("204320.KS", "HL만도", "자동차", "자동차 부품", "AUTOPART"),
    ("018880.KS", "한온시스템", "자동차", "자동차 부품", "AUTOPART"),
    ("161390.KS", "한국타이어앤테크놀로지", "자동차", "자동차 부품", "AUTOPART"),
    ("073240.KS", "금호타이어", "자동차", "자동차 부품", "AUTOPART"),
    ("064350.KS", "현대로템", "자동차", "자동차 부품", "AUTOPART"),
    ("086280.KS", "현대글로비스", "자동차", "자동차 부품", "AUTOPART"),
    # ── 금융 ────────────────────────────────────────────────────
    ("105560.KS", "KB금융", "금융", "은행·지주", "BANK"),
    ("055550.KS", "신한지주", "금융", "은행·지주", "BANK"),
    ("086790.KS", "하나금융지주", "금융", "은행·지주", "BANK"),
    ("316140.KS", "우리금융지주", "금융", "은행·지주", "BANK"),
    ("138930.KS", "BNK금융지주", "금융", "은행·지주", "BANK"),
    ("175330.KS", "JB금융지주", "금융", "은행·지주", "BANK"),
    ("139130.KS", "DGB금융지주", "금융", "은행·지주", "BANK"),
    ("005940.KS", "NH투자증권", "금융", "증권", "SEC"),
    ("016360.KS", "삼성증권", "금융", "증권", "SEC"),
    ("006800.KS", "미래에셋증권", "금융", "증권", "SEC"),
    ("039490.KS", "키움증권", "금융", "증권", "SEC"),
    ("003540.KS", "대신증권", "금융", "증권", "SEC"),
    ("138040.KS", "메리츠금융지주", "금융", "증권", "SEC"),
    ("000810.KS", "삼성화재", "금융", "보험·카드", "INS"),
    ("032830.KS", "삼성생명", "금융", "보험·카드", "INS"),
    ("005830.KS", "DB손해보험", "금융", "보험·카드", "INS"),
    ("001450.KS", "현대해상", "금융", "보험·카드", "INS"),
    ("088350.KS", "한화생명", "금융", "보험·카드", "INS"),
    ("029780.KS", "삼성카드", "금융", "보험·카드", "INS"),
    # ── 인터넷·게임 ─────────────────────────────────────────────
    ("035420.KS", "NAVER", "인터넷·게임", "인터넷 플랫폼", "NET"),
    ("035720.KS", "카카오", "인터넷·게임", "인터넷 플랫폼", "NET"),
    ("259960.KS", "크래프톤", "인터넷·게임", "게임", "GAME"),
    ("036570.KS", "엔씨소프트", "인터넷·게임", "게임", "GAME"),
    ("251270.KS", "넷마블", "인터넷·게임", "게임", "GAME"),
    ("263750.KQ", "펄어비스", "인터넷·게임", "게임", "GAME"),
    ("112040.KQ", "위메이드", "인터넷·게임", "게임", "GAME"),
    ("293490.KQ", "카카오게임즈", "인터넷·게임", "게임", "GAME"),
    ("078340.KQ", "컴투스", "인터넷·게임", "게임", "GAME"),
    ("095660.KQ", "네오위즈", "인터넷·게임", "게임", "GAME"),
    ("192080.KQ", "더블유게임즈", "인터넷·게임", "게임", "GAME"),
    ("225570.KQ", "넥슨게임즈", "인터넷·게임", "게임", "GAME"),
    # ── 소재·산업재 ─────────────────────────────────────────────
    ("005490.KS", "POSCO홀딩스", "소재·산업재", "철강·비철", "STEEL"),
    ("010130.KS", "고려아연", "소재·산업재", "철강·비철", "STEEL"),
    ("004020.KS", "현대제철", "소재·산업재", "철강·비철", "STEEL"),
    ("103140.KS", "풍산", "소재·산업재", "철강·비철", "STEEL"),
    ("000670.KS", "영풍", "소재·산업재", "철강·비철", "STEEL"),
    ("011170.KS", "롯데케미칼", "소재·산업재", "화학", "CHEM"),
    ("011780.KS", "금호석유", "소재·산업재", "화학", "CHEM"),
    ("298050.KS", "효성첨단소재", "소재·산업재", "화학", "CHEM"),
    ("002380.KS", "KCC", "소재·산업재", "화학", "CHEM"),
    ("014680.KS", "한솔케미칼", "소재·산업재", "화학", "CHEM"),
    ("285130.KS", "SK케미칼", "소재·산업재", "화학", "CHEM"),
    ("120110.KS", "코오롱인더", "소재·산업재", "화학", "CHEM"),
    ("298000.KS", "효성화학", "소재·산업재", "화학", "CHEM"),
    ("010950.KS", "S-Oil", "소재·산업재", "정유·에너지", "OIL"),
    ("096770.KS", "SK이노베이션", "소재·산업재", "정유·에너지", "OIL"),
    ("267250.KS", "HD현대", "소재·산업재", "정유·에너지", "OIL"),
    ("009540.KS", "HD한국조선해양", "소재·산업재", "조선", "SHIP"),
    ("010620.KS", "HD현대미포", "소재·산업재", "조선", "SHIP"),
    ("042660.KS", "한화오션", "소재·산업재", "조선", "SHIP"),
    ("010140.KS", "삼성중공업", "소재·산업재", "조선", "SHIP"),
    ("042670.KS", "HD현대인프라코어", "소재·산업재", "기계·중공업", "MACH"),
    ("267270.KS", "HD현대건설기계", "소재·산업재", "기계·중공업", "MACH"),
    ("241560.KS", "두산밥캣", "소재·산업재", "기계·중공업", "MACH"),
    ("034020.KS", "두산에너빌리티", "소재·산업재", "기계·중공업", "MACH"),
    ("000150.KS", "두산", "소재·산업재", "기계·중공업", "MACH"),
    ("010120.KS", "LS일렉트릭", "소재·산업재", "기계·중공업", "MACH"),
    ("006260.KS", "LS", "소재·산업재", "기계·중공업", "MACH"),
    ("000720.KS", "현대건설", "소재·산업재", "건설", "CONST"),
    ("028260.KS", "삼성물산", "소재·산업재", "건설", "CONST"),
    ("047040.KS", "대우건설", "소재·산업재", "건설", "CONST"),
    ("006360.KS", "GS건설", "소재·산업재", "건설", "CONST"),
    ("375500.KS", "DL이앤씨", "소재·산업재", "건설", "CONST"),
    ("294870.KS", "HDC현대산업개발", "소재·산업재", "건설", "CONST"),
    ("028050.KS", "삼성E&A", "소재·산업재", "건설", "CONST"),
    ("047050.KS", "포스코인터내셔널", "소재·산업재", "상사", "TRADE"),
    ("001120.KS", "LX인터내셔널", "소재·산업재", "상사", "TRADE"),
    ("001250.KS", "GS글로벌", "소재·산업재", "상사", "TRADE"),
    # ── 소비재 ──────────────────────────────────────────────────
    ("090430.KS", "아모레퍼시픽", "소비재", "화장품", "COSM"),
    ("051900.KS", "LG생활건강", "소비재", "화장품", "COSM"),
    ("161890.KS", "한국콜마", "소비재", "화장품", "COSM"),
    ("192820.KS", "코스맥스", "소비재", "화장품", "COSM"),
    ("237880.KQ", "클리오", "소비재", "화장품", "COSM"),
    ("097950.KS", "CJ제일제당", "소비재", "음식료·담배", "FOOD"),
    ("271560.KS", "오리온", "소비재", "음식료·담배", "FOOD"),
    ("004370.KS", "농심", "소비재", "음식료·담배", "FOOD"),
    ("033780.KS", "KT&G", "소비재", "음식료·담배", "FOOD"),
    ("280360.KS", "롯데웰푸드", "소비재", "음식료·담배", "FOOD"),
    ("007310.KS", "오뚜기", "소비재", "음식료·담배", "FOOD"),
    ("003230.KS", "삼양식품", "소비재", "음식료·담배", "FOOD"),
    ("001680.KS", "대상", "소비재", "음식료·담배", "FOOD"),
    ("005180.KS", "빙그레", "소비재", "음식료·담배", "FOOD"),
    ("282330.KS", "BGF리테일", "소비재", "유통", "RETAIL"),
    ("023530.KS", "롯데쇼핑", "소비재", "유통", "RETAIL"),
    ("139480.KS", "이마트", "소비재", "유통", "RETAIL"),
    ("069960.KS", "현대백화점", "소비재", "유통", "RETAIL"),
    ("057050.KS", "현대홈쇼핑", "소비재", "유통", "RETAIL"),
    ("008770.KS", "호텔신라", "소비재", "유통", "RETAIL"),
    ("007070.KS", "GS리테일", "소비재", "유통", "RETAIL"),
    ("105630.KS", "한세실업", "소비재", "의류·패션", "APPAREL"),
    ("020000.KS", "한섬", "소비재", "의류·패션", "APPAREL"),
    ("111770.KS", "영원무역", "소비재", "의류·패션", "APPAREL"),
    # ── 통신·유틸리티 ───────────────────────────────────────────
    ("017670.KS", "SK텔레콤", "통신·유틸리티", "통신", "TELCO"),
    ("030200.KS", "KT", "통신·유틸리티", "통신", "TELCO"),
    ("032640.KS", "LG유플러스", "통신·유틸리티", "통신", "TELCO"),
    ("015760.KS", "한국전력", "통신·유틸리티", "유틸리티", "UTIL"),
    ("036460.KS", "한국가스공사", "통신·유틸리티", "유틸리티", "UTIL"),
    ("051600.KS", "한전KPS", "통신·유틸리티", "유틸리티", "UTIL"),
    ("052690.KS", "한전기술", "통신·유틸리티", "유틸리티", "UTIL"),
    # ── 미디어·엔터 ─────────────────────────────────────────────
    ("352820.KS", "하이브", "미디어·엔터", "엔터", "ENT"),
    ("041510.KQ", "에스엠", "미디어·엔터", "엔터", "ENT"),
    ("122870.KQ", "와이지엔터테인먼트", "미디어·엔터", "엔터", "ENT"),
    ("035900.KQ", "JYP Ent.", "미디어·엔터", "엔터", "ENT"),
    ("253450.KQ", "스튜디오드래곤", "미디어·엔터", "미디어·콘텐츠", "MEDIA"),
    ("035760.KQ", "CJ ENM", "미디어·엔터", "미디어·콘텐츠", "MEDIA"),
    ("036420.KQ", "콘텐트리중앙", "미디어·엔터", "미디어·콘텐츠", "MEDIA"),
    # ── 운송 ────────────────────────────────────────────────────
    ("003490.KS", "대한항공", "운송", "항공", "AIR"),
    ("089590.KS", "제주항공", "운송", "항공", "AIR"),
    ("272450.KS", "진에어", "운송", "항공", "AIR"),
    ("011200.KS", "HMM", "운송", "해운", "SHIPPING"),
    ("028670.KS", "팬오션", "운송", "해운", "SHIPPING"),
    ("005880.KS", "대한해운", "운송", "해운", "SHIPPING"),
    ("000120.KS", "CJ대한통운", "운송", "물류", "LOGI"),
    ("002320.KS", "한진", "운송", "물류", "LOGI"),
    # ── 방산·우주 ───────────────────────────────────────────────
    ("012450.KS", "한화에어로스페이스", "방산·우주", "방산·우주", "DEFENSE"),
    ("047810.KS", "한국항공우주", "방산·우주", "방산·우주", "DEFENSE"),
    ("079550.KS", "LIG넥스원", "방산·우주", "방산·우주", "DEFENSE"),
    # ── IT 서비스 ───────────────────────────────────────────────
    ("018260.KS", "삼성에스디에스", "IT 서비스", "IT서비스", "ITSVC"),
    ("307950.KS", "현대오토에버", "IT 서비스", "IT서비스", "ITSVC"),
    ("022100.KQ", "포스코DX", "IT 서비스", "IT서비스", "ITSVC"),
    ("030520.KQ", "한글과컴퓨터", "IT 서비스", "IT서비스", "ITSVC"),
    # ── 지주 ────────────────────────────────────────────────────
    ("003550.KS", "LG", "지주", "지주회사", "HOLDING"),
    ("034730.KS", "SK", "지주", "지주회사", "HOLDING"),
    ("000880.KS", "한화", "지주", "지주회사", "HOLDING"),
    ("001040.KS", "CJ", "지주", "지주회사", "HOLDING"),
    ("004990.KS", "롯데지주", "지주", "지주회사", "HOLDING"),
]


def _seed(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16) % (2**32)


def _dart_url(tk: str) -> str:
    """DART 전자공시 검색 (티커 숫자부분으로)."""
    code = tk.split(".")[0]
    return f"https://dart.fss.or.kr/dsab007/main.do?option=corp&textCrpNm={code}"


def _member_synth(tk: str, nm: str) -> dict:
    """오프라인 데모용 합성 헤게모니 지표 (결정론적). 실제와 무관."""
    import numpy as np
    rng = np.random.default_rng(_seed(tk))
    rev = round(float(rng.uniform(-8, 28)), 1)            # 매출 YoY
    spread = round(float(rng.uniform(-12, 28)), 1)        # 연간 스프레드
    op = round(rev + spread, 1)                           # 영업이익 YoY
    # 분기 TTM — 일부는 가속, 일부는 둔화, 일부는 흑자전환 기저
    q_spread = round(spread + float(rng.uniform(-10, 14)), 1)
    accel = round(q_spread - spread, 1)
    # 흑자전환 기저효과 케이스 (가끔)
    q_op = round(op + float(rng.uniform(-5, 20)), 1)
    if rng.random() < 0.15:
        q_op = round(float(rng.uniform(55, 90)), 1)       # 분기 영익 폭등(기저)
    rs6 = round(float(rng.uniform(-30, 45)), 1)           # KOSPI 대비 6M
    # rs3 — 점화/냉각 다양화
    rs3 = round(rs6 * float(rng.uniform(-0.4, 1.6)) + float(rng.uniform(-8, 18)), 1)
    gap = round(float(rng.uniform(2, 12)), 1)
    gaplvl = "H" if gap > 8 else "L" if gap < 4 else "M"
    pe = None if rng.random() < 0.2 else round(float(rng.uniform(6, 40)), 1)
    fpe = None if pe is None or rng.random() < 0.3 else round(pe * 0.9, 1)
    from_high = round(float(rng.uniform(-45, -1)), 1)   # 52주 고점 대비(데모)
    # 수급(데모 합성): 외국인·기관 순매수(억), 외국인 지분율
    fnet = round(float(rng.uniform(-400, 600)), 1)
    inet = round(float(rng.uniform(-300, 400)), 1)
    fpct = round(float(rng.uniform(3, 55)), 1)
    import supply as _sup
    days = int(rng.integers(-30, 70))
    return {
        "tk": tk, "nm": nm, "spread": spread, "q_spread": q_spread,
        "accel": accel, "rs3": rs3, "rs6": rs6, "gap": gap, "gaplvl": gaplvl,
        "from_high": from_high,
        "foreign_net": fnet, "inst_net": inet, "foreign_pct": fpct,
        "supply": _sup.supply_label(fnet, inet),
        "op": op, "rev": rev, "q_op": q_op, "pe": pe, "fpe": fpe, "peg": None,
        "q_note": "정상", "d_until": days,
        "ir": {"date": "2026-05", "docs": [
            {"label": "DART 사업·분기보고서", "url": _dart_url(tk)}]},
    }


def _member_yf(tk: str, nm: str) -> dict:
    """실시간(yfinance) 재무 기반 스프레드. 시세·PER·수급은 build()에서 일괄 merge."""
    import yfinance as yf

    t = yf.Ticker(tk)

    def yoy(df, names):
        if df is None or getattr(df, "empty", True):
            return None
        for n in names:
            if n in df.index:
                s = df.loc[n].dropna().sort_index()
                if len(s) >= 2 and s.iloc[-2] not in (0,):
                    return round((s.iloc[-1] / abs(s.iloc[-2]) - 1) * 100, 1)
        return None

    def ttm_yoy(df, names):
        if df is None or getattr(df, "empty", True):
            return None
        for n in names:
            if n in df.index:
                s = df.loc[n].dropna().sort_index()
                if len(s) >= 8:
                    now, prev = s.iloc[-4:].sum(), s.iloc[-8:-4].sum()
                    if prev:
                        return round((now / abs(prev) - 1) * 100, 1)
        return None

    REV = ["Total Revenue", "TotalRevenue", "Operating Revenue"]
    OP = ["Operating Income", "OperatingIncome", "Total Operating Income As Reported"]
    a, q = None, None
    try:
        a = t.income_stmt
    except Exception:
        pass
    try:
        q = t.quarterly_income_stmt
    except Exception:
        pass
    rev, op = yoy(a, REV), yoy(a, OP)
    spread = round(op - rev, 1) if (rev is not None and op is not None) else None
    t_rev, t_op = ttm_yoy(q, REV), ttm_yoy(q, OP)
    q_spread = round(t_op - t_rev, 1) if (t_rev is not None and t_op is not None) else None
    accel = round(q_spread - spread, 1) if (q_spread is not None and spread is not None) else None

    # 시세·PER·수급은 build()에서 배치로 일괄 산출 → 여기선 재무(스프레드)만.
    return {
        "tk": tk, "nm": nm, "spread": spread, "q_spread": q_spread,
        "accel": accel, "op": op, "rev": rev, "q_op": t_op,
        "q_note": "정상", "d_until": None,
        "ir": {"date": datetime.today().strftime("%Y-%m"), "docs": [
            {"label": "DART 사업·분기보고서", "url": _dart_url(tk)}]},
    }


def _price_maps(tickers: list[str], bench) -> dict:
    """전 종목 시세를 yf.download 로 '한 번에' 받아 {tk: {rs3,rs6,gap,gaplvl,from_high}}.

    종목별 t.history(196회) 대신 단일 일괄 호출 → throttle 위험·시간 대폭 감소.
    """
    import yfinance as yf
    out = {tk: {"rs3": None, "rs6": None, "gap": None,
                "gaplvl": "M", "from_high": None} for tk in tickers}
    try:
        data = yf.download(tickers, period="1y", auto_adjust=True,
                           group_by="ticker", threads=True, progress=False)
    except Exception:
        return out

    def series(tk, field):
        try:
            return data[tk][field].dropna()
        except Exception:
            return None

    have_bench = bench is not None and len(bench) > 130

    def ret(s, n):
        return (s.iloc[-1] / s.iloc[-n] - 1) * 100

    for tk in tickers:
        c = series(tk, "Close")
        if c is None or len(c) == 0:
            continue
        rec = out[tk]
        hi = float(c.iloc[-252:].max())
        rec["from_high"] = round((float(c.iloc[-1]) / hi - 1) * 100, 1) if hi else None
        if len(c) > 130 and have_bench:
            rec["rs3"] = round(ret(c, 63) - ret(bench, 63), 1)
            rec["rs6"] = round(ret(c, 126) - ret(bench, 126), 1)
        o = series(tk, "Open")
        if o is not None and len(o):
            g = ((o - c.shift(1)).abs() / c.shift(1) * 100).dropna().iloc[-60:]
            if len(g):
                gap = round(float(g.max()), 1)
                rec["gap"] = gap
                rec["gaplvl"] = "H" if gap > 8 else "L" if gap < 4 else "M"
    return out


def _member_dart(key: str, tk: str, nm: str, corp_map: dict) -> dict:
    """DART 연결재무 기반 스프레드. 시세·PER·수급은 build()에서 일괄 merge."""
    import dart
    code6 = tk.split(".")[0]
    cc = corp_map.get(code6)
    rev = op = spread = q_spread = q_op = accel = None
    q_note = "정상"
    if cc:
        yr = date.today().year
        ann = None
        for y in (yr - 1, yr - 2):           # 최근 사업보고서
            ann = dart.annual_spread(key, cc, y)
            if ann:
                break
        if ann:
            rev, op, spread = ann["rev"], ann["op"], ann["spread"]
        # ① 정밀 4분기 롤링 TTM (누적공시 역산) — 미국판과 동일
        ttm = dart.ttm_yoy(key, cc)
        if ttm:
            q_spread, q_op = ttm["q_spread"], ttm["q_op"]
            q_note = "정상"
        else:
            # ② 폴백: 최신 분기 누적 YoY 근사치
            q = None
            for y in (yr, yr - 1):
                q = dart.quarter_spread(key, cc, y)
                if q:
                    break
            if q:
                q_spread, q_op = q["spread"], q["op"]
                q_note = "분기 근사(누적)"
            else:
                q_note = "분기 미확인"
        if spread is not None and q_spread is not None:
            accel = round(q_spread - spread, 1)
    else:
        q_note = "DART 코드 매핑 실패"

    return {
        "tk": tk, "nm": nm, "spread": spread, "q_spread": q_spread,
        "accel": accel, "op": op, "rev": rev, "q_op": q_op,
        "q_note": q_note, "d_until": None,
        "ir": {"date": datetime.today().strftime("%Y-%m"), "docs": [
            {"label": "DART 사업·분기보고서", "url": _dart_url(tk)}]},
    }


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return 0.0
    n = len(xs)
    return round(xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2, 1)


def build(mode: str) -> dict:
    """mode: 'demo'(합성) / 'yf'(yfinance) / 'dart'(DART+yfinance 하이브리드)."""
    import os
    bench = None
    dart_key = None
    corp = {}
    if mode == "dart":   # 키부터 확인 (네트워크 낭비 방지)
        dart_key = os.environ.get("DART_API_KEY")
        if not dart_key:
            raise SystemExit("환경변수 DART_API_KEY 가 필요합니다. "
                             "https://opendart.fss.or.kr 에서 무료 발급.")
    if mode != "demo":
        import yfinance as yf
        try:
            bench = yf.Ticker("^KS11").history(period="7mo")["Close"].dropna()
        except Exception:
            bench = None
    if mode == "dart":
        import dart as dartmod
        print("· DART 종목코드 매핑 다운로드 중...")
        corp = dartmod.corp_map(dart_key)
        print(f"  → {len(corp)}개 매핑 확보")

    # ── 배치 수집(비데모) — 느린 종목별 호출을 일괄 호출로 ──
    # 시세는 yf.download 1회, PER·수급·지분율은 pykrx 일괄로 받아 나중에 merge.
    # (종목별 t.info·pykrx 호출이 34종목에서도 30분 타임아웃을 넘긴 주범)
    tickers = [e[0] for e in UNIVERSE]
    price_maps: dict = {}
    per_m: dict = {}
    fnet_m: dict = {}
    inet_m: dict = {}
    fpct_map: dict = {}
    if mode != "demo":
        try:
            print("· 시세 일괄 다운로드(yfinance)…")
            price_maps = _price_maps(tickers, bench)
            ok = sum(1 for v in price_maps.values() if v.get("rs6") is not None)
            print(f"  → 시세 {ok}/{len(tickers)}종목")
        except Exception as e:
            print(f"  (시세 생략: {e})")
        try:
            import supply as _sup
            print("· PER·수급·지분율 일괄 로드(pykrx)…")
            per_m = _sup.per_map()
            fnet_m, inet_m = _sup.net_flow_maps(20)
            fpct_map = _sup.foreign_pct_map()
            print(f"  → PER {len(per_m)} · 외국인순매수 {len(fnet_m)} · "
                  f"기관순매수 {len(inet_m)} · 지분율 {len(fpct_map)}")
        except Exception as e:
            print(f"  (pykrx 생략: {e})")

    # 세부산업별 멤버 구성 — 재무(DART/yfinance)는 종목별이라 병렬로 수집.
    def _one(entry):
        tk, nm, gics, sub_ko, sub_code = entry
        if mode == "demo":
            m = _member_synth(tk, nm)
        elif mode == "dart":
            m = _member_dart(dart_key, tk, nm, corp)
        else:
            m = _member_yf(tk, nm)
        return sub_code, sub_ko, gics, m

    if mode == "demo":
        results = [_one(e) for e in UNIVERSE]          # 합성은 즉시 — 병렬 불필요
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        workers = 6 if mode == "dart" else 10          # DART 는 throttle 회피로 보수적
        results = []
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_one, e): e for e in UNIVERSE}
            for fut in as_completed(futs):
                done += 1
                entry = futs[fut]
                try:
                    results.append(fut.result())
                    print(f"  [{done}/{len(UNIVERSE)}] {entry[1]} ({entry[0]}) ✓")
                except Exception as e:  # noqa: BLE001
                    print(f"  [{done}/{len(UNIVERSE)}] {entry[1]} ({entry[0]}) 실패: {e}")

    # 배치 맵 merge — 비데모 멤버에 시세·PER·수급 채우기 (데모는 이미 보유)
    import supply as _supmod
    subs_map: dict[str, dict] = {}
    for sub_code, sub_ko, gics, m in results:
        if mode != "demo":
            tk = m["tk"]
            c6 = tk.split(".")[0]
            pm = price_maps.get(tk, {})
            m["rs3"], m["rs6"] = pm.get("rs3"), pm.get("rs6")
            m["gap"], m["gaplvl"] = pm.get("gap"), pm.get("gaplvl", "M")
            m["from_high"] = pm.get("from_high")
            m["pe"], m["fpe"], m["peg"] = per_m.get(c6), None, None
            fn, ino = fnet_m.get(c6), inet_m.get(c6)
            m["foreign_net"], m["inst_net"] = fn, ino
            m["foreign_pct"] = fpct_map.get(c6)
            m["supply"] = _supmod.supply_label(fn, ino)
        subs_map.setdefault(sub_code, {"sic": sub_code, "ko": sub_ko,
                                       "desc": sub_code, "gics": gics,
                                       "members": []})
        subs_map[sub_code]["members"].append(m)

    subs = []
    for s in subs_map.values():
        s["members"].sort(key=lambda m: (m["spread"] if m["spread"] is not None else -999),
                          reverse=True)
        s["med"] = _median([m["spread"] for m in s["members"]])
        s["n"] = len(s["members"])
        subs.append(s)
    subs.sort(key=lambda s: s["med"], reverse=True)

    # 대섹터 집계
    sec_map: dict[str, list] = {}
    for s in subs:
        sec_map.setdefault(s["gics"], [])
        sec_map[s["gics"]].extend(m["spread"] for m in s["members"])
    sectors = [{"gics": g, "med": _median(v), "n_sub": sum(1 for s in subs if s["gics"] == g),
                "n_co": len(v)} for g, v in sec_map.items()]
    sectors.sort(key=lambda x: x["med"], reverse=True)

    # 시장 배지 (코스피 기준) — 데모는 합성, 실시간은 yfinance
    if mode == "demo":
        market = {"vix": 18.5, "vix_state": "경계", "spy3": 4.2, "spy6": 7.8}
    else:
        import yfinance as yf
        def chg(sym, n):
            try:
                c = yf.Ticker(sym).history(period="7mo")["Close"].dropna()
                return round((c.iloc[-1] / c.iloc[-n] - 1) * 100, 1)
            except Exception:
                return None
        vk = None
        try:
            vk = round(float(yf.Ticker("^KS11").history(period="5d")["Close"].iloc[-1]), 0)
        except Exception:
            pass
        market = {"vix": 18.5, "vix_state": "—",
                  "spy3": chg("^KS11", 63), "spy6": chg("^KS11", 126)}

    return {"updated": date.today().isoformat(), "demo": (mode == "demo"),
            "market": market, "sectors": sectors, "subs": subs}


def main():
    ap = argparse.ArgumentParser(description="한국판 헤게모니 트리 데이터 빌더")
    ap.add_argument("--demo", action="store_true", help="오프라인 합성 데모")
    ap.add_argument("--dart", action="store_true",
                    help="DART 연결재무 + yfinance 시세 (DART_API_KEY 필요)")
    ap.add_argument("--out", default="data/tree_kr.json")
    args = ap.parse_args()
    mode = "demo" if args.demo else "dart" if args.dart else "yf"
    tree = build(mode)
    out = Path(__file__).resolve().parent / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=1)
    n = sum(len(s["members"]) for s in tree["subs"])
    label = {"demo": "데모", "dart": "DART+시세", "yf": "yfinance"}[mode]
    print(f"✅ {out} 생성 — 섹터 {len(tree['sectors'])} · 세부산업 "
          f"{len(tree['subs'])} · 종목 {n} ({label})")


if __name__ == "__main__":
    main()
