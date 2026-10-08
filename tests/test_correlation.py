"""Tests de la fusion multi-capteurs (predictive/correlation.py)."""
from predictive.correlation import analyser, humidex


def _v(temp=22, hum=50, gas=0, presence=0):
    return {"temp": temp, "humidity": hum, "gas": gas, "presence": presence}


def test_incendie_gaz_temp_monte_humidite_baisse():
    s = analyser(_v(gas=400), {"dtemp": 4, "dhum": -6}, cam_personnes=0)
    assert s.nom == "INCENDIE" and s.severite == "CRITICAL"


def test_fuite_gaz_sans_chaleur():
    s = analyser(_v(gas=400), {"dtemp": 0, "dhum": 0}, cam_personnes=0)
    assert s.nom == "FUITE_GAZ" and s.severite == "CRITICAL"


def test_intrusion_camera_plus_pir():
    s = analyser(_v(presence=1), {}, cam_personnes=1)
    assert s.nom == "INTRUSION" and s.severite == "CRITICAL"


def test_presence_un_seul_capteur_est_warning():
    s = analyser(_v(presence=1), {}, cam_personnes=0)
    assert s.nom == "PRESENCE" and s.severite == "WARNING"


def test_normal_quand_tout_va_bien():
    s = analyser(_v(), {"dtemp": 0, "dhum": 0}, cam_personnes=0)
    assert s.nom == "NORMAL"


def test_humidex_augmente_avec_humidite():
    # À température égale, plus d'humidité => indice de chaleur plus élevé
    assert humidex(30, 80) > humidex(30, 30)
