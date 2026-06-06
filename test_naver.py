"""네이버 금융 파서 오프라인 테스트 (네트워크 불필요)."""
import naver


def test_per_from_integration():
    obj = {"totalInfos": [
        {"code": "PER", "value": "12.34배"},
        {"code": "PBR", "value": "1.2배"},
    ]}
    assert naver._per_from_integration(obj) == 12.3


def test_per_negative_is_none():
    obj = {"totalInfos": [{"code": "PER", "value": "-5.0"}]}
    assert naver._per_from_integration(obj) is None


def test_per_missing_is_none():
    assert naver._per_from_integration({"totalInfos": []}) is None
    assert naver._per_from_integration({}) is None
    assert naver._per_from_integration(None) is None


def test_foreign_pct_from_integration():
    obj = {"totalInfos": [{"key": "외국인소진율", "value": "52.10%"}]}
    assert naver._foreign_pct_from_integration(obj) == 52.1


def test_flows_from_trend_sums_recent_days():
    recs = {"dealTrendInfos": [
        {"bizdate": "20260605", "foreignerPureBuyQuant": "1000",
         "organPureBuyQuant": "-200", "foreignerHoldRatio": "52.1"},
        {"bizdate": "20260604", "foreignerPureBuyQuant": "500",
         "organPureBuyQuant": "300", "foreignerHoldRatio": "52.0"},
    ]}
    f, i, hold = naver._flows_from_trend(recs, days=20)
    assert f == 1500          # 1000 + 500
    assert i == 100           # -200 + 300
    assert hold == 52.1       # 최신 보유율


def test_flows_from_trend_limits_days():
    recs = {"dealTrendInfos": [
        {"foreignerPureBuyQuant": "100", "organPureBuyQuant": "10"},
        {"foreignerPureBuyQuant": "100", "organPureBuyQuant": "10"},
        {"foreignerPureBuyQuant": "100", "organPureBuyQuant": "10"},
    ]}
    f, i, _ = naver._flows_from_trend(recs, days=2)
    assert f == 200 and i == 20    # 최근 2행만


def test_flows_from_trend_empty():
    assert naver._flows_from_trend({}, 20) == (None, None, None)
    assert naver._flows_from_trend({"dealTrendInfos": []}, 20) == (None, None, None)


def test_num_parsing():
    assert naver._num("1,234.5") == 1234.5
    assert naver._num("5.6%") == 5.6
    assert naver._num("3.2배") == 3.2
    assert naver._num("-") is None
    assert naver._num(None) is None
