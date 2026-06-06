"""수급 집계·라벨 로직 오프라인 테스트 (pykrx 네트워크 불필요)."""
import pandas as pd
import supply


def _df(rows):
    """투자자별 순매수 mock (index=투자자, columns=[매도,매수,순매수])."""
    idx, net = zip(*rows)
    return pd.DataFrame({"매도": [0]*len(rows), "매수": [0]*len(rows),
                         "순매수": list(net)}, index=list(idx))


def test_agg_foreign_and_inst():
    df = _df([("개인", -500), ("외국인", 300), ("기타외국인", 50),
              ("기관합계", 150), ("전체", 0)])
    f, i = supply._agg_net(df)
    assert f == 350    # 외국인 300 + 기타외국인 50
    assert i == 150


def test_agg_missing_rows():
    df = _df([("개인", 100), ("전체", 100)])
    f, i = supply._agg_net(df)
    assert f is None and i is None


def test_label_dual_accumulation():
    assert "쌍끌이" in supply.supply_label(300, 150)


def test_label_foreign_only():
    assert supply.supply_label(300, -50) == "🟢 외국인 매집"


def test_label_inst_only():
    assert "기관 매집" in supply.supply_label(-200, 100)


def test_label_dual_sell():
    assert "이탈" in supply.supply_label(-300, -100)


def test_label_unknown():
    assert "미확인" in supply.supply_label(None, None)


def test_eok_conversion():
    assert supply._eok(35_000_000_000) == 350.0   # 350억
    assert supply._eok(None) is None
