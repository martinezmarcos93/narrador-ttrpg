# Handoff — 2026-10-05 — Reinicio, visibilidad y cross-front

## Rama
- feat/retrieval-evaluation
- No mergeado a main.
- No se ejecutaron pruebas locales.

## Cerrado en esta pasada

### Persistencia / reinicio
- StateManager.load() ahora hace merge recursivo de defaults.
- Un estado YAML antiguo no destruye subestructuras nuevas al recargar.
- Regresiones preparadas para conservar relaciones, consecuencias y conocimiento por perspectiva tras reinicio.
- Persistencia de relojes cross-front verificada por escenario preparado.

### Visibilidad
- El contexto neutral de StateManager dejó de exponer hechos legacy de `hechos_conocidos`.
- KnowledgeVisibility continúa siendo la puerta explícita para conocimiento de personaje/jugador.
- Recall por mención sigue pasando por KnowledgeRouter.
- El helper duplicado de campaña visible fue eliminado.

### Cross-front
- `front_clock_delta` puede emitir `frente <nombre> lleno` al cruzar el umbral.
- Ese evento puede disparar otra consecuencia causal.
- Regresión preparada: Culto llena su reloj y dispara una consecuencia que avanza Guardia.
- Se conservan métricas y provenance de la cascada.

### Writers / background
- Revisado VaultWriter y el camino background de app.py.
- VaultWriter registra narración player-facing y actualiza notas narrativas; no debe convertirse en segundo ejecutor de propuestas.
- Creación estructurada de NPC/locación continúa centralizada en ProposalExecutor.
- Pendiente: endurecer coordinación/errores de writers background si se busca garantía de entrega.

## Próximo bloque
1. Auditar exhaustivamente todos los puntos Core → Service → UI y accesos de escritura.
2. Completar cross-front con estados ya llenos, decrementos, múltiples umbrales y prioridades.
3. Añadir recuperación ante escritura de vault fallida sin afectar el estado transaccional.
4. Completar ground truth específico de System Packs desde el inventario real.
5. Preparar campaña real y luego benchmark LOCAL cuando Marcos autorice pruebas.

## Restricciones
No local tests, no benchmark real, no pull, no Ollama, no merge.


## Cierre de pasada — 2026-10-05
- Branch: feat/retrieval-evaluation.
- No merge a main. Compare verificado: 122 ahead / 2 behind / 42 archivos.
- Writer boundary endurecida: `on_narrator_response_safe()` aísla log de sesión, evento, notas de NPC y notas de locación; un fallo no aborta las demás salidas.
- UI → Core endurecido para avances de World Agent: `NarratorService.apply_world_advances()` centraliza mutaciones de frentes/relojes y WorldSimulation.
- Cross-front endurecido: `front_clock_delta` solo emite `frente <nombre> lleno` al cruzar el umbral; no re-dispara si ya estaba lleno y los decrementos quedan acotados a cero.
- Ground truth verificado contra los packs presentes en `data/systems`: VTM V20, D&D 5e, Cthulhu 7e, Pathfinder 2e y generic. Añadidos casos específicos para Cthulhu y Pathfinder.
- Tests nuevos preparados, no ejecutados: aislamiento del VaultWriter y cruce de umbral de front clock.
- LOCAL PENDIENTE: ejecución real de suite, benchmark, carga de campaña/manuales y E2E.
- Siguiente bloque: cerrar interfaces públicas restantes Core/Service/UI, campaña real + manuales, benchmark local y endurecimiento final de seguridad/API antes de Release Candidate.
