from pathlib import Path


def test_metrics_endpoint_present():
    text = Path('app/main.py').read_text()
    assert "@app.get('/metrics'" in text
    assert "@app.get('/connectors/catalog'" in text
