# HANDOFF — 2026-10-05 — Vertical Slice de Turno

Rama: `feat/retrieval-evaluation`.

No se hizo merge a `main`. No se ejecutaron pruebas locales, Ollama, benchmark real ni deployment.

## Trabajo realizado

- NarratorService ahora centraliza aplicación de propuestas y persistencia del contrato de turno.
- La UI dejó de llamar directamente a Orchestrator para esos dos pasos.
- TurnContract incorpora `record_proposal_result()`.
- Los cambios de propuesta se agregan a `state_delta` sin sobrescribir deltas causales.
- Se registra provenance de ProposalExecutor/ProposalValidator y errores de validación.
- Se agregaron regresiones para propuesta aceptada, propuesta rechazada y persistencia mediante NarratorService.

## Próximo bloque P0

1. Rollback compuesto con fallos en distintas etapas.
2. Escenarios TTRPG compuestos.
3. Auditoría transversal de RuleArbiter.
4. Integración definitiva de KnowledgeVisibility + retrieval + prompt.
5. Ground truth ambiguo, multi-capa y específico por sistema.
6. Benchmark de manual/campaña.
7. Campaña real y pruebas locales cuando Marcos las autorice.

Las pruebas agregadas no fueron ejecutadas. No mergear a `main` sin autorización expresa.
