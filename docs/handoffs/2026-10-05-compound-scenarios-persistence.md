# Handoff — 2026-10-05 — escenarios compuestos + persistencia

## Rama
- `feat/retrieval-evaluation`
- Sin merge a `main`.
- Tests preparados, no ejecutados localmente.

## Cerrado

### Persistencia
`StateManager._save_now()` usa:
1. archivo temporal en el mismo directorio;
2. escritura YAML;
3. flush;
4. `fsync`;
5. `os.replace()` atómico.

Un fallo durante el replace no destruye el archivo anterior y el temporal se limpia.

### Escenarios TTRPG
Se agregaron regresiones compuestas para:
- investigación fallida → consecuencia → activación en turno posterior;
- combate + cola de iniciativa;
- conflicto social + relación + evento;
- front + reloj + límite de segmentos;
- cadena causal con relación, front y world fact;
- propuesta compuesta con personaje + NPC + locación + consecuencia;
- conflicto de propuesta detectado antes de ejecución parcial;
- secreto de campaña excluido del retrieval;
- precedencia STATE > MANUAL > SYSTEM/CAMPAIGN > UNIVERSAL.

### Seguridad de conocimiento
La barrera de documentos de campaña restringidos permanece:
- `llm_visible=false`;
- `secret/private/dm/hidden`;
- equivalentes españoles.

## Pendiente P0

1. Pruebas E2E de fuga de conocimiento entre perspectiva, retrieval y prompt final.
2. Fallback determinista explícito cuando la propuesta estructurada es inválida.
3. Fallos de persistencia más agresivos: YAML serialización, permisos y recuperación posterior.
4. Cadenas causales largas, ciclos, múltiples consecuencias y cross-front.
5. Auditoría final de caminos legacy fuera del postprocesado principal.
6. Ground truth ambiguo, multi-capa y específico por System Pack.
7. Benchmark real queda LOCAL PENDIENTE.

## Restricciones
No ejecutar tests locales, Ollama, benchmark real, pull/copia local ni merge sin autorización expresa.
