# Arquitectura Flask/API — 2026-10-05

## Principio

La interfaz HTTP es un adaptador. La regla estructural es:

`HTTP/DTO -> WebApplicationService -> NarratorService -> Orchestrator/Core -> State/Persistence`

La UI nunca debe mutar `StateManager`, `WorldSimulationEngine`, relaciones, frentes, consecuencias o entidades directamente.

## Estado actual

La GUI histórica sigue en `narrator/app.py` con Dear PyGui. La nueva capa vive en `narrator/web/` y no importa Dear PyGui.

Componentes:

- `narrator/web/app.py`: Flask application factory, HTTP, request IDs, auth, límites y errores.
- `narrator/web/schemas.py`: DTOs y validación de payloads.
- `narrator/web/service.py`: fachada de aplicación para HTTP.
- `narrator/web/session_store.py`: ownership server-side de sesiones; es un seam para Redis/DB.
- `narrator/core/narrator_service.py`: dominio narrativo.
- `narrator/core/*` y `narrator/agents/*`: verdad determinista y agentes.

## Contrato v1

### GET /api/v1/health

Público.

Respuesta:

`{"ok": true, "service": "narrator", "api_version": "v1"}`

### POST /api/v1/sessions

Crea una sesión server-side.

Request:

`{"campaign": "demo", "system": "generic"}`

Respuesta 201:

`{"session_id": "...", "campaign": "demo", "system": "generic"}`

El navegador no puede declarar arbitrariamente el estado de la sesión: solo recibe un identificador opaco.

### GET /api/v1/sessions/{session_id}/world

Requiere sesión válida.

Respuesta:

`{"session_id": "...", "status": "..." }`

### POST /api/v1/rolls/resolve

Requiere sesión válida.

Request mínimo:

`{"session_id":"...", "action_text":"...", "rolls":[12], "sides":20, "system_slug":"dnd_5e", "character":{}}`

Los dados admitidos son 4, 6, 8, 10, 12, 20 y 100.

### POST /api/v1/turns

Requiere sesión válida.

Request:

`{"session_id":"...", "text":"..." }`

El contrato inicial devuelve 202 y no ejecuta todavía streaming/turn-engine HTTP. Esto es deliberado: primero se estabiliza el contrato, luego se conecta el pipeline completo.

## Errores

Formato único:

`{"error":{"code":"...","message":"...","request_id":"..."}}`

Nunca se devuelven stack traces, paths internos, prompts, credenciales ni errores crudos del proveedor.

Códigos base:

- `invalid_request` → 400
- `unauthorized` → 401
- `forbidden_origin` → 403
- `not_found` → 404
- `payload_too_large` → 413
- `internal_error` → 500

## Autenticación y sesiones

La capa HTTP admite Bearer API key mediante `NARRATOR_API_KEY`. Si `NARRATOR_ENV=production`, la clave es obligatoria al crear la aplicación.

Las sesiones son server-side. El siguiente paso antes de Internet pública es reemplazar el `SessionStore` en memoria por un backend persistente y asociar cada sesión a una identidad autenticada.

No se debe interpretar el session_id como identidad de usuario.

## Separación frontend/backend

El frontend nuevo debe consumir exclusivamente `/api/v1/*`. No debe importar módulos de `narrator.core`.

La GUI puede evolucionar hacia:

`templates/static -> fetch(/api/v1/*) -> Flask -> WebApplicationService -> NarratorService`

El streaming se incorporará después mediante SSE o WebSocket, sin mover lógica de dominio al navegador.

## Seguridad ya preparada

- límite global de body mediante `MAX_CONTENT_LENGTH`;
- Bearer/API key configurable;
- API key obligatoria en production;
- allowlist opcional de Origin;
- `X-Content-Type-Options: nosniff`;
- `X-Frame-Options: DENY`;
- `Referrer-Policy: no-referrer`;
- `Cache-Control: no-store`;
- request ID;
- errores internos redacted;
- validación estricta de DTOs;
- límites de longitud y cardinalidad;
- no confiar en estado enviado por el navegador.

## Antes de exponer a Internet

Queda pendiente en entorno local/infra:

1. HTTPS/reverse proxy.
2. identidad de usuario real y expiración de sesión.
3. SessionStore persistente.
4. CSRF si se adopta cookie authentication.
5. rate limiting.
6. auditoría de logs y secretos.
7. sandbox/allowlist de rutas de vault y documentos.
8. límites de concurrencia y timeouts del LLM.
9. CORS con dominios reales, no wildcard.
10. pruebas de penetración y smoke E2E.
