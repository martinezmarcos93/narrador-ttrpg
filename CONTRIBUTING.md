# Guía de Contribución — Narrador TTRPG

## Reglas generales

- La rama `main` está protegida. Solo el mantenedor del proyecto puede mergear directamente.
- Todo cambio debe ir en una rama propia y entrar por Pull Request.
- Cada PR debe tener una descripción clara de qué cambia y por qué.
- No se aceptan PRs que rompan los imports o que no pasen una verificación manual básica (`python -c "from narrator.agents.orchestrator import Orchestrator"`).

## Flujo de trabajo

```
main (protegido)
 └── feat/nombre-de-la-feature    ← abrís acá
 └── fix/nombre-del-bug
 └── docs/lo-que-sea
```

1. Forkear o crear rama desde `main`.
2. Trabajar en la rama.
3. Abrir PR contra `main` con descripción y contexto.
4. El mantenedor revisa y mergea.

## Convenciones de commits

Usamos prefijos estándar:

| Prefijo | Cuándo usarlo |
|---------|---------------|
| `feat:` | Nueva funcionalidad |
| `fix:` | Corrección de bug |
| `docs:` | Solo documentación |
| `refactor:` | Cambio sin nueva feature ni fix |
| `test:` | Tests, sin cambio en código de producción |
| `chore:` | Tareas de mantenimiento (deps, CI, etc.) |

Ejemplo: `feat(theory_engine): integrar PacingToneAgent al orquestador`

## Estructura del proyecto

```
narrator/
  agents/       ← agentes de alto nivel (Orchestrator, NarratorAgent, etc.)
  core/         ← infraestructura reutilizable (LLM, Vault, State, PromptBuilder)
    theory_engine/  ← agentes de teoría rolera universal (agnósticos al sistema)
```

- No agregues lógica de negocio en `core/`. `core/` es infraestructura.
- Los agentes de teoría viven en `core/theory_engine/` y deben ser agnósticos al sistema de juego.
- Los YAMLs de sistemas (`data/systems/`) son configuración, no código. Cambios ahí no requieren PR si son adiciones puras.

## Archivos que NO se commitean

```
vault/                   # contenido personal de campaña
estado_campana.yaml      # estado de partida en curso
world_state.json         # estado persistente del WorldSimulationEngine
investigation_state.json # estado persistente del InvestigationEngine
*.pyc / __pycache__/
.env
```

## Licencia

Al contribuir aceptás que tu código se distribuye bajo la licencia MIT incluida en este repositorio.
