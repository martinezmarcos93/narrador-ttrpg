# Despliegue de la API y la GUI web

Local-first: por defecto el servidor escucha solo en `127.0.0.1`.

## Local

```bash
python -m narrator.web            # http://127.0.0.1:8765
```

Sin claves configuradas funciona en modo local (un solo usuario).

## Multiusuario

```bash
cp .env.example .env              # NARRATOR_WEB_DB y NARRATOR_API_KEY
python scripts/manage_api_keys.py crear ana     # la clave se muestra una sola vez
python scripts/manage_api_keys.py rotar <id>    # revoca y emite una nueva
python scripts/manage_api_keys.py revocar <id>
```

Cada usuario ve solo sus sesiones; la clave de `NARRATOR_API_KEY` es admin.
Los turnos se serializan: el motor comparte un único estado de campaña.

## Exponerlo a internet

1. Servicio persistente con systemd: `deploy/narrador-web.service`.
2. HTTPS con reverse proxy: `deploy/Caddyfile` (certificados automáticos) o
   `deploy/nginx.conf`. Ambos desactivan el buffering para el streaming SSE.
3. En `.env`: `NARRATOR_ENV=production`, `NARRATOR_TRUSTED_PROXIES=1`,
   `NARRATOR_ALLOWED_ORIGINS=https://tu-dominio`.
4. Opcional: `pip install waitress` (pasar antes por la auditoría de dependencias);
   sin waitress se usa el servidor de werkzeug con un aviso.

## Hardening incluido

| Control | Dónde |
|---|---|
| Autenticación Bearer, claves con hash, rotación/revocación | `narrator/web/store.py` |
| Aislamiento de sesiones por dueño (ajenas = 404) | `narrator/web/service.py` |
| Límite de pedidos por identidad (429) | `RateLimiter` en `narrator/web/app.py` |
| Límite de cuerpo (413) antes de parsear | `before_request` |
| CSP estricta, X-Frame-Options, nosniff, no-referrer, no-store, HSTS en producción | `after_request` |
| Errores sin trazas ni rutas; 404/405 con su código | manejadores de error |
| Documentos tratados como datos (anti prompt injection) | `narrator/core/injection_guard.py` |
| Smoke E2E y pen-test básico | `python scripts/smoke_web.py [--llm]` |
