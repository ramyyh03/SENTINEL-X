"""Tests de la Brique 6.2 — SensorHealthMonitor."""
from datetime import datetime, timedelta, timezone

from predictive.sensor_health import SensorHealthMonitor

T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


def _msg(temp=25.0, humidity=50.0, gas=150, presence=0, offset_s=0):
    ts = (T0 + timedelta(seconds=offset_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"temp": temp, "humidity": humidity, "gas": gas,
            "presence": presence, "timestamp": ts}


def test_sain():
    m = SensorHealthMonitor()
    r = m.update(_msg(offset_s=0))
    r = m.update(_msg(temp=25.2, offset_s=2))
    assert r["statuses"]["temp"].status == "healthy"
    assert r["overall_health"]["level"] == "HEALTHY"


def test_hors_limites():
    m = SensorHealthMonitor()
    r = m.update(_msg(temp=200, offset_s=0))   # 200 °C impossible
    assert r["statuses"]["temp"].status == "failed"
    assert r["statuses"]["temp"].severity == "CRITICAL"


def test_fige_stuck():
    m = SensorHealthMonitor()
    r = None
    for i in range(10):                        # même valeur 10 fois
        r = m.update(_msg(temp=25.0, humidity=50 + i, offset_s=i * 2))
    assert r["statuses"]["temp"].status == "stuck"
    assert r["statuses"]["temp"].severity == "WARNING"


def test_derive_drift():
    m = SensorHealthMonitor()
    m.update(_msg(temp=25.0, offset_s=0))
    r = m.update(_msg(temp=70.0, offset_s=1))  # +45 °C en 1 s = impossible
    assert r["statuses"]["temp"].status == "drift"


def test_timeout():
    m = SensorHealthMonitor(timeout_seconds=60)
    m.update(_msg(offset_s=0))
    r = m.update(_msg(offset_s=120))           # 120 s de trou
    assert r["statuses"]["temp"].status == "timeout"
    assert r["statuses"]["temp"].severity == "CRITICAL"


def test_presence_constante_pas_stuck():
    m = SensorHealthMonitor()
    r = None
    for i in range(15):                        # PIR=0 longtemps = NORMAL
        r = m.update(_msg(presence=0, temp=25 + i * 0.1, offset_s=i * 2))
    assert r["statuses"]["presence"].status == "healthy"
