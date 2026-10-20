# Frontera Core / Service / UI

```
Dear PyGui (narrator/app.py) ─┐
                              ├─> NarratorService ─> Orchestrator ─> Core
Flask (narrator/web/*)  ──────┘     (fachada)        (coordinación)   (StateManager,
                                                                       CausalityEngine,
                                                                       KnowledgeRouter, ...)
```

## Reglas

1. **La UI solo habla con `NarratorService`.** Ni `app.py` ni `narrator/web/` pueden
   leer `orchestrator`, `retriever`, `builder`, `scenes`, `pacing_agent` ni `causality`.
   Lo verifica `tests/test_service_boundary.py` analizando el AST.
2. **La UI no muta estado de dominio.** Las mutaciones estructuradas (personaje,
   entidades, relojes, relaciones, consecuencias) entran como propuesta por
   `apply_proposal*` y pasan por `ProposalExecutor` (validación + rollback).
3. **Flask no contiene lógica de juego.** `narrator/web/service.py` traduce HTTP a
   llamadas de `NarratorService` y verifica pertenencia de sesión.

## API pública de `NarratorService`

| Grupo | Métodos |
|---|---|
| Turno | `prepare_turn`, `persist_turn`, `run_turn` (texto completo, sin UI) |
| Propuestas | `apply_proposal`, `apply_proposal_with_fallback`, `apply_character_snapshot`, `compose_postprocessing_proposal`, `extract_proposal`, `clean_narrative` |
| Mundo | `evaluate_causality`, `apply_world_advances`, `record_event`, `world_status`, `create_world_agent` |
| Sistema | `detect_system`, `system_data`, `character_sheet_schema`, `resolve_roll` |
| Consultas UI | `vault_path`, `vault_template_path`, `live_vault_updates`, `sessions_dir`, `clocks_summary`, `fronts_with_clocks`, `scenes_status` |
| Mantenimiento | `reset_session_pacing`, `invalidate_retrieval_cache`, `create_extractor` |

`narrator_agent` y `rule_arbiter` se exponen como colaboradores de solo lectura para
el postprocesado de texto en la GUI de escritorio.
