# Handoff — 2026-10-05 — Visibilidad, fallback, relaciones y causalidad

## Rama
- feat/retrieval-evaluation
- 99 commits por delante de main, 0 por detrás al momento de este handoff.
- No mergeado.

## Trabajo cerrado en esta pasada

### Visibilidad E2E
- KnowledgeRouter expone una ruta pública para recuperar campaña visible.
- Recall por mención en Orchestrator dejó de usar una ruta directa que podía saltarse KnowledgeRouter.
- Los nombres de NPCs/locaciones con `llm_visible=false` o visibilidad secreta/privada ya no participan del recall por mención.
- Se añadió regresión router → PromptBuilder para impedir que un fragmento restringido llegue al prompt final.

### Fallback determinista
- NarratorService agrega `apply_proposal_with_fallback()`.
- Propuesta inválida/rechazada: no se intenta corregir ni ejecutar parcialmente; el resultado explícita `narration_only`.
- app.py registra ese resultado en TurnContract.

### Relaciones sociales
- `relations` forma parte de ALLOWED_KEYS/NarrativeProposal.
- ProposalValidator transporta relaciones hacia ContinuityValidator.
- StateManager persiste relaciones dentro de la misma propuesta/transacción.
- Se añadió regresión compuesta de relación social.
- Se añadió validación de `front_clock_delta` contra relojes existentes y límites acumulados.

### Causalidad
- Métrica `depth_limit_reached`.
- Regresiones para cadenas largas y ciclos.
- Se conserva la ejecución de múltiples consecuencias de un mismo evento.
- Queda pendiente probar interacción cross-front real entre múltiples relojes.

### Persistencia
- Regresión de fallo de serialización YAML: el archivo anterior se conserva y no quedan temporales.
- Regresión de estado corrupto: se mueve a backup/cuarentena antes de continuar.

### Retrieval / ground truth
- Ground truth ampliado con casos ambiguos/multi-capa.
- Casos específicos por sistema: V20 y D&D.
- Benchmark real sigue siendo LOCAL PENDIENTE.

## Auditoría legacy
- Revisados app.py, NarratorAgent, Orchestrator y VaultWriter.
- No se detectó otro bypass directo de personaje/entidades fuera de la ruta compuesta de postprocesado.
- Sigue pendiente auditar exhaustivamente writers/background persistence y otros accesos internos de UI.

## Restricciones operativas
- No se ejecutaron pruebas locales.
- No se ejecutó benchmark real.
- No se hizo pull/copia local.
- No se mergeó a main.

## Siguiente bloque recomendado
1. Completar E2E de visibilidad incluyendo estado/perspectiva/campaña real.
2. Auditar writers/background persistence y accesos Core/Service/UI.
3. Completar cross-front: múltiples relojes, umbrales y consecuencias cruzadas.
4. Ampliar ground truth con IDs específicos de System Packs cuando el inventario del cerebro permita verificarlos.
5. Preparar escenarios de recuperación tras reinicio y persistencia de consecuencias/relaciones.
6. Luego avanzar hacia campaña real y evaluación LOCAL.
