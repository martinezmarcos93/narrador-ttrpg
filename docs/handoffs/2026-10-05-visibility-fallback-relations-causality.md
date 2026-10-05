# Handoff — 2026-10-05 — Visibilidad, fallback, relaciones y causalidad

## Rama
- feat/retrieval-evaluation
- Sin merge a main.
- No se ejecutaron pruebas locales.

## Trabajo cerrado

### Visibilidad
- Recall por mención ya usa KnowledgeRouter y no una ruta directa que pueda saltarse la política de visibilidad.
- Entidades con llm_visible=false o visibilidad secreta/privada no participan del recall por mención.
- Regresión router → PromptBuilder preparada para impedir fuga de fragmentos restringidos.

### Fallback
- NarratorService expone apply_proposal_with_fallback().
- Propuesta inválida/rechazada: fallback explícito narration_only; no se intenta corregir ni ejecutar parcialmente.
- app.py registra el resultado rechazado en TurnContract.

### Relaciones
- relations forma parte de NarrativeProposal.
- ProposalValidator transporta relations a ContinuityValidator.
- StateManager persiste relaciones dentro de la misma propuesta.
- Se añadió regresión social.
- front_clock_delta valida existencia del reloj y límites acumulados.

### Causalidad
- Métrica depth_limit_reached.
- Regresiones de cadena larga y ciclo.
- Múltiples consecuencias siguen pudiendo activarse en una cascada.
- Pendiente: cross-front real entre múltiples relojes y consecuencias.

### Persistencia
- Regresión de fallo de serialización: conserva el archivo anterior y elimina temporales.
- Regresión de estado corrupto: cuarentena/backup antes de continuar.

### Retrieval
- Ground truth ampliado con casos ambiguos/multi-capa.
- Casos específicos por sistema para V20 y D&D.
- Benchmark real: LOCAL PENDIENTE.

### Auditoría legacy
- Revisados app.py, NarratorAgent, Orchestrator y VaultWriter.
- No se detectó otro bypass directo de personaje/entidades fuera del postprocesado compuesto.
- Pendiente auditoría exhaustiva de writers/background persistence y accesos internos UI/Core.

## Restricciones
- No local tests.
- No benchmark real.
- No pull/copia local.
- No merge.

## Siguiente bloque
1. E2E de visibilidad con estado/perspectiva/campaña real.
2. Writers/background persistence y Core/Service/UI.
3. Cross-front, umbrales y múltiples relojes.
4. Ground truth con IDs reales de System Packs.
5. Recuperación tras reinicio de consecuencias/relaciones.
6. Campaña real y evaluación LOCAL.
