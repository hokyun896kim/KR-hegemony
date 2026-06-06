"""네이버 금융 백엔드 — KRX(pykrx)가 해외(Actions) IP에서 막힐 때의 클라우드 폴백.

KRX 데이터 사이트는 해외 클라우드 IP에 빈 응답을 주지만, 네이버 모바일 API
(api.stock.naver.com)는 상대적으로 접근이 열려 있다. 여기서
  - PER            ← /integration (totalInfos)
  - 외국인 지분율   ← /trend 또는 /integration
  - 외국인·기관 순매수(최근 N영업일) ← /trend (dealTrendInfos)
를 받아 pykrx 공란을 메운다.

best-effort: 네이버가 막히거나 JSON 형식이 바뀌면 해당 값만 None 으로
우아하게 폴백한다(핵심 DART 재무엔 영향 없음). 파싱 로직(_per_from_integration,
_flows_from_trend 등)은 네트워크 없이 오프라인 단위테스트로 검증한다.
"""
from __future__ import annotations

import json
import urllib.request

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                   "Mobile/15E148 Safari/604.1"),
    "Referer": "https://m.stock.naver.com/",
    "Accept": "application/json",
}
_BASE = "https://api.stock.naver.com/stock"


def _get(url: str, timeout: int = 15, retries: int = 2) -> bytes:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def _num(s) -> float | None:
    """'12.34', '1,234', '5.6%', '3.2배' → float. 실패 시 None."""
    if s is None:
        return None
    t = (str(s).replace(",", "").replace("%", "").replace("배", "")
         .replace("주", "").strip())
    if t in ("", "-", "N/A"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


# ----------------------------- 순수 파서(테스트) -----------------------------
def _per_from_integration(obj) -> float | None:
    """integration JSON → PER. totalInfos 에서 code/key 가 PER 인 항목의 value."""
    if not isinstance(obj, dict):
        return None
    for it in (obj.get("totalInfos") or []):
        if not isinstance(it, dict):
            continue
        k = str(it.get("code") or it.get("key") or "").upper()
        if k == "PER":
            v = _num(it.get("value"))
            if v is not None and v > 0:   # 적자(음수/0)는 결측 처리
                return round(v, 1)
    return None


def _foreign_pct_from_integration(obj) -> float | None:
    """integration JSON → 외국인 보유/소진율(%)."""
    if not isinstance(obj, dict):
        return None
    for it in (obj.get("totalInfos") or []):
        if not isinstance(it, dict):
            continue
        k = str(it.get("code") or it.get("key") or "")
        kl = k.upper()
        if "외국인" in k or "FOREIGN" in kl or "FRGN" in kl:
            v = _num(it.get("value"))
            if v is not None:
                return round(v, 2)
    return None


def _pick_key(d: dict, *needles) -> str | None:
    """dict 키 중 모든 needle(소문자)을 포함하는 첫 키."""
    for key in d:
        kl = str(key).lower()
        if all(n in kl for n in needles):
            return key
    return None


def _flows_from_trend(obj, days: int = 20) -> tuple:
    """trend JSON → (외국인 순매수합(주), 기관 순매수합(주), 외국인 지분율%).

    레코드 키는 카멜케이스(예: foreignerPureBuyQuant, organPureBuyQuant,
    foreignerHoldRatio)라 needle 매칭으로 방어적으로 찾는다.
    """
    recs = None
    if isinstance(obj, dict):
        for key in ("dealTrendInfos", "trendInfos", "result", "dealTrends"):
            if isinstance(obj.get(key), list):
                recs = obj[key]
                break
    elif isinstance(obj, list):
        recs = obj
    if not recs:
        return None, None, None

    fkey = ikey = rkey = None
    for r in recs:
        if isinstance(r, dict):
            fkey = (_pick_key(r, "foreigner", "buy")
                    or _pick_key(r, "foreign", "buy"))
            ikey = _pick_key(r, "organ", "buy") or _pick_key(r, "inst", "buy")
            rkey = (_pick_key(r, "foreigner", "hold")
                    or _pick_key(r, "foreigner", "ratio")
                    or _pick_key(r, "foreign", "ratio"))
            break

    fsum = isum = None
    found_f = found_i = False
    for r in recs[:days]:
        if not isinstance(r, dict):
            continue
        if fkey:
            v = _num(r.get(fkey))
            if v is not None:
                fsum = (fsum or 0) + v
                found_f = True
        if ikey:
            v = _num(r.get(ikey))
            if v is not None:
                isum = (isum or 0) + v
                found_i = True

    hold = None
    if rkey:
        for r in recs:                       # 최신 보유율
            if isinstance(r, dict):
                hv = _num(r.get(rkey))
                if hv is not None:
                    hold = round(hv, 2)
                    break
    return (fsum if found_f else None,
            isum if found_i else None,
            hold)


# ----------------------------- 네트워크 -----------------------------
def enrich(code6: str, days: int = 20, close: float | None = None) -> dict:
    """한 종목의 {per, foreign_pct, foreign_net, inst_net} 를 네이버에서.

    순매수는 네이버가 '주(quant)'로 주므로 close 가 있으면 억원으로 환산
    (없으면 부호만 의미 있는 주수 그대로 — supply_label 은 부호만 사용).
    """
    per = foreign_pct = foreign_net = inst_net = None

    # ① PER · (지분율 보조) ← integration
    try:
        obj = json.loads(_get(f"{_BASE}/{code6}/integration"))
        per = _per_from_integration(obj)
        foreign_pct = _foreign_pct_from_integration(obj)
    except Exception:
        pass

    # ② 외국인·기관 순매수 · 지분율 ← trend
    try:
        obj = json.loads(_get(f"{_BASE}/{code6}/trend"))
        f_sh, i_sh, hold = _flows_from_trend(obj, days)
        if hold is not None:
            foreign_pct = hold
        # 주 → 억원 (close 있을 때). 없으면 주수 그대로(부호 보존).
        scale = (close / 1e8) if close else 1.0
        foreign_net = round(f_sh * scale, 1) if f_sh is not None else None
        inst_net = round(i_sh * scale, 1) if i_sh is not None else None
    except Exception:
        pass

    return {"per": per, "foreign_pct": foreign_pct,
            "foreign_net": foreign_net, "inst_net": inst_net}
