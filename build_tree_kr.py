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
UNIVERSE = [
    ("005930.KS", "삼성전자", "IT·반도체", "반도체", "SEMI"),
    ("000660.KS", "SK하이닉스", "IT·반도체", "반도체", "SEMI"),
    ("000990.KS", "DB하이텍", "IT·반도체", "반도체", "SEMI"),
    ("058470.KQ", "리노공업", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("240810.KQ", "원익IPS", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("357780.KQ", "솔브레인", "IT·반도체", "반도체 장비·소재", "SEMIEQ"),
    ("009150.KS", "삼성전기", "IT·반도체", "전자부품", "ELEC"),
    ("066570.KS", "LG전자", "IT·반도체", "전자부품", "ELEC"),
    ("373220.KS", "LG에너지솔루션", "2차전지·소재", "2차전지", "BATT"),
    ("006400.KS", "삼성SDI", "2차전지·소재", "2차전지", "BATT"),
    ("051910.KS", "LG화학", "2차전지·소재", "2차전지", "BATT"),
    ("247540.KQ", "에코프로비엠", "2차전지·소재", "2차전지 소재", "BATTMAT"),
    ("086520.KQ", "에코프로", "2차전지·소재", "2차전지 소재", "BATTMAT"),
    ("003670.KS", "포스코퓨처엠", "2차전지·소재", "2차전지 소재", "BATTMAT"),
    ("207940.KS", "삼성바이오로직스", "바이오·헬스케어", "바이오", "BIO"),
    ("068270.KS", "셀트리온", "바이오·헬스케어", "바이오", "BIO"),
    ("196170.KQ", "알테오젠", "바이오·헬스케어", "바이오", "BIO"),
    ("028300.KQ", "HLB", "바이오·헬스케어", "바이오", "BIO"),
    ("005380.KS", "현대차", "자동차", "완성차", "AUTO"),
    ("000270.KS", "기아", "자동차", "완성차", "AUTO"),
    ("012330.KS", "현대모비스", "자동차", "자동차 부품", "AUTOPART"),
    ("105560.KS", "KB금융", "금융", "은행·지주", "BANK"),
    ("055550.KS", "신한지주", "금융", "은행·지주", "BANK"),
    ("086790.KS", "하나금융지주", "금융", "은행·지주", "BANK"),
    ("035420.KS", "NAVER", "인터넷·게임", "인터넷 플랫폼", "NET"),
    ("035720.KS", "카카오", "인터넷·게임", "인터넷 플랫폼", "NET"),
    ("259960.KS", "크래프톤", "인터넷·게임", "게임", "GAME"),
    ("036570.KS", "엔씨소프트", "인터넷·게임", "게임", "GAME"),
    ("005490.KS", "POSCO홀딩스", "소재·산업재", "철강·비철", "STEEL"),
    ("010130.KS", "고려아연", "소재·산업재", "철강·비철", "STEEL"),
    ("090430.KS", "아모레퍼시픽", "소비재", "화장품·음식료", "CONS"),
    ("097950.KS", "CJ제일제당", "소비재", "화장품·음식료", "CONS"),
    ("017670.KS", "SK텔레콤", "통신·유틸리티", "통신", "TELCO"),
    ("015760.KS", "한국전력", "통신·유틸리티", "유틸리티", "UTIL"),
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


def _member_yf(tk: str, nm: str, bench) -> dict:
    """실시간(yfinance) 헤게모니 지표. (인터넷 필요)"""
    import numpy as np
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

    # 시세 RS (KOSPI 대비) + gap + 52주 고점比
    rs3 = rs6 = gap = from_high = None
    gaplvl = "M"
    try:
        h = t.history(period="1y", auto_adjust=True)
        c = h["Close"].dropna()
        if len(c) > 130 and bench is not None and len(bench) > 130:
            def ret(s, n):
                return (s.iloc[-1] / s.iloc[-n] - 1) * 100
            rs3 = round(ret(c, 63) - ret(bench, 63), 1)
            rs6 = round(ret(c, 126) - ret(bench, 126), 1)
        if len(c):
            hi = float(c.iloc[-252:].max())
            from_high = round((float(c.iloc[-1]) / hi - 1) * 100, 1) if hi else None
        # gap: 최근 60일 전일종가 대비 시가 최대 괴리
        o, pc = h["Open"], h["Close"].shift(1)
        g = ((o - pc).abs() / pc * 100).dropna().iloc[-60:]
        if len(g):
            gap = round(float(g.max()), 1)
            gaplvl = "H" if gap > 8 else "L" if gap < 4 else "M"
    except Exception:
        pass

    info = {}
    try:
        info = t.info or {}
    except Exception:
        pass
    return {
        "tk": tk, "nm": nm, "spread": spread, "q_spread": q_spread,
        "accel": accel, "rs3": rs3, "rs6": rs6, "gap": gap, "gaplvl": gaplvl,
        "from_high": from_high,
        "op": op, "rev": rev, "q_op": t_op, "pe": info.get("trailingPE"),
        "fpe": info.get("forwardPE"), "peg": info.get("trailingPegRatio"),
        "q_note": "정상", "d_until": None,
        "ir": {"date": datetime.today().strftime("%Y-%m"), "docs": [
            {"label": "DART 사업·분기보고서", "url": _dart_url(tk)}]},
    }


def _price_info_yf(tk: str, bench) -> dict:
    """yfinance 로 시세 RS/갭/52주고점比 + PER 을 가져온다 (DART 모드의 가격축)."""
    import yfinance as yf
    rs3 = rs6 = gap = from_high = pe = fpe = peg = None
    gaplvl = "M"
    t = yf.Ticker(tk)
    try:
        h = t.history(period="1y", auto_adjust=True)   # 52주 고점用
        c = h["Close"].dropna()
        if len(c) > 130 and bench is not None and len(bench) > 130:
            def ret(s, n):
                return (s.iloc[-1] / s.iloc[-n] - 1) * 100
            rs3 = round(ret(c, 63) - ret(bench, 63), 1)
            rs6 = round(ret(c, 126) - ret(bench, 126), 1)
        if len(c):
            hi = float(c.iloc[-252:].max())
            from_high = round((float(c.iloc[-1]) / hi - 1) * 100, 1) if hi else None
        o, pc = h["Open"], h["Close"].shift(1)
        g = ((o - pc).abs() / pc * 100).dropna().iloc[-60:]
        if len(g):
            gap = round(float(g.max()), 1)
            gaplvl = "H" if gap > 8 else "L" if gap < 4 else "M"
    except Exception:
        pass
    try:
        info = t.info or {}
        pe, fpe, peg = (info.get("trailingPE"), info.get("forwardPE"),
                        info.get("trailingPegRatio"))
    except Exception:
        pass
    return {"rs3": rs3, "rs6": rs6, "gap": gap, "gaplvl": gaplvl,
            "from_high": from_high, "pe": pe, "fpe": fpe, "peg": peg}


def _member_dart(key: str, tk: str, nm: str, corp_map: dict, bench) -> dict:
    """DART 연결재무(스프레드) + yfinance(시세·PER) 하이브리드."""
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

    pinfo = _price_info_yf(tk, bench)
    return {
        "tk": tk, "nm": nm, "spread": spread, "q_spread": q_spread,
        "accel": accel, "rs3": pinfo["rs3"], "rs6": pinfo["rs6"],
        "from_high": pinfo["from_high"],
        "gap": pinfo["gap"], "gaplvl": pinfo["gaplvl"],
        "op": op, "rev": rev, "q_op": q_op, "pe": pinfo["pe"],
        "fpe": pinfo["fpe"], "peg": pinfo["peg"],
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

    # 수급(pykrx) — 외국인 지분율 맵 1회 로드 (설치/네트워크 실패 시 생략)
    sup = None
    fpct_map = {}
    if mode != "demo":
        try:
            import supply as sup
            print("· 외국인 지분율 맵 로드 중(pykrx)...")
            fpct_map = sup.foreign_pct_map()
            print(f"  → {len(fpct_map)}종목")
        except Exception as e:
            print(f"  (수급 생략: {e})")
            sup = None

    # 세부산업별 멤버 구성
    subs_map: dict[str, dict] = {}
    for i, (tk, nm, gics, sub_ko, sub_code) in enumerate(UNIVERSE, 1):
        if mode == "demo":
            m = _member_synth(tk, nm)
        elif mode == "dart":
            print(f"  [{i}/{len(UNIVERSE)}] {nm} ({tk}) DART…")
            m = _member_dart(dart_key, tk, nm, corp, bench)
        else:
            m = _member_yf(tk, nm, bench)
        # 수급 보강 (외국인·기관 순매수 + 외국인 지분율)
        if sup is not None:
            try:
                m.update(sup.supply_member(tk.split(".")[0], 20, fpct_map))
            except Exception:
                pass
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
