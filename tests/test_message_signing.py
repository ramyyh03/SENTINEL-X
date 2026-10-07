"""Tests de la signature HMAC anti-injection (security/message_signing.py)."""
from security.message_signing import message_canonique, signer, verifier

SECRET = "cle-partagee-equipe-6"
MESSAGE = {"temp": 23.4, "humidity": 51.0, "gas": 180,
           "presence": 1, "timestamp": "2026-10-07T12:00:00Z"}


def test_signature_valide_est_acceptee():
    # Arrange
    sig = signer(MESSAGE, SECRET)

    # Act / Assert
    assert verifier(MESSAGE, sig, SECRET) is True


def test_message_falsifie_est_rejete():
    # Arrange : l'attaquant modifie le gaz après signature
    sig = signer(MESSAGE, SECRET)
    falsifie = {**MESSAGE, "gas": 9999}

    # Act / Assert
    assert verifier(falsifie, sig, SECRET) is False


def test_mauvaise_cle_est_rejetee():
    # Arrange : l'attaquant ne connaît pas la clé
    sig = signer(MESSAGE, SECRET)

    # Act / Assert
    assert verifier(MESSAGE, sig, "mauvaise-cle") is False


def test_signature_vide_est_rejetee():
    # Act / Assert
    assert verifier(MESSAGE, "", SECRET) is False


def test_message_canonique_est_deterministe():
    # Assert : format figé, identique à celui calculé côté ESP32
    assert message_canonique(MESSAGE) == "23.4|51.0|180|1|2026-10-07T12:00:00Z"
