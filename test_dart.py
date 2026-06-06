"""DART 파싱·스프레드 로직 오프라인 테스트 (네트워크 불필요).

실제 DART fnlttSinglAcntAll.json 응답과 같은 형태의 mock 으로 검증한다.
"""
import dart


def _rows(rev_t, rev_p, op_t, op_p, rev_id="ifrs-full_Revenue",
          op_id="dart_OperatingIncomeLoss"):
    """연간 손익 행 mock (천원/원 단위 문자열, 콤마 포함)."""
    def fmt(v):
        return f"{v:,}"
    return [
        {"sj_div": "BS", "account_nm": "자산총계", "thstrm_amount": "999"},
        {"sj_div": "IS", "account_id": rev_id, "account_nm": "매출액",
         "thstrm_amount": fmt(rev_t), "frmtrm_amount": fmt(rev_p)},
        {"sj_div": "IS", "account_id": op_id, "account_nm": "영업이익",
         "thstrm_amount": fmt(op_t), "frmtrm_amount": fmt(op_p)},
    ]


def test_spread_basic():
    # 매출 +10%, 영업이익 +30% → 스프레드 +20p
    rows = _rows(110_000, 100_000, 26_000, 20_000)
    r = dart._spread_from_rows(rows, ["thstrm_amount"], ["frmtrm_amount"])
    assert r["rev"] == 10.0
    assert r["op"] == 30.0
    assert r["spread"] == 20.0


def test_spread_match_by_korean_name():
    # account_id 가 비표준이어도 한글명 '매출액'/'영업이익' 으로 매칭
    rows = _rows(120_000, 100_000, 22_000, 20_000,
                 rev_id="X", op_id="Y")
    r = dart._spread_from_rows(rows, ["thstrm_amount"], ["frmtrm_amount"])
    assert r["rev"] == 20.0
    assert r["op"] == 10.0
    assert r["spread"] == -10.0


def test_turnaround_op_yoy_huge():
    # 전년 영업이익 적자 → YoY 가 음수 분모로 큰 값 (스코어러가 기저효과로 처리)
    rows = _rows(105_000, 100_000, 8_000, -1_000)
    r = dart._spread_from_rows(rows, ["thstrm_amount"], ["frmtrm_amount"])
    assert r["rev"] == 5.0
    assert r["op"] is not None and r["op"] > 100   # 적자→흑자 → 큰 YoY


def test_missing_returns_none():
    rows = [{"sj_div": "BS", "account_nm": "부채총계", "thstrm_amount": "1"}]
    assert dart._spread_from_rows(rows, ["thstrm_amount"], ["frmtrm_amount"]) is None


def test_quarter_prefers_cumulative_field():
    # 분기: 누적금액(add) 우선 사용
    rows = [
        {"sj_div": "IS", "account_id": "ifrs-full_Revenue", "account_nm": "매출액",
         "thstrm_amount": "30,000", "thstrm_add_amount": "90,000",
         "frmtrm_amount": "28,000", "frmtrm_add_amount": "80,000"},
        {"sj_div": "IS", "account_id": "dart_OperatingIncomeLoss",
         "account_nm": "영업이익", "thstrm_amount": "6,000",
         "thstrm_add_amount": "18,000", "frmtrm_amount": "5,000",
         "frmtrm_add_amount": "15,000"},
    ]
    r = dart._spread_from_rows(rows, ["thstrm_add_amount", "thstrm_amount"],
                               ["frmtrm_add_amount", "frmtrm_amount"])
    # 누적 90,000/80,000 = +12.5%, 영익 18,000/15,000 = +20% → 스프레드 +7.5p
    assert r["rev"] == 12.5
    assert r["op"] == 20.0
    assert r["spread"] == 7.5


def test_num_parsing():
    assert dart._num("1,234,567") == 1234567.0
    assert dart._num(" -5,000 ") == -5000.0
    assert dart._num("") is None
    assert dart._num(None) is None


# ---------- 정밀 4분기 롤링 TTM 역산 ----------
def _cum8(rev_q, op_q, y0=2024):
    """8분기 단독값(rev_q,op_q) → 누적 dict 2종 (연속 8분기, y0 Q1부터)."""
    cum_rev, cum_op = {}, {}
    # (year,q) 순서대로 8개
    seq = [(y0, 1), (y0, 2), (y0, 3), (y0, 4),
           (y0 + 1, 1), (y0 + 1, 2), (y0 + 1, 3), (y0 + 1, 4)]
    accR = {y0: 0, y0 + 1: 0}
    accO = {y0: 0, y0 + 1: 0}
    for (y, q), r, o in zip(seq, rev_q, op_q):
        accR[y] += r; accO[y] += o
        cum_rev[(y, q)] = accR[y]   # 누적
        cum_op[(y, q)] = accO[y]
    return cum_rev, cum_op


def test_ttm_basic_yoy():
    # 직전4분기 매출합 100, 영익 20 / 최근4분기 매출 115(+15%), 영익 26(+30%)
    rev_q = [25, 25, 25, 25, 28, 29, 29, 29]   # 합 100 → 115
    op_q = [5, 5, 5, 5, 6, 6.5, 6.75, 6.75]    # 합 20 → 26
    cr, co = _cum8(rev_q, op_q)
    r = dart._ttm_from_cumulative(cr, co)
    assert r["q_rev"] == 15.0
    assert r["q_op"] == 30.0
    assert r["q_spread"] == 15.0


def test_ttm_standalone_reconstruction():
    # 누적에서 단독 역산이 맞는지: Q4 단독 = 연간 - 9M
    cum = {(2024, 1): 10, (2024, 2): 22, (2024, 3): 36, (2024, 4): 52}
    st = dict(dart._standalone(cum))
    assert st[(2024, 1)] == 10
    assert st[(2024, 2)] == 12     # 22-10
    assert st[(2024, 3)] == 14     # 36-22
    assert st[(2024, 4)] == 16     # 52-36


def test_ttm_insufficient_quarters():
    cum = {(2024, 1): 10, (2024, 2): 20}   # 4분기 미만
    assert dart._ttm_from_cumulative(cum, cum) is None


def test_ttm_non_contiguous_rejected():
    # 8개지만 연속이 아니면(중간 빠짐) None
    cr, co = _cum8([25]*8, [5]*8)
    del cr[(2024, 3)]; del co[(2024, 3)]   # 한 분기 누락 → 단독 복원 불가/불연속
    assert dart._ttm_from_cumulative(cr, co) is None
