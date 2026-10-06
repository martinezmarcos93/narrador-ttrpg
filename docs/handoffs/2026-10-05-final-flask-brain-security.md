# Handoff — cierre de jornada 2026-10-05

## Estado

Rama: `feat/retrieval-evaluation`
Base lógica: `main`
No se hizo merge a `main`.
No se ejecutaron tests locales, Ollama, embeddings reales, benchmark real ni E2E.

## Cerrado en esta pasada

1. Core -> Service -> UI:
   - world advances ya pasan por NarratorService/Orchestrator;
   - se documentó la regla de no mutación de dominio desde UI;
   - se aisló VaultWriter de fallos de persistencia secundaria.

2. Flask/API:
   - nueva capa `narrator/web/`;
   - application factory;
   - DTOs;
   - session store server-side;
   - error contract;
   - request IDs;
   - body limit;
   - security headers;
   - Bearer/API-key;
   - production exige API key;
   - Origin allowlist configurable.

3. Contratos:
   - `/api/v1/health`
   - `/api/v1/sessions`
   - `/api/v1/sessions/{id}/world`
   - `/api/v1/rolls/resolve`
   - `/api/v1/turns`
   - streaming queda conscientemente para después de estabilizar el contrato.

4. Cerebro:
   - loader PDF determinista;
   - chunks;
   - provenance/hash;
   - metadata system/campaign/kind/layer;
   - indexación incremental existente;
   - filtro por system;
   - filtro por campaign;
   - script local de ingestión;
   - script local de evaluación.

5. Regresión:
   - tests web preparados;
   - casos de autenticación;
   - escenarios deterministas existentes ampliados durante la jornada.

6. Documentación:
   - `docs/ARCHITECTURE-FLASK-API-2026-10-05.md`
   - `docs/BRAIN-INGESTION-EVALUATION-2026-10-05.md`
   - `docs/SECURITY-REVIEW-2026-10-05.md`
   - roadmap actualizado.

## Lo que ahora corresponde al entorno local

1. Pull de `feat/retrieval-evaluation`.
2. Instalar dependencias incluyendo Flask.
3. Ejecutar suite pytest y corregir cualquier fallo real.
4. Levantar Flask localmente.
5. Cargar PDFs reales con `scripts/ingest_brain.py`.
6. Revisar manualmente metadata/chunks.
7. Construir embeddings del cerebro.
8. Ejecutar `scripts/evaluate_retrieval.py`.
9. Ejecutar escenario real de campaña.
10. Revisar startup/errores/UX de la nueva GUI.

## No declarar todavía

- Internet-ready.
- autenticación multiusuario completa.
- persistencia distribuida de sesiones.
- streaming web terminado.
- benchmark satisfactorio.
- retrieval satisfactorio sobre corpus real.

## Siguiente etapa después de los resultados locales

Los resultados locales deben convertirse en datos de ingeniería: errores reproducibles, métricas retrieval, casos de leakage/visibilidad, fallos de contrato HTTP y problemas de UX. A partir de eso se hace la siguiente pasada, no antes.
