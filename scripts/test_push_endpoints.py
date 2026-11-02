"""
Test push endpoints directly.
"""

from backend.routers.push import get_digest
from backend.routers.health import health


def test_health_func():
    data = health()
    assert data["status"] == "ok"
    assert "version" in data
    print("[PASS] health endpoint:", data)


def test_push_digest_windows():
    for win in ["24h", "7d", "30d"]:
        data = get_digest(window=win)
        assert "high" in data
        assert "medium" in data
        assert "low" in data
        assert "data_as_of" in data
        total = len(data["high"]) + len(data["medium"]) + len(data["low"])
        print(f"[PASS] get_digest(window='{win}') -> total: {total} (high: {len(data['high'])}, med: {len(data['medium'])}, low: {len(data['low'])})")

    # Verify Reliance results card in 30d window
    data = get_digest(window="30d")
    rel_results = [
        item for item in data["high"]
        if item.get("ticker") == "RELIANCE.NS" and item.get("enrichment", {}).get("type") == "results_card"
    ]
    assert len(rel_results) > 0, "Expected Reliance results card in 30d window"
    enrich = rel_results[0]["enrichment"]
    metrics = enrich["data"]["metrics"]
    print(f"[PASS] Reliance Results Card found in digest:")
    print(f"       Basis: {enrich['data']['basis']}")
    print(f"       Revenue: {metrics['revenue']['current']} Cr (QoQ {metrics['revenue']['qoq_pct']}%, YoY {metrics['revenue']['yoy_pct']}%)")
    print(f"       PAT:     {metrics['pat']['current']} Cr (QoQ {metrics['pat']['qoq_pct']}%, YoY {metrics['pat']['yoy_pct']}%)")


if __name__ == "__main__":
    test_health_func()
    test_push_digest_windows()
    print("\nALL FASTAPI ENDPOINT TESTS PASSED!")
