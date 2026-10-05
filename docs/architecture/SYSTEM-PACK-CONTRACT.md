# Contrato de System Pack

Un System Pack describe un sistema de rol sin obligar al código del narrador a
conocer sus nombres concretos.

## Campos mínimos

- slug: identificador estable.
- sistema: nombre visible.
- edition: edición.
- vocabulario: terminología del sistema.
- character_sheet_schema: estructura de ficha.
- resolution: resolución mecánica declarativa.
- lorebook: contexto corto y explícito.
- knowledge: filtros de recuperación.
- llm_system_prompt: instrucciones narrativas.

## Knowledge

El bloque knowledge define cómo buscar material específico:

    knowledge:
      brain_system: vtm_v20
      preferred_sources:
        - manual
        - system
      universal_fallback: true

El código puede leer este contrato sin importar si el sistema es Vampiro,
Cthulhu, Hombre Lobo o uno futuro.


## Knowledge Router

La política `knowledge` es ejecutable mediante `narrator/core/knowledge_router.py`.

El flujo es:

`SystemPack` → `KnowledgeRouter` → fuentes habilitadas → `ContextFragment` → `render_context()`.

`preferred_sources` controla las fuentes consultadas. No es una instrucción decorativa para el LLM.

- `manual`: texto del manual/PDF adjunto a la sesión.
- `system`: neuronas específicas del sistema.
- `campaign`: contenido mutable del vault de campaña.
- `state`: contenido clasificado como estado.
- `universal`: neuronas generales del cerebro.

Si `universal_fallback` está activo, la capa universal se incorpora aunque no figure explícitamente en `preferred_sources`.

La autoridad narrativa continúa siendo independiente del orden de consulta:
`STATE > MANUAL > SYSTEM > CAMPAIGN > UNIVERSAL`.

Esto permite consultar varias fuentes sin permitir que conocimiento general desplace una regla específica.
