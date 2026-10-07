"""Tests de l'analyse de connectivité et du cockpit (api/server.py)."""
from api import server


def test_statut_systeme_structure(tmp_path):
    # Arrange : une base vide (aucune mesure)
    db = tmp_path / "vide.db"

    # Act
    etat = server._statut_systeme(db)

    # Assert : toutes les briques attendues sont présentes
    attendus = {"api", "broker", "esp32", "webcam", "detection", "ollama", "ia"}
    assert attendus.issubset(etat["composants"].keys())
    assert etat["composants"]["api"]["ok"] is True       # l'API répond toujours
    assert isinstance(etat["tout_ok"], bool)


def test_tcp_ouvert_port_ferme():
    # Act : un port improbable sur localhost est fermé
    assert server._tcp_ouvert("127.0.0.1", 59999, timeout=0.5) is False


def test_age_derniere_mesure_sans_donnees(tmp_path):
    # Act / Assert : pas de base -> pas d'âge
    assert server._age_derniere_mesure(tmp_path / "absent.db") is None


def test_page_cockpit_contient_elements():
    # Act
    html = server._page_cockpit()

    # Assert : le cockpit embarque l'analyse et les onglets
    assert "Cockpit" in html
    assert "/api/v1/status" in html
    assert 'src="/dashboard"' in html


def test_page_security_rend_une_page():
    # Act
    html = server._page_security()

    # Assert
    assert "Suis-je sécurisé" in html and "<table>" in html
