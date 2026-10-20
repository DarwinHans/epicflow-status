#!/usr/bin/env python3
"""Tests de la lógica de estado de check.py. Sin red.  Correr: python3 test_check.py"""
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("check", str(Path(__file__).parent / "check.py"))
ck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ck)

fallos = []


def check(nombre, cond, extra=""):
    print(f"  {'OK  ' if cond else 'FALLA'} {nombre}{'' if cond else '  ' + str(extra)}")
    if not cond:
        fallos.append(nombre)


T0 = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
OK = {"ok": True, "http": 200, "ms": 300, "error": ""}
MAL = {"ok": False, "http": None, "ms": 15000, "error": "timed out"}
SITIO = {"nombre": "Monkey", "url": "https://x.cl/", "dominio": "x.cl"}

print("estado")
r = ck.aplicar({}, OK, T0)
check("primer ok = arriba", r["estado"] == "arriba" and r["fallos_seguidos"] == 0)
r = ck.aplicar(r, MAL, T0 + timedelta(minutes=15))
check("un fallo aislado no cae", r["estado"] == "arriba" and r["fallos_seguidos"] == 1, r["estado"])
r = ck.aplicar(r, MAL, T0 + timedelta(minutes=30))
check("dos fallos seguidos = caído", r["estado"] == "caido", r["estado"])
r = ck.aplicar(r, OK, T0 + timedelta(minutes=45))
check("ok vuelve a arriba", r["estado"] == "arriba" and r["fallos_seguidos"] == 0)
check("agregado diario", r["dias"]["2026-10-19"] == [2, 4], r["dias"])

print("retención")
r = {}
for i in range(100):
    r = ck.aplicar(r, OK, T0 + timedelta(days=i))
check("90 días de historia", len(r["dias"]) == 90 and "2026-10-19" not in r["dias"], len(r["dias"]))
check(f"{ck.MUESTRAS_RECIENTES} muestras recientes", len(r["recientes"]) == ck.MUESTRAS_RECIENTES)

print("niveles y alertas")
check("nivel ok", ck.nivel({"estado": "arriba", "ssl_dias": 80, "dominio_dias": 300}) == "ok")
check("nivel ssl", ck.nivel({"estado": "arriba", "ssl_dias": 5}) == "ssl")
check("nivel dominio", ck.nivel({"estado": "arriba", "ssl_dias": 80, "dominio_dias": 10}) == "dominio")
check("caído gana", ck.nivel({"estado": "caido", "ssl_dias": 5}) == "caido")
rc = {"ultimo": {"error": "timed out", "http": None, "ms": 1}, "ssl_dias": 5, "dominio_dias": 10}
check("sin cambio no avisa", ck.mensaje_alerta(SITIO, "ok", "ok", rc) is None)
check("avisa caída", ck.mensaje_alerta(SITIO, "ok", "caido", rc).startswith("CAÍDO: Monkey"))
check("avisa vuelta", ck.mensaje_alerta(SITIO, "caido", "ok", rc).startswith("OK: Monkey volvió"))
check("avisa SSL", "vence en 5" in ck.mensaje_alerta(SITIO, "ok", "ssl", rc))

print("whois")
check("nic.cl", ck.parse_vencimiento_whois("Expiration date: 2028-10-14 18:49:18 CLST").year == 2028)
check("verisign", ck.parse_vencimiento_whois("   Registry Expiry Date: 2027-05-29T22:32:47Z").month == 5)
check("sin fecha = None", ck.parse_vencimiento_whois("No match") is None)

print()
print("TODO OK" if not fallos else f"{len(fallos)} FALLAS: {fallos}")
sys.exit(1 if fallos else 0)
