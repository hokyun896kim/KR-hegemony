"""DART(전자공시) OpenAPI 백엔드 — 한국 연결재무제표로 헤게모니 스프레드 계산.

yfinance의 한국 재무 커버리지 한계를 보완한다. DART 연결손익계산서에서
매출액·영업이익을 직접 받아 YoY 스프레드를 산출하므로 훨씬 정확하다.

필요: 무료 DART API 키 (https://opendart.fss.or.kr → 인증키 신청).
      환경변수 DART_API_KEY 로 전달.

핵심 함수
- corp_map(key): 종목코드(6자리) → DART 고유번호(corp_code) 매핑
- annual_spread(key, corp_code, year): 연간 매출/영업이익 YoY + 스프레드
- quarter_spread(key, corp_code, year): 최근 분기 누적 YoY (있을 때)

네트워크가 필요하므로 이 모듈은 사용자 PC/Actions에서 실행한다.
순수 파싱 로직(_spread_from_rows, _pick)은 오프라인 단위테스트로 검증된다.
"""
from __future__ import annotations

import io
import json
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import date

BASE = "https://opendart.fss.or.kr/api"

# 손익계산서 계정 식별 (account_id 우선, 없으면 한글명 키워드)
REV_IDS = {"ifrs-full_Revenue", "ifrs_Revenue", "dart_OperatingRevenue"}
REV_NM = ("매출액", "수익(매출액)", "영업수익", "매출")
OP_IDS = {"dart_OperatingIncomeLoss", "ifrs-full_OperatingIncomeLoss",
          "ifrs-full_ProfitLossFromOperatingActivities"}
OP_NM = ("영업이익", "영업이익(손실)")

# 기본주당이익(EPS) — PER = 종가 ÷ EPS 계산용 (별도 호출 없이 같은 손익 응답에서 추출)
EPS_IDS = {"ifrs-full_BasicEarningsLossPerShare", "ifrs_BasicEarningsPerShare",
           "dart_BasicEarningsLossPerShareKRW"}
EPS_NM = ("기본주당이익", "기본주당순이익", "기본및희석주당이익", "주당이익")

REPRT_ANNUAL = "11011"          # 사업보고서(연간)
# 분기 보고서 (최신 우선 시도)
REPRT_QUARTERS = ["11014", "11012", "11013"]  # 3분기 · 반기 · 1분기


def _get(url: str, timeout: int = 20, retries: int = 2) -> bytes:
    """일시적 네트워크/throttle 실패를 가벼운 backoff 로 재시도.

    재시도/대기를 짧게(2회·0.6s) 둬서 opendart throttle 시 sleep 누적으로
    전체 빌드가 길어지는 것을 막는다. 마지막 시도엔 sleep 없음.
    """
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hegemony-kr"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries - 1:
                time.sleep(0.6)
    raise last


def _num(s) -> float | None:
    if s is None:
        return None
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _pick(rows: list[dict], ids: set[str], nms: tuple, fields: list[str]):
    """IS/CIS 행에서 계정을 찾아 fields(우선순위) 중 첫 유효 숫자를 반환."""
    def grab(r):
        for fld in fields:
            v = _num(r.get(fld))
            if v is not None:
                return v
        return None
    # 1) account_id 정확 매칭
    for r in rows:
        if r.get("sj_div") in ("IS", "CIS") and r.get("account_id") in ids:
            v = grab(r)
            if v is not None:
                return v
    # 2) 한글 계정명 키워드 매칭
    for r in rows:
        if r.get("sj_div") not in ("IS", "CIS"):
            continue
        nm = (r.get("account_nm") or "").replace(" ", "")
        if any(k.replace(" ", "") in nm for k in nms):
            v = grab(r)
            if v is not None:
                return v
    return None


