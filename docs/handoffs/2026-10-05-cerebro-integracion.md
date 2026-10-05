# Handoff — 2026-10-05 — Integración del Cerebro

## Decisión consolidada

La arquitectura conserva dos fuentes de conocimiento:

- Cerebro rolistico permanente: conceptos universales y patrones reutilizables.
- Biblioteca documental: PDFs/documentos específicos de sistema y crónica.

El PDF no se elimina. Es precisamente la fuente para reglas especiales,
opciones concretas de personaje, excepciones, tablas, lore y tono específico.

## Implementado en esta rama

- Nueva rama: `feat/cerebro-integracion`.
- `IndiceCerebro`: índice persistente incremental de neuronas.
- Embeddings del cerebro configurables, por defecto `bge-m3`.
- `RecuperadorCerebro`: ranking híbrido semántico + léxico + filtro de
  sistema + expansión por enlaces Obsidian.
- Integración del cerebro en el `VaultRetriever` existente.
- El Orquestador consulta el cerebro durante el turno narrativo.
- El Orquestador consulta cerebro + manual durante creación de personajes.
- Prompt Builder distingue explícitamente cerebro universal de contexto del vault.
- Configuración de `cerebro.embedding_model`.
- 16 neuronas universales originales + un nodo índice.
- ADR que fija la separación cerebro/biblioteca.
- Tests unitarios sin dependencia de Ollama para indexación y grafo.
- Comando:
  `python -m narrator.cerebro.indexador --path cerebro --model bge-m3`.

## Próximo bloque

1. Mejorar la recuperación híbrida con pesos y filtros por capa.
2. Añadir un contrato de procedencia para cada fragmento recuperado:
   universal, sistema, manual, campaña o estado.
3. Integrar recuperación específica de manuales adjuntos sin degradar el
   contexto universal.
4. Crear el contrato de System Pack.
5. Separar definitivamente resolución mecánica, estado y narración.
6. Recién después comenzar la nueva shell Flask.

## No hacer todavía

- No eliminar la carga de PDF.
- No crear otro RAG.
- No pasar reglas al LLM para que las resuelva por cuenta propia.
- No iniciar Flask antes de estabilizar recuperación y contrato de turno.


## Bloque posterior — System Pack y routing efectivo

Se implementó el contrato ejecutable `narrator/core/system_pack.py`.

Cambios relevantes:
- Los cinco sistemas distribuidos declaran `knowledge`.
- `SystemPack.from_dict()` valida campos obligatorios y fuentes permitidas.
- `PromptBuilder.load_system()` valida el paquete al cargarlo.
- El prompt expone la política de conocimiento del sistema.
- Un `manual_text` adjunto entra al contexto como capa `MANUAL`, sin eliminar la biblioteca PDF/manual.
- Se corrigió `build_narrator_context()`: el RAG legado ya no sobrescribe el contexto híbrido cerebro + vault.
- El recall por mención de NPC/locación ahora complementa el contexto híbrido.
- La expansión por grafo del cerebro se reranquea antes del truncado final.
- Se agregaron pruebas del contrato para todos los System Packs distribuidos.

Precedencia operativa actual:
`STATE > MANUAL > SYSTEM > CAMPAIGN > UNIVERSAL`.

Esto es deliberado: el cerebro universal aporta conceptos generales; el manual/PDF sigue siendo la fuente específica para reglas, lore, excepciones y creación de personajes.

### Pendiente inmediato

1. Introducir un router de conocimiento explícito basado en `SystemPack.knowledge`, para que la preferencia de fuentes deje de ser solo metadata/prompt y gobierne la recuperación.
2. Incorporar procedencia documental más precisa (libro/página cuando el barrido del manual la conserve).
3. Formalizar el contrato de turno Python → resolución → estado → contexto → LLM, reutilizando los motores existentes.
4. Recién después endurecer Flask/UI.

Las pruebas nuevas están escritas pero no se han ejecutado en un entorno local durante esta iteración.


