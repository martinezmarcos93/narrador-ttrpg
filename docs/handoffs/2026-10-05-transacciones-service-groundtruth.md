# Handoff — 2026-10-05 — Transacciones, Service Boundary y Ground Truth

## Estado

Rama: `feat/retrieval-evaluation`
Base: `main`
Merge: no realizado.
Pruebas locales: no ejecutadas.
Ollama/benchmark real: no ejecutados.

## Trabajo realizado en esta pasada

### Transacciones

Se expuso `StateManager.batch_depth` como API pública.

`ProposalExecutor` ya no necesita consultar directamente `_batch_depth` para su recuperación de emergencia.

Además, una propuesta ejecutada dentro de un batch externo ahora respeta la frontera del llamador: cierra solamente su propia frontera y deja abierta la transacción exterior.

Se añadió regresión para esta situación.

### Service Boundary

`NarratorService` ahora expone:

- `detect_system()`
- `record_event()`
- `prepare_turn()`
- `world_status()`

La UI fue migrada en los puntos correspondientes para no llamar directamente al Orchestrator.

Todavía existen accesos directos de UI al Orchestrator para componentes de infraestructura/consulta, por lo que la migración no se considera terminada.

### Retrieval / Ground Truth

Se verificaron los IDs iniciales contra los archivos reales de `cerebro/universal`.

Se amplió el dataset con:

- agencia del jugador;
- frentes y relojes;
- información/conocimiento;
- combate;
- causalidad.

Se añadieron además relevancias graduadas para preparar nDCG más útil.

## Próximo bloque

Continuar con:

1. escenarios compuestos de rollback/fallo por etapa;
2. vertical slice de turno completo;
3. precedencia STATE > MANUAL > SYSTEM > UNIVERSAL;
4. KnowledgeVisibility integrada con retrieval;
5. casos de ground truth multi-capa y específicos por sistema;
6. Service Boundary restante.

## Restricciones

No ejecutar pruebas locales, benchmark real, deployment ni merge a `main` sin autorización expresa.
