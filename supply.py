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
def foreign_pct_map(date_str: str | None = None) -> dict[str, float]:
    """외국인 지분율 맵 {종목코드6: 지분율%} (1회 호출)."""
    from pykrx import stock
    from datetime import date
    d = date_str or date.today().strftime("%Y%m%d")
    out = {}
    for mkt in ("KOSPI", "KOSDAQ"):
        try:
            df = stock.get_exhaustion_rates_of_foreign_investment(d, mkt)
            col = "지분율" if "지분율" in df.columns else None
            if col:
                for code, row in df.iterrows():
                    try:
                        out[str(code)] = float(row[col])
                    except (TypeError, ValueError):
                        pass
        except Exception:
            continue
    return out


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