## Knowledge Router — implementado

Se añadió `narrator/core/knowledge_router.py`.

El router:
- lee `SystemPack.knowledge`;
- decide qué fuentes consultar;
- conserva la procedencia en `ContextFragment`;
- aplica fallback universal cuando corresponde;
- deduplica resultados antes del render;
- reutiliza el índice/RAG existente, sin crear un segundo sistema de recuperación.

El `Orchestrator` ahora instancia `KnowledgeRouter` y lo utiliza para construir el contexto narrativo.

También se añadió `VaultRetriever.get_vault_fragments_by_layer()` para recuperar específicamente campaña/estado sin mezclar capas.

Tests específicos:
- `tests/test_knowledge_router.py`
- `tests/test_system_pack.py`

No se ejecutaron localmente.


## Contrato formal de turno — implementado

Se añadió `narrator/core/turn_contract.py` con las etapas explícitas:

`input → interpretation → intent → rule_need → retrieval → resolution → state_update → context_selection → narrative_prompt → llm → post_process → persist`.

El contrato registra:
- entrada y sistema activo;
- interpretación e intención;
- necesidad de resolución;
- contexto recuperado y procedencia;
- snapshot del estado mutable;
- resolución mecánica calculada por Python;
- delta de estado;
- prompt narrativo;
- salida del LLM.

`Orchestrator.prepare_turn()` ejecuta las etapas Python hasta producir el prompt. No llama al LLM.

`narrator/app.py` utiliza ahora `prepare_turn()` para el flujo agente. La respuesta del LLM se registra como salida del contrato después del streaming.

Se corrigió además una inicialización inalcanzable: `KnowledgeRouter` estaba después de un `return` en `_load_config()`; ahora se inicializa en `Orchestrator.__init__()`.

### Estado mutable como capa autoritativa

Se añadió `StateManager.get_turn_context_text()` y el estado vivo entra al prompt como sección separada y autoritativa. Esto evita confundir una nota histórica recuperada del vault con el estado actual de la campaña.

### Cobertura

Nuevo test:
- `tests/test_turn_contract.py`

Los tests están escritos pero **no fueron ejecutados localmente**, de acuerdo con la restricción vigente de no realizar pruebas locales todavía.

### Siguiente bloque recomendado

1. Convertir las mutaciones de estado emitidas por el LLM en propuestas verificables por Python, evitando que el LLM sea autoridad de estado.
2. Hacer que `RuleArbiter` produzca una estructura de resolución tipada más rica (acción, atributo, dificultad, dados, total, veredicto, banda, procedencia de regla).
3. Persistir un `TurnContract` resumido en el log de sesión para trazabilidad/debug.
4. Completar métricas de retrieval y procedencia.
5. Recién después avanzar a Flask.


## Barridos posteriores — 2026-10-05

Se avanzó sin depender de manuales:

- Turn Contract: identidad única, timestamp, transiciones monotónicas, errores, cierre persistente y resumen técnico limitado a 200 turnos.
- Rule Arbiter: rechazo de resultados fuera de rango y dados incompatibles con la mecánica; trazabilidad de validación.
- Knowledge Router: estado vivo como fragmento autoritativo; recuperación universal desacoplada del slug del sistema; métricas de recuperación.
- Cerebro universal: nuevas neuronas sobre causalidad, información/conocimiento, transiciones, conflicto social, incertidumbre, estado ficción/mecánica, presupuesto de contexto y continuidad temporal.
- StateManager: eventos, consecuencias pendientes y hechos conocidos, expuestos en el contexto de turno.
- Continuidad: validador determinista para conflictos de hechos, eventos duplicados, presencia de NPCs y regresión temporal.
- Propuestas narrativas: contrato estructural separado de la aplicación de mutaciones; el LLM todavía no tiene permiso para mutar directamente el estado.

No se ejecutaron pruebas locales. Los tests correspondientes quedaron escritos para validación posterior.
