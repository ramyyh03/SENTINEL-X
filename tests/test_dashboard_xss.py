"""Test de sécurité (CYBER) — le dashboard ne doit jamais exécuter du contenu reçu.

Faille corrigée : XSS stockée. Une alerte ou une mesure contenant du HTML était
recopiée telle quelle dans /dashboard et /live, donc exécutée par le navigateur
de l'opérateur connecté (contournement du login + 2FA).

Lancer :  python -m pytest tests/test_dashboard_xss.py -v
"""
from __future__ import annotations

import sqlite3

import pytest

from api import auth
from api.alert_store import AlertStore
from api.server import create_app

CHARGE = "<script>alert('xss')</script>"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """API de test sur une base temporaire, dashboard accessible sans compte."""
    monkeypatch.setattr(auth, "comptes_existants", lambda: False)
    store = AlertStore(db_path=str(tmp_path / "test.db"))
    app = create_app(store)
    return app.test_client(), store


def _alerte(**surcharge):
    base = {"source": "ia_vision", "type": "intrusion_detected", "confidence": 0.9,
            "timestamp": "2026-10-07T08:00:00Z", "details": {}}
    base.update(surcharge)
    return base


@pytest.mark.parametrize("alerte", [
    _alerte(source=CHARGE),
    _alerte(type=CHARGE),
    _alerte(timestamp=CHARGE),
    _alerte(details={"context": CHARGE}),
    _alerte(details={"severity": CHARGE}),
])
def test_dashboard_echappe_le_contenu_des_alertes(client, alerte):
    c, _ = client
    assert c.post("/api/v1/alerts", json=alerte).status_code == 201
    page = c.get("/dashboard").get_data(as_text=True)
    assert "<script>alert(" not in page          # rien d'exécutable
    assert "&lt;script&gt;" in page.lower()       # mais le texte reste visible


def test_live_echappe_les_mesures(client):
    c, store = client
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sensor_data (id INTEGER PRIMARY KEY, "
                     "timestamp TEXT, temp REAL, humidity REAL, gas REAL, presence INTEGER)")
        conn.execute("INSERT INTO sensor_data (timestamp, temp, humidity, gas, presence) "
                     "VALUES (?, 22.5, 45.0, 300, 0)", (CHARGE,))
    page = c.get("/live").get_data(as_text=True)
    assert "<script>alert(" not in page
    assert "&lt;script&gt;" in page
