"""한국 수급(투자자별 매매) 백엔드 — pykrx 기반.

한국 시장의 핵심은 '누가 사는가'다. 최근 N거래일 외국인·기관 순매수와
외국인 지분율을 받아 tree.json 에 미리 넣어, AI 웹검색 없이도 도구가
'쌍끌이 매집 / 외국인 이탈' 같은 수급 신호를 즉시 보여주게 한다.

필요: pip install pykrx   (KRX 데이터 스크래핑, API 키 불필요)
네트워크가 필요하므로 사용자 PC/Actions 에서 실행한다.
집계 로직(_agg_net, supply_label)은 오프라인 단위테스트로 검증된다.
"""
from __future__ import annotations

# 외국인 = '외국인' + '기타외국인'(있으면). 기관 = '기관합계'.
_FOREIGN_ROWS = ("외국인", "기타외국인")
_INST_ROWS = ("기관합계",)


def _row_net(df, names) -> float | None:
    """투자자별 순매수 DataFrame 에서 지정 행들의 순매수 합(원)."""
    if df is None:
        return None
    col = "순매수" if ("순매수" in getattr(df, "columns", [])) else None
    if col is None:
        return None
    total = 0.0
    found = False
    for nm in names:
        if nm in df.index:
            try:
                total += float(df.loc[nm, col])
                found = True
            except (TypeError, ValueError):
                pass
    return total if found else None


def _agg_net(df) -> tuple:
    """(외국인 순매수, 기관 순매수) 원 단위. 순수 함수(테스트용)."""
    return _row_net(df, _FOREIGN_ROWS), _row_net(df, _INST_ROWS)


def supply_label(foreign_net, inst_net) -> str:
    """외국인·기관 순매수 부호로 수급 신호 라벨."""
    f = foreign_net or 0
    i = inst_net or 0
    if foreign_net is None and inst_net is None:
        return "— 수급 미확인"
    if f > 0 and i > 0:
        return "🟢 쌍끌이 매집(외국인+기관)"
    if f > 0 and i <= 0:
        return "🟢 외국인 매집"
    if f <= 0 and i > 0:
        return "🟡 기관 매집(외국인 매도)"
    if f < 0 and i < 0:
        return "🔴 동반 순매도(이탈)"
    return "⚪ 중립"


def _eok(won) -> float | None:
    """원 → 억원 반올림."""
    return round(won / 1e8, 1) if won is not None else None


# ----------------------------- 네트워크(pykrx) -----------------------------
def _candidate_dates(date_str: str | None = None, span: int = 10):
    """기준일부터 하루씩 거슬러 올라가는 날짜 문자열(YYYYMMDD) 생성기.

    워크플로가 매주 토요일(+공휴일)에 도는데 pykrx 스냅샷은 휴장일에 비어 있다.
    실제 데이터가 나올 때까지 최근 거래일로 후퇴하기 위함.
    """
    from datetime import date, datetime, timedelta
    base = (datetime.strptime(date_str, "%Y%m%d").date()
            if date_str else date.today())
    for back in range(span):
        yield (base - timedelta(days=back)).strftime("%Y%m%d")


def foreign_pct_map(date_str: str | None = None) -> dict[str, float]:
    """외국인 지분율 맵 {종목코드6: 지분율%}. 휴장일이면 직전 거래일로 후퇴."""
    from pykrx import stock
    for d in _candidate_dates(date_str):
        out = {}
        for mkt in ("KOSPI", "KOSDAQ"):
            try:
                df = stock.get_exhaustion_rates_of_foreign_investment(d, mkt)
                col = "지분율" if "지분율" in df.columns else None
                if col:
                    for code, row in df.iterrows():
                        try:
                            out[str(code).zfill(6)] = float(row[col])
                        except (TypeError, ValueError):
                            pass
            except Exception:
                continue
        if out:
            return out
    return {}


