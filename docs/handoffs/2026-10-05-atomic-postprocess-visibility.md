# Handoff — 2026-10-05 — propuesta post-LLM + visibilidad

## Rama
- `feat/retrieval-evaluation`
- Base: `main`
- Estado al cierre: 76 commits ahead, 0 behind.
- No merge realizado.

## Trabajo cerrado en esta pasada

### 1. Postprocesado LLM atómico
Se eliminó la ejecución separada de:
- `narrative_proposal`
- mutaciones `[state:]`
- JSON legacy de personaje
- entidades `[[NUEVO_NPC]]` / `[[NUEVA_LOCACION]]`

Ahora `NarratorService.compose_postprocessing_proposal()` compone una única propuesta antes de llamar a `apply_proposal()`.

Reglas:
1. `narrative_proposal.character_changes` tiene precedencia.
2. Si no existe, se usan mutaciones legacy.
3. Si tampoco existen, el JSON legacy de personaje se convierte a `character_changes`.
4. Entidades legacy se agregan a la propuesta solo cuando VaultWriter está activo.
5. Entidades duplicadas por tipo + nombre no se agregan dos veces.
6. Se preserva el formato legacy `locacion`.

Esto evita múltiples transacciones para una misma respuesta del LLM.

### 2. Barrera de visibilidad
`KnowledgeRouter._campaign_fragments()` ahora descarta documentos de campaña cuando:
- `llm_visible == false`
- `visibility/visibilidad` es `secret`, `private`, `dm`, `hidden`, `oculto`, `secreto` o `privado`.

La capa campaign mantiene su presupuesto y sigue intentando obtener fragmentos visibles.

### 3. Regresiones preparadas
Se agregaron pruebas para:
- precedencia de propuesta estructurada sobre JSON/mutación legacy;
- deduplicación de NPCs y combinación de locaciones;
- conversión del JSON legacy a cambios;
- fuga de conocimiento de campaña restringido.

No se ejecutaron tests locales.

## Pendiente inmediato

### P0 — siguiente bloque
1. Revisar el contrato de fallback cuando una propuesta compuesta es inválida.
2. Añadir escenarios compuestos de investigación, combate, conflicto social, causalidad, fronts y secreto no visible.
3. Expandir ground truth ambiguo/multi-capa y específico por sistema.
4. Auditar precedencia de manual/System Pack/universal en casos con conflicto real.
5. Endurecer fallos de persistencia después de una propuesta compuesta.
6. Revisar otros caminos legacy fuera de `finish_streaming()`.

## Restricciones operativas
- No ejecutar pruebas locales.
- No ejecutar Ollama.
- No ejecutar benchmark real.
- No hacer pull/copia local.
- No mergear a `main` sin autorización expresa.

## Principio de continuación
Seguir de lo más sencillo a lo más complejo y cubrir el mayor número posible de integraciones relacionadas en cada pasada:
contrato → lógica determinista → integración → persistencia → escenario/regresión → documentación.
