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
