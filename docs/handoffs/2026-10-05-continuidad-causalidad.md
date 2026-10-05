# Handoff — 2026-10-05 — Continuidad y causalidad

## Estado de la sesión

Rama: `feat/retrieval-evaluation`
Base: `main`
Merge a `main`: no autorizado / no realizado.
Pruebas locales: no ejecutadas.
Benchmark real de retrieval/Ollama: no ejecutado.

## Bloque completado

Se endureció la barrera determinista previa a la mutación del estado y se cerró una inconsistencia entre el contrato de efectos causales y su ejecución.

### ContinuityValidator

Ahora cubre:

- conflictos de facts;
- eventos duplicados como warning;
- regresión temporal;
- NPCs desconocidos y presencia inválida;
- NPCs creados en la misma propuesta;
- duplicados de entidades dentro de una propuesta;
- locaciones declaradas en la propuesta y referencias de escena cuando existe un registro conocido;
- clocks desconocidos;
- deltas inválidos;
- acumulación de múltiples cambios sobre un mismo clock;
- límites de clocks;
- relaciones y fuerza `-100..100`;
- entidades desconocidas en relaciones;
- estructura de consecuencias;
- trigger/due obligatorios;
- tipos de efectos causales;
- referencias de NPC/locación dentro de efectos;
- facts, flags, eventos, relaciones, character/player/world facts;
- queue_consequence;
- front_clock_delta y fronts inexistentes.

La validación mantiene la regla de no inventar una autoridad para entidades que el estado actual no registra globalmente.

### NarrativeProposal / ProposalValidator

Se endureció `NarrativeProposal.from_dict()` para no convertir silenciosamente estructuras inválidas.

Ahora rechaza:

- contenedores con tipo incorrecto;
- events que no sean strings;
- npc_presence cuyos valores no sean bool;
- listas con elementos que no sean objetos.

`ProposalValidator` ahora pasa NPCs, locaciones, consecuencias y scene_changes al ContinuityValidator.

### CausalityEngine

Se implementaron los efectos que ya estaban declarados por contrato pero que antes no tenían ejecución:

- `fact`
- `flag`
- `npc_presence`
- `scene_location`
- `clock_delta`

Los efectos previamente soportados continúan integrados:

- event
- world_fact
- character_fact
- player_fact
- relation
- front_clock_delta
- queue_consequence

La ejecución sigue siendo determinista, acotada por profundidad y dentro del batch de persistencia.

## Regresiones agregadas

Se agregaron escenarios para:

- acumulación de cambios de clock;
- NPC creado y referenciado en la misma propuesta;
- entidades de relación inexistentes;
- consecuencias sin trigger/due;
- efectos causales inválidos;
- tipos inválidos en NarrativeProposal;
- paso de entidades/consecuencias hacia ContinuityValidator;
- ejecución de primitivas de estado/escena mediante CausalityEngine.

## Limitaciones todavía abiertas

1. El estado no posee aún un registro canónico global de todos los NPCs/locaciones del campaign vault. Por eso ContinuityValidator valida con certeza las entidades presentes en estado, relaciones, escena o creadas en la misma propuesta, pero no puede demostrar la existencia de cualquier entidad externa del vault sin introducir ese registro.
2. Los `front_clock_delta` se validan contra su clock individual; todavía falta una agregación transversal de deltas provenientes de múltiples consecuencias que se activen juntas.
3. Las incompatibilidades semánticas específicas de cada System Pack todavía pertenecen a una capa posterior.
4. Service Boundary sigue parcialmente pendiente.
5. La regression suite completa todavía no fue ejecutada.
6. Retrieval real todavía no fue ejecutado.

## Siguiente bloque recomendado

Continuar desde P0, en este orden:

1. cerrar la consistencia transaccional con escenarios anidados/fallos por etapa;
2. construir un vertical slice TTRPG más completo que conecte retrieval + RuleArbiter + ProposalValidator + ProposalExecutor + CausalityEngine + KnowledgeVisibility + StateManager + provenance;
3. reforzar precedencia STATE > MANUAL > SYSTEM > CAMPAIGN > UNIVERSAL;
4. avanzar hacia una campaña mínima real;
5. dejar preparado el benchmark real sin ejecutarlo;
6. completar Service Boundary.

## Regla operativa

No ejecutar pruebas locales, benchmark real, deployment ni merge a main hasta autorización expresa.
