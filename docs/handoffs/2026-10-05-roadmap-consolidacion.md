# Handoff — 2026-10-05 — Roadmap maestro y primera pasada incremental

## Decisión de planificación

Se establece docs/ROADMAP-MAESTRO-2026-10-05.md como fuente de verdad de planificación.

Regla permanente para futuras pasadas:

1. comenzar por lo más sencillo;
2. avanzar progresivamente hacia lo complejo;
3. integrar tantos subsistemas relacionados como sea seguro;
4. dejar preparado el máximo valor posible sin depender de pruebas locales;
5. no ejecutar pruebas locales hasta autorización;
6. no mergear sin autorización.

La arquitectura mantiene la separación:

STATE > MANUAL > SYSTEM PACK > UNIVERSAL BRAIN > conocimiento general del LLM.

El cerebro universal y los manuales/PDF son complementarios y ambos permanecen.

## Primera pasada después del roadmap

Se trabajó sobre el bloque más simple que podía conectar varias capas sin introducir Flask ni depender de Ollama.

### Cambios implementados

- StateManager:
  - nueva API pública rollback_batch();
  - elimina la necesidad de manipular directamente la intención de persistencia desde ProposalExecutor.

- ProposalExecutor:
  - rollback transaccional utiliza la API pública del StateManager;
  - conserva restauración de memoria y persistencia compensatoria.

- NarratorService:
  - reutiliza el NarratorAgent perteneciente al Orchestrator;
  - elimina una instancia duplicada del agente.

- Regression scenarios:
  - investigación fallida → consecuencia pendiente → siguiente turno → activación causal;
  - conflicto social → relación → visibilidad separada;
  - RuleArbiter → resolución determinista antes de narración;
  - propuesta inválida → cero mutación;
  - causalidad → relación + front clock + world fact.

### Ground truth

Se verificaron los IDs de las neuronas universales usados por el benchmark actual. Los identificadores del ground truth inicial coinciden con el frontmatter real de las neuronas relevantes.

No se modificó el ground truth porque no había una discrepancia que corregir.

## No ejecutado

- tests locales;
- benchmark real;
- embeddings;
- Ollama;
- campaña real;
- LLM E2E.

Esto es deliberado por la restricción vigente.

## Próxima prioridad

Continuar con la misma regla:

1. ampliar la suite sintética;
2. integrar retrieval en los escenarios;
3. añadir precedencia manual/system/universal;
4. completar ContinuityValidator;
5. avanzar hacia campaña real;
6. dejar benchmark real y optimización para cuando se habiliten pruebas locales.

No saltar todavía a Flask.


## Pasada siguiente — retrieval por capas + continuidad

Se añadieron contratos de regresión para:

- composición manual + system + universal + campaign;
- precedencia por autoridad de ContextFragment;
- validación de clocks inexistentes;
- validación de delta no entero;
- validación de overflow/underflow de clocks;
- puente ProposalValidator → ContinuityValidator para clock_changes.

La integración usa stubs deterministas en tests, no embeddings ni LLM.

## Restricción

No se ejecutaron tests locales ni benchmark real.

## Próximo bloque

- conectar escenarios a retrieval real cuando se habilite ejecución local;
- ampliar ContinuityValidator a entidades, relaciones y consecuencias;
- completar turn end-to-end sin depender de LLM real;
- avanzar hacia campaña real.
