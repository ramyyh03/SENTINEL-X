"""Tests de sécurité (CYBER) — qui a le droit de faire quoi sur l'API.

Règle : sans configuration explicite, rien n'est accessible depuis le réseau.

Lancer :  python -m pytest tests/ -v
"""
from __future__ import annotations

import pyotp
import pytest

from api import auth, server
from api.alert_store import AlertStore

RESEAU = {"REMOTE_ADDR": "192.168.43.99"}   # une machine du réseau (pas le PC serveur)
ALERTE = {"source": "ia_vision", "type": "intrusion_detected", "confidence": 0.9,
          "timestamp": "2026-10-07T08:00:00Z", "details": {}}


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """API de test : base et fichier de comptes temporaires, compteurs remis à zéro."""
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(server, "ALERT_TOKEN", "")
    server._echecs_login_par_ip.clear()
    server._requetes_par_ip.clear()
    return server.create_app(AlertStore(db_path=str(tmp_path / "test.db")))


# --- Envoi d'alertes ---------------------------------------------------------

def test_alerte_acceptee_depuis_le_pc_serveur(app):
    assert app.test_client().post("/api/v1/alerts", json=ALERTE).status_code == 201


def test_alerte_refusee_depuis_le_reseau_sans_jeton(app):
    r = app.test_client().post("/api/v1/alerts", json=ALERTE, environ_overrides=RESEAU)
    assert r.status_code == 403


def test_alerte_depuis_le_reseau_avec_jeton(app, monkeypatch):
    monkeypatch.setattr(server, "ALERT_TOKEN", "jeton-de-test")
    c = app.test_client()
    mauvais = c.post("/api/v1/alerts", json=ALERTE, environ_overrides=RESEAU,
                     headers={"X-Sentinel-Token": "faux"})
    bon = c.post("/api/v1/alerts", json=ALERTE, environ_overrides=RESEAU,
                 headers={"X-Sentinel-Token": "jeton-de-test"})
    assert (mauvais.status_code, bon.status_code) == (403, 201)


# --- Dashboard sans compte ---------------------------------------------------

@pytest.mark.parametrize("page", ["/dashboard", "/live", "/camera"])
def test_sans_compte_le_reseau_est_refuse(app, page):
    c = app.test_client()
    assert c.get(page).status_code == 200                              # PC serveur
    assert c.get(page, environ_overrides=RESEAU).status_code == 403    # réseau


# --- Login -------------------------------------------------------------------

def test_avec_compte_login_obligatoire_meme_en_local(app):
    auth.creer_utilisateur("admin", "motdepasse1")
    assert app.test_client().get("/dashboard").status_code == 302


def test_login_bloque_apres_trop_d_echecs(app):
    secret = auth.creer_utilisateur("admin", "motdepasse1")
    c = app.test_client()
    faux = {"username": "admin", "password": "faux", "code": "000000"}
    codes = [c.post("/login", data=faux, environ_overrides=RESEAU).status_code
             for _ in range(server.LOGIN_MAX_ECHECS + 2)]
    assert codes[:server.LOGIN_MAX_ECHECS] == [401] * server.LOGIN_MAX_ECHECS
    assert codes[-1] == 429
    # Même le BON mot de passe est refusé pendant le blocage (sinon il ne sert à rien)
    bon = {"username": "admin", "password": "motdepasse1", "code": pyotp.TOTP(secret).now()}
    assert c.post("/login", data=bon, environ_overrides=RESEAU).status_code == 429
    # Une autre adresse n'est pas pénalisée
    assert c.post("/login", data=bon).status_code == 302