def _per_from_df(df) -> dict:
    """pykrx 펀더멘털 스냅샷(index=종목코드) → {코드6: PER}. 순수 함수(테스트용).

    PER ≤ 0(적자·결측)은 제외 → 스코어러가 결측으로 처리하게 둔다.
    """
    if df is None or "PER" not in getattr(df, "columns", []):
        return {}
    out = {}
    for code, row in df.iterrows():
        try:
            v = float(row["PER"])
        except (TypeError, ValueError):
            continue
        if v and v > 0:
            out[str(code).zfill(6)] = round(v, 1)
    return out


def _netmap_from_df(df) -> dict:
    """투자자 순매수 일괄 DataFrame(index=종목코드) → {코드6: 억원}. 순수 함수.

    '순매수거래대금' 우선, 없으면 '순매수' 포함 컬럼을 자동 선택.
    """
    if df is None:
        return {}
    cols = list(getattr(df, "columns", []))
    col = None
    for c in cols:
        if "순매수" in str(c) and "대금" in str(c):
            col = c
            break
    if col is None:
        for c in cols:
            if "순매수" in str(c):
                col = c
                break
    if col is None:
        return {}
    out = {}
    for code, row in df.iterrows():
        try:
            out[str(code).zfill(6)] = round(float(row[col]) / 1e8, 1)
        except (TypeError, ValueError):
            pass
    return out


def per_map(date_str: str | None = None) -> dict[str, float]:
    """PER 맵 {종목코드6: PER} — pykrx 펀더멘털 일괄. 휴장일이면 직전 거래일로 후퇴."""
    from pykrx import stock
    for d in _candidate_dates(date_str):
        out = {}
        for mkt in ("KOSPI", "KOSDAQ"):
            df = None
            try:
                df = stock.get_market_fundamental_by_ticker(d, market=mkt)
            except Exception:
                try:
                    df = stock.get_market_fundamental(d, market=mkt)
                except Exception:
                    df = None
            out.update(_per_from_df(df))
        if out:
            return out
    return {}


def net_flow_maps(days: int = 20) -> tuple[dict, dict]:
    """({코드6: 외국인순매수억}, {코드6: 기관순매수억}) — pykrx 일괄.

    종목별 호출 대신 투자자별 전체 순매수를 시장×투자자 4회로 받는다.
    함수가 없거나 실패하면 빈 맵 반환(호출측에서 None 처리).
    """
    from pykrx import stock
    from datetime import datetime, timedelta
    fn = getattr(stock, "get_market_net_purchases_of_equities", None)
    if fn is None:
        return {}, {}
    # 종료일을 직전 거래일로 후퇴(토요일·공휴일 실행 대비)
    for to in _candidate_dates(span=10):
        fr = (datetime.strptime(to, "%Y%m%d").date()
              - timedelta(days=days * 2)).strftime("%Y%m%d")
        fmap, imap = {}, {}
        for mkt in ("KOSPI", "KOSDAQ"):
            for inv, target in (("외국인", fmap), ("기관합계", imap)):
                try:
                    target.update(_netmap_from_df(fn(fr, to, mkt, inv)))
                except Exception:
                    pass
        if fmap or imap:
            return fmap, imap
    return {}, {}


def net_flows(code6: str, days: int = 20) -> tuple:
    """최근 days 거래일 외국인·기관 순매수(원). pykrx."""
    from pykrx import stock
    from datetime import date, timedelta
    to = date.today().strftime("%Y%m%d")
    fr = (date.today() - timedelta(days=days * 2)).strftime("%Y%m%d")
    try:
        df = stock.get_market_trading_value_by_investor(fr, to, code6)
        return _agg_net(df)
    except Exception:
        return None, None


def supply_member(code6: str, days: int = 20,
                  fpct: dict | None = None) -> dict:
    """한 종목의 수급 필드 {foreign_net, inst_net, foreign_pct, supply}."""
    f, i = net_flows(code6, days)
    return {
        "foreign_net": _eok(f),
        "inst_net": _eok(i),
        "foreign_pct": (fpct or {}).get(code6),
        "supply": supply_label(f, i),
    }
