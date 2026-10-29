from io import BytesIO

import app.services as services
from config import Config


def test_get_usd_rate_uses_configured_url(app, monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return BytesIO(b'{"rates": {"VND": 25000}}')

    monkeypatch.setattr(services.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(services, '_cache', {'rate': None, 'at': 0.0})

    with app.app_context():
        assert app.config['RATE_API_URL'] == Config.RATE_API_URL
        assert services.get_usd_rate() == 25000

    assert calls == [(Config.RATE_API_URL, 5)]


def test_get_usd_rate_falls_back_on_malformed_response(app, monkeypatch):
    monkeypatch.setattr(
        services.urllib.request, 'urlopen',
        lambda request, timeout: BytesIO(b'{"rates": null}'),
    )
    monkeypatch.setattr(services, '_cache', {'rate': 24000, 'at': 0.0})

    with app.app_context():
        assert services.get_usd_rate() == 24000