def _yoy(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return (cur / abs(prev) - 1) * 100 if prev > 0 else (cur - prev) / abs(prev) * 100


def _spread_from_rows(rows: list[dict], cur_fields: list[str],
                      prev_fields: list[str]) -> dict | None:
    """손익 행 리스트에서 매출/영업이익 YoY + 스프레드를 계산 (순수 함수, 테스트용)."""
    rev_c = _pick(rows, REV_IDS, REV_NM, cur_fields)
    rev_p = _pick(rows, REV_IDS, REV_NM, prev_fields)
    op_c = _pick(rows, OP_IDS, OP_NM, cur_fields)
    op_p = _pick(rows, OP_IDS, OP_NM, prev_fields)
    rev_yoy, op_yoy = _yoy(rev_c, rev_p), _yoy(op_c, op_p)
    if rev_yoy is None or op_yoy is None:
        return None
    return {"rev": round(rev_yoy, 1), "op": round(op_yoy, 1),
            "spread": round(op_yoy - rev_yoy, 1)}


# ----------------------------- 네트워크 호출 -----------------------------
def corp_map(key: str) -> dict[str, str]:
    """종목코드(6자리) → corp_code(8자리) 매핑 다운로드."""
    raw = _get(f"{BASE}/corpCode.xml?crtfc_key={key}")
    zf = zipfile.ZipFile(io.BytesIO(raw))
    root = ET.fromstring(zf.read(zf.namelist()[0]))
    out = {}
    for el in root.iter("list"):
        sc = (el.findtext("stock_code") or "").strip()
        cc = (el.findtext("corp_code") or "").strip()
        if sc and len(sc) == 6 and cc:
            out[sc] = cc
    return out


def _statement(key: str, corp_code: str, year: int, reprt: str,
               fs: str) -> list[dict] | None:
    url = (f"{BASE}/fnlttSinglAcntAll.json?crtfc_key={key}"
           f"&corp_code={corp_code}&bsns_year={year}&reprt_code={reprt}"
           f"&fs_div={fs}")
    try:
        d = json.loads(_get(url))
    except Exception:
        return None
    if d.get("status") != "000":
        return None
    return d.get("list", [])


def annual_spread(key: str, corp_code: str, year: int) -> dict | None:
    """연간 사업보고서로 매출/영업이익 YoY + 스프레드.

    한 번의 호출에 당기(thstrm)·전기(frmtrm)가 함께 와서 YoY 가 바로 나온다.
    연결(CFS) 우선, 없으면 별도(OFS).
    """
    for fs in ("CFS", "OFS"):
        rows = _statement(key, corp_code, year, REPRT_ANNUAL, fs)
        if not rows:
            continue
        res = _spread_from_rows(rows, ["thstrm_amount"], ["frmtrm_amount"])
        if res:
            res["eps"] = _pick(rows, EPS_IDS, EPS_NM, ["thstrm_amount"])  # 당기 EPS
            res["fs"] = fs
            return res
    return None


# ----------------------------- 정밀 4분기 롤링 TTM -----------------------------
# DART 누적공시 → 분기 단독 역산 → 최근 4분기 합 vs 직전 4분기 합 YoY (미국판과 동일 개념)
# 보고서코드 → 분기 인덱스: 1분기(11013)=Q1누적, 반기(11012)=H1누적,
#                          3분기(11014)=9M누적, 사업보고서(11011)=연간누적
_REPRT_BY_Q = {1: "11013", 2: "11012", 3: "11014", 4: "11011"}

_CUM_FIELDS = ["thstrm_add_amount", "thstrm_amount"]   # 누적금액 우선


def _standalone(cum: dict) -> list:
    """누적값 dict{(year,q):값} → 분기 단독 [((year,q), 단독값)] 시간순.

    Q1=Q1누적, Qn(n>1)=Qn누적 − Q(n-1)누적. 직전 분기 누적이 없으면 건너뜀.
    """
    out = []
    for (y, q) in sorted(cum):
        if q == 1:
            out.append(((y, q), cum[(y, q)]))
        else:
            prev = cum.get((y, q - 1))
            if prev is not None:
                out.append(((y, q), cum[(y, q)] - prev))
    return out


def _qidx(yq):
    y, q = yq
    return y * 4 + (q - 1)


def _ttm_from_cumulative(cum_rev: dict, cum_op: dict) -> dict | None:
    """누적 매출/영업이익 → 정밀 TTM(최근4분기 vs 직전4분기) YoY + 스프레드.

    순수 함수(네트워크 없음) — 오프라인 테스트로 검증.
    """
    sr = dict(_standalone(cum_rev))
    so = dict(_standalone(cum_op))
    common = sorted((k for k in sr if k in so), key=_qidx)
    if len(common) < 8:
        return None
    last8 = common[-8:]
    if _qidx(last8[-1]) - _qidx(last8[0]) != 7:    # 8분기가 연속이어야
        return None
    cur, prev = last8[-4:], last8[:4]
    rev_now, rev_prev = sum(sr[k] for k in cur), sum(sr[k] for k in prev)
    op_now, op_prev = sum(so[k] for k in cur), sum(so[k] for k in prev)
    rev_yoy, op_yoy = _yoy(rev_now, rev_prev), _yoy(op_now, op_prev)
    if rev_yoy is None or op_yoy is None:
        return None
    return {"q_rev": round(rev_yoy, 1), "q_op": round(op_yoy, 1),
            "q_spread": round(op_yoy - rev_yoy, 1)}


def _cum(key: str, corp_code: str, year: int, reprt: str,
         fs_order: tuple = ("CFS", "OFS")):
    """(year, reprt) 의 누적 매출·영업이익 → (rev, op) 또는 None.

    fs_order 로 시도할 재무유형을 제한할 수 있다(연간에서 확인된 CFS/OFS 하나만
    쓰면 분기 호출 수가 절반 — opendart throttle 완화).
    """
    for fs in fs_order:
        rows = _statement(key, corp_code, year, reprt, fs)
        if not rows:
            continue
        rev = _pick(rows, REV_IDS, REV_NM, _CUM_FIELDS)
        op = _pick(rows, OP_IDS, OP_NM, _CUM_FIELDS)
        if rev is not None and op is not None:
            return rev, op
    return None


def ttm_yoy(key: str, corp_code: str, this_year: int | None = None,
            prefer_fs: str | None = None) -> dict | None:
    """DART 에서 최근 3개 사업연도의 누적공시를 모아 정밀 TTM 스프레드 계산.

    미래/미공시 분기는 자동으로 건너뛴다. 8분기 연속 확보 시에만 산출.
    prefer_fs("CFS"/"OFS") 가 주어지면 그 재무유형만 조회(호출 수 절반).
    """
    fs_order = (prefer_fs,) if prefer_fs in ("CFS", "OFS") else ("CFS", "OFS")
    today = date.today()
    yr = this_year or today.year
    cum_rev, cum_op = {}, {}
    for y in (yr, yr - 1, yr - 2):
        for q, reprt in _REPRT_BY_Q.items():
            # 아직 공시될 수 없는 미래 분기는 건너뜀(분기말+~45일 공시 마감 전).
            # 분기 q 의 마감월 ≈ 3q, 공시는 그 ~45일 뒤 → 보수적으로 분기말이
            # 지나지 않았으면 호출 생략(불필요한 네트워크 라운드트립 제거).
            if y > today.year or (y == today.year and 3 * q > today.month):
                continue
            cv = _cum(key, corp_code, y, reprt, fs_order)
            if cv:
                cum_rev[(y, q)], cum_op[(y, q)] = cv
    return _ttm_from_cumulative(cum_rev, cum_op)


def quarter_spread(key: str, corp_code: str, year: int) -> dict | None:
    """최신 분기 보고서의 누적 YoY (있을 때). q_op 베이스로 사용.

    누적금액(thstrm_add_amount) 우선, 없으면 당기금액(thstrm_amount).
    완전한 TTM 은 아니며 '최근 분기누적' 흐름의 근사치다.
    """
    for reprt in REPRT_QUARTERS:
        for fs in ("CFS", "OFS"):
            rows = _statement(key, corp_code, year, reprt, fs)
            if not rows:
                continue
            res = _spread_from_rows(
                rows, ["thstrm_add_amount", "thstrm_amount"],
                ["frmtrm_add_amount", "frmtrm_amount"])
            if res:
                res["fs"] = fs
                res["reprt"] = reprt
                return res
    return None
