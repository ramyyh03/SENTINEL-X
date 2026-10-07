"""Tests du lanceur unique (scripts/launch_all.py)."""
from scripts import launch_all as L


def test_services_definis():
    # Assert : les 4 processus de fond sont bien déclarés
    noms = {nom for nom, _, _ in L.SERVICES}
    assert noms == {"api", "ingest", "detect", "vision"}


def test_urls_coherentes():
    # Assert : le cockpit et le dashboard pointent sur le bon port
    assert L.URL_COCKPIT.endswith("/app")
    assert L.URL_DASHBOARD.endswith("/dashboard")


def test_ollama_pret_retourne_bool():
    # Act / Assert : jamais une exception, toujours un booléen
    assert isinstance(L.ollama_pret(), bool)


def test_rapport_ne_plante_pas(capsys):
    # Act : l'affichage de l'état ne doit jamais lever
    L._rapport(broker_ok=True, api_ok=False, ollama_ok=False)

    # Assert : il a bien écrit quelque chose
    assert "ÉTAT DU SYSTÈME" in capsys.readouterr().out
