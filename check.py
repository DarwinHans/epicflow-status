#!/usr/bin/env python3
"""check — chequea los sitios de sites.json y actualiza data/<slug>.json.

Corre en GitHub Actions cada 15 minutos. Solo stdlib, sin LLM.

Por sitio: HTTP (código y tiempo), días al vencimiento del SSL y del dominio
(whois, una vez al día). Guarda agregados diarios de 90 días más las últimas
96 muestras, para que el archivo no crezca.

Alertas a Telegram solo cuando cambia el estado (caído <-> arriba, SSL o
dominio por vencer), no en cada corrida. Un sitio se da por caído después de
FALLOS_PARA_CAIDO chequeos fallidos seguidos: un solo fallo suele ser la red
del runner, no el sitio.

Variables: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (si faltan, no avisa).
           STATUS_DATA_DIR (para tests).
"""
from __future__ import annotations

import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("STATUS_DATA_DIR", ROOT / "data"))
FALLOS_PARA_CAIDO = 2
SSL_AVISO_DIAS = 14
DOMINIO_AVISO_DIAS = 30
DIAS_HISTORIA = 90
MUESTRAS_RECIENTES = 96
WHOIS = {"cl": "whois.nic.cl", "com": "whois.verisign-grs.com", "net": "whois.verisign-grs.com"}


# ── Chequeos ────────────────────────────────────────────────────────────────

def chequear_http(url: str) -> dict:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "epicflow-status/1 (+https://status.epicflowworld.com)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            code, err = r.status, ""
    except urllib.error.HTTPError as e:
        code, err = e.code, f"HTTP {e.code}"
    except (urllib.error.URLError, OSError) as e:
        code, err = None, str(getattr(e, "reason", e))[:120]
    ms = int((time.time() - t0) * 1000)
    return {"ok": bool(code and code < 400), "http": code, "ms": ms, "error": err}


