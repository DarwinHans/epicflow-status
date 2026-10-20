#!/usr/bin/env python3
"""build — genera site/ para GitHub Pages a partir de sites.json y plantilla/.

Una página por sitio con "publico": true, en /<slug>/. Cada página muestra solo
su propio sitio: nunca lista a otros clientes. La portada tampoco los lista.
Las páginas no traen datos incrustados: los leen al abrirse desde data/<slug>.json
en raw.githubusercontent.com, así que no hace falta redesplegar en cada chequeo.

Uso:  python3 build.py   (lo corre el workflow pages.yml)
"""
import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
SITE = ROOT / "site"
REPO = "DarwinHans/epicflow-status"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/data"

PORTADA = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Estado de servicios · Epic Flow AI</title><link rel="icon" href="favicon.svg" type="image/svg+xml">
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0a0e12;color:#f0f3f5;
font:16px/1.5 ui-sans-serif,system-ui,sans-serif;padding:20px;text-align:center}p{color:#9aa3ad;max-width:42ch}</style>
</head><body><div><h1>Epic Flow AI · Monitoreo</h1>
<p>Cada cliente con mantención tiene su propia página de estado. Si buscas la tuya, usa el enlace que te enviamos.</p>
</div></body></html>
"""


def main() -> None:
    sitios = json.loads((ROOT / "sites.json").read_text())
    plantilla = (ROOT / "plantilla/cliente.html").read_text()
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    (SITE / ".nojekyll").write_text("")
    shutil.copy(ROOT / "plantilla/favicon.svg", SITE / "favicon.svg")
    (SITE / "index.html").write_text(PORTADA)
    (SITE / "404.html").write_text(PORTADA)
    for s in sitios:
        if not s.get("publico"):
            continue
        out = SITE / s["slug"]
        out.mkdir()
        page = (plantilla.replace("{{NOMBRE}}", html.escape(s["nombre"]))
                         .replace("{{DATA_URL}}", f"{RAW}/{s['slug']}.json"))
        (out / "index.html").write_text(page)
        print(f"site/{s['slug']}/index.html")


if __name__ == "__main__":
    main()
