# Security Review — 2026-10-05

## Cerrado en código

- HTTP request size cap.
- DTO validation and cardinality limits.
- Server-side session registry.
- Bearer API key boundary.
- Production requires API key.
- Optional Origin allowlist.
- Security response headers.
- Stable request IDs.
- Generic 500 response.
- No raw stack trace in client responses.
- Domain mutations remain behind NarratorService.
- Knowledge visibility remains upstream of VaultWriter.
- Atomic state persistence.
- Restricted campaign fragments are excluded from visible retrieval.

## Riesgos todavía abiertos

### Authentication

La API key es una barrera operativa, no un sistema completo de identidad. Antes de servicio público se necesita identidad por usuario, rotación, expiración y revocación.

### Sessions

El store actual es memoria de proceso. Reinicio = pérdida de sesiones HTTP. Debe sustituirse por Redis/DB antes de múltiples workers.

### Filesystem

Cualquier endpoint futuro que reciba rutas de PDFs/vault debe aceptar únicamente IDs/roots allowlisted. Nunca una ruta arbitraria proporcionada por el cliente.

### LLM/Ollama

No exponer Ollama directamente a Internet. Flask/API debe ser el único perímetro.

### Logs

No registrar prompts completos, tokens de autenticación, documentos privados ni secretos.

### CORS/CSRF

Con Bearer headers, mantener CORS explícito. Si se cambia a cookies, añadir CSRF antes de habilitar mutaciones.

### Rate limiting

Debe existir antes de permitir endpoints que disparen inferencia o indexación costosa.

## Go/no-go

El sistema está preparado para comenzar desarrollo local de la nueva GUI, pero **no está declarado Internet-ready**. La publicación requiere cerrar los riesgos abiertos y ejecutar pruebas locales/E2E.