def dias_ssl(url: str) -> int | None:
    host = urllib.parse.urlparse(url).hostname
    try:
        with socket.create_connection((host, 443), timeout=10) as s:
            with ssl.create_default_context().wrap_socket(s, server_hostname=host) as ss:
                exp = datetime.strptime(ss.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z")
    except (OSError, ssl.SSLError, KeyError, ValueError):
        return None
    return (exp.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days


def parse_vencimiento_whois(texto: str) -> datetime | None:
    """Fecha de vencimiento en respuestas de whois.nic.cl y de Verisign."""
    for pat in (r"Expiration date:\s*([0-9-]+ [0-9:]+)",          # whois.nic.cl
                r"Fecha de expiraci[oó]n:\s*([0-9-]+)",
                r"Registry Expiry Date:\s*([0-9T:-]+)"):          # Verisign
        m = re.search(pat, texto, re.I)
        if m:
            raw = m.group(1).strip().replace("T", " ")
            for fmt, largo in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
                try:
                    return datetime.strptime(raw[:largo], fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    return None


def dias_dominio(dominio: str) -> int | None:
    server = WHOIS.get(dominio.rsplit(".", 1)[-1])
    if not server:
        return None
    try:
        with socket.create_connection((server, 43), timeout=15) as s:
            s.sendall((dominio + "\r\n").encode())
            buf = b""
            while chunk := s.recv(4096):
                buf += chunk
    except OSError:
        return None
    exp = parse_vencimiento_whois(buf.decode("utf-8", "replace"))
    return (exp - datetime.now(timezone.utc)).days if exp else None


# ── Estado (puro, cubierto por test_check.py) ───────────────────────────────

def nivel(rec: dict) -> str:
    """Nivel que dispara alertas: caido > ssl > dominio > ok."""
    if rec.get("estado") == "caido":
        return "caido"
    if rec.get("ssl_dias") is not None and rec["ssl_dias"] < SSL_AVISO_DIAS:
        return "ssl"
    if rec.get("dominio_dias") is not None and rec["dominio_dias"] < DOMINIO_AVISO_DIAS:
        return "dominio"
    return "ok"


def aplicar(rec: dict, res: dict, ahora: datetime) -> dict:
    """Incorpora un resultado de chequeo al registro del sitio y devuelve el registro nuevo."""
    rec = dict(rec)
    rec["fallos_seguidos"] = 0 if res["ok"] else rec.get("fallos_seguidos", 0) + 1
    if res["ok"]:
        rec["estado"] = "arriba"
    elif rec["fallos_seguidos"] >= FALLOS_PARA_CAIDO:
        rec["estado"] = "caido"
    else:
        rec.setdefault("estado", "arriba")   # un fallo aislado no cambia el estado
    rec["ultimo"] = {"ts": ahora.isoformat(timespec="seconds"), **res}

    dias = dict(rec.get("dias", {}))
    hoy = ahora.strftime("%Y-%m-%d")
    ok, total = dias.get(hoy, [0, 0])
    dias[hoy] = [ok + (1 if res["ok"] else 0), total + 1]
    rec["dias"] = {k: dias[k] for k in sorted(dias)[-DIAS_HISTORIA:]}

    recientes = list(rec.get("recientes", [])) + [[int(ahora.timestamp()), 1 if res["ok"] else 0, res["ms"]]]
    rec["recientes"] = recientes[-MUESTRAS_RECIENTES:]
    rec["actualizado"] = ahora.isoformat(timespec="seconds")
    return rec


def mensaje_alerta(sitio: dict, antes: str, despues: str, rec: dict) -> str | None:
    if antes == despues:
        return None
    n = sitio["nombre"]
    if despues == "caido":
        return f"CAÍDO: {n} ({rec['ultimo'].get('error') or 'HTTP ' + str(rec['ultimo'].get('http'))}) — {sitio['url']}"
    if despues == "ssl":
        return f"AVISO: {n}, el certificado SSL vence en {rec['ssl_dias']} días"
    if despues == "dominio":
        return f"AVISO: {n}, el dominio {sitio['dominio']} vence en {rec['dominio_dias']} días"
    if antes == "caido":
        return f"OK: {n} volvió a estar arriba ({rec['ultimo']['ms']} ms)"
    return f"OK: {n}, aviso de {antes} resuelto"


# ── Orquestación ────────────────────────────────────────────────────────────

def avisar(texto: str) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    print("ALERTA:", texto)
    if not (token and chat):
        return
    body = urllib.parse.urlencode({"chat_id": chat, "text": f"[epicflow-status] {texto}"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=body, timeout=15)
    except (urllib.error.URLError, OSError) as e:
        print("no se pudo avisar a Telegram:", e, file=sys.stderr)


def main() -> int:
    if "--prueba-telegram" in sys.argv:
        # Verifica secrets y entrega sin tocar datos (workflow_dispatch con prueba=true).
        avisar("prueba de entrega: si lees esto, las alertas de caída van a llegar aquí.")
        return 0
    sitios = json.loads((ROOT / "sites.json").read_text())
    DATA.mkdir(exist_ok=True)
    ahora = datetime.now(timezone.utc)
    for s in sitios:
        path = DATA / f"{s['slug']}.json"
        rec = json.loads(path.read_text()) if path.exists() else {}
        antes = nivel(rec) if rec else "ok"
        rec = aplicar(rec, chequear_http(s["url"]), ahora)
        rec.update({"slug": s["slug"], "nombre": s["nombre"], "url": s["url"], "publico": s["publico"]})
        rec["ssl_dias"] = dias_ssl(s["url"])
        # whois una vez al día si respondió, cada 6 h si falló: los registros limitan
        # consultas y el dato cambia lento. whois.nic.cl suele no responder a IPs
        # de GitHub y .cl no tiene RDAP, así que para .cl esto es best effort.
        ult = rec.get("dominio_chequeado")
        espera = 86400 if rec.get("dominio_dias") is not None else 6 * 3600
        if s.get("dominio") and (not ult or (ahora - datetime.fromisoformat(ult)).total_seconds() > espera):
            d = dias_dominio(s["dominio"])
            if d is not None:
                rec["dominio_dias"] = d
            rec["dominio_chequeado"] = ahora.isoformat(timespec="seconds")
        msg = mensaje_alerta(s, antes, nivel(rec), rec)
        if msg:
            avisar(msg)
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
        print(f"{s['slug']:18} {rec['estado']:7} http={rec['ultimo']['http']} {rec['ultimo']['ms']}ms ssl={rec['ssl_dias']} dom={rec.get('dominio_dias')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
