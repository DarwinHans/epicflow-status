# epicflow-status

Monitoreo de los sitios que mantiene Epic Flow AI y una página de estado por cliente en `status.epicflowworld.com/<cliente>/`.

- `check.py` corre en GitHub Actions cada 15 minutos. Chequea HTTP, SSL y vencimiento del dominio (para `.cl` es best effort: whois.nic.cl no siempre responde a IPs de GitHub y `.cl` no tiene RDAP), y guarda `data/<slug>.json` con 90 días de agregados diarios. Avisa a Telegram solo cuando cambia el estado; un sitio cuenta como caído después de 2 fallos seguidos.
- `build.py` genera `site/` (GitHub Pages) con una página por sitio con `"publico": true`. Cada página muestra solo su propio sitio y lee los datos en vivo, así que no se redespliega en cada chequeo.
- `sites.json` es la lista de sitios. Para agregar un cliente: sumar una entrada y, cuando la página esté revisada, poner `"publico": true`.

Solo stdlib de Python, sin dependencias ni LLM. Tests: `python3 test_check.py`.

Secrets del repo: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

Parte del Agentic OS de Darwin Hans: ver `~/proyectos/_sistema/ARQUITECTURA.md`.
