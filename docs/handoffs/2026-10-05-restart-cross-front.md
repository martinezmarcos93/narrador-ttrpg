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
