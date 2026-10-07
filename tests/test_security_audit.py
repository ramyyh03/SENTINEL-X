"""Tests de l'auto-audit de sécurité (scripts/security_audit.py)."""
from scripts import security_audit as sa


def test_secrets_detecte_fichier_sensible_suivi():
    # Arrange : un .env et une clé privée sont suivis par Git
    suivis = {"README.md", ".env", "docker/mosquitto/certs/server.key"}

    # Act
    constat = sa.controle_secrets_versionnes(suivis)

    # Assert
    assert constat.ok is False
    assert constat.gravite == "CRITICAL"


def test_secrets_ignore_les_certificats_publics():
    # Arrange : un certificat public n'est PAS un secret
    suivis = {"docker/mosquitto/certs/ca.crt", "docker/mosquitto/certs/server.crt"}

    # Act
    constat = sa.controle_secrets_versionnes(suivis)

    # Assert
    assert constat.ok is True


def test_xss_ok_quand_server_echappe():
    # Act : le vrai api/server.py utilise html.escape partout depuis le correctif
    constat = sa.controle_xss()

    # Assert
    assert constat.ok is True


def test_cle_session_est_auto_corrigeable():
    # Act
    constat = sa.controle_cle_session()

    # Assert : qu'elle soit présente ou non, ce contrôle est réparable sans risque
    assert constat.auto_corrigeable is True or constat.ok is True


def test_rapport_retourne_code_non_nul_si_critique():
    # Arrange : un constat critique en échec
    critique = sa.Constat("Test", False, "CRITICAL", "msg", "fix")

    # Act
    code = sa.afficher_rapport([critique])

    # Assert
    assert code == 1
