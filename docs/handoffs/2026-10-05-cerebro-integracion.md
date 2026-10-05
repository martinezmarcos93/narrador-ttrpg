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


### Barrido siguiente — ejecución segura de propuestas

Se implementó el primer ciclo real de propuestas:
- `NarrativeProposal`: contrato cerrado para hechos, eventos, NPCs, consecuencias, cambios de personaje, escena y relojes.
- `ProposalValidator`: valida forma y continuidad antes de aplicar.
- `ProposalExecutor`: único ejecutor Python; una propuesta inválida no muta estado.
- `StateManager.apply_proposal()`: aplica cambios de campaña y persiste.
- Cambios de personaje procedentes de etiquetas `[state: ...]` ahora pasan por `ProposalExecutor` y el schema activo antes de mutar.
- `Orchestrator.validate_and_apply_proposal()`: punto de entrada único para futuras propuestas estructuradas del LLM.
- Se exige schema válido para aceptar cambios de campos de personaje.
- Tests agregados para rechazo, aplicación y límites de propuestas.

El sistema todavía no interpreta automáticamente la respuesta narrativa libre como una `NarrativeProposal`; la extracción estructurada sigue siendo el siguiente paso deliberado.


### Integración de propuestas estructuradas

Se añadió un protocolo opcional `json-proposal` al prompt del narrador. `NarratorAgent` lo extrae y elimina del texto visible. `app.py` lo envía al `Orchestrator.validate_and_apply_proposal()`. Si la propuesta falla validación, no se aplica. Si contiene `character_changes`, esas mutaciones pasan por el schema activo y no se aplican también por las etiquetas `[state: ...]`, evitando doble aplicación.

Los tests de extracción, sanitización y ejecución segura quedaron agregados. No se ejecutaron localmente.

### Barrido de entidades y causalidad — 2026-10-05

Se amplió el contrato json-proposal para soportar:
- npcs: NPCs nuevos confirmados por la ficción.
- locations: locaciones nuevas confirmadas por la ficción.
- npc_presence, consecuencias, relojes y cambios de escena continúan dentro del mismo contrato.

ProposalValidator rechaza NPCs o locaciones sin nombre. ProposalExecutor puede materializarlos mediante VaultWriter, manteniendo el vault como biblioteca persistente de entidades.

StateManager.apply_proposal() fue refactorizado para realizar las mutaciones de una propuesta en memoria y ejecutar una sola persistencia al final. Esto evita múltiples escrituras intermedias durante una misma propuesta.

Se añadió narrator/core/causality_engine.py:
- activa consecuencias por trigger textual explícito;
- activa consecuencias por sesión/turno lógico;
- activa consecuencias marcadas para el siguiente turno al comienzo del turno siguiente;
- registra la activación como evento persistente;
- no genera contenido ni interpreta narrativa libre.

Orchestrator expone evaluate_causality() y prepare_turn() activa las consecuencias de siguiente turno antes del retrieval, de modo que el estado causal ya forme parte del contexto que recibe el LLM.

Tests agregados:
- tests/test_causality_engine.py
- cobertura de entidades en tests/test_proposal_contract.py
- cobertura de ejecución de entidades en tests/test_proposal_executor.py

No se ejecutaron pruebas locales.

### Barrido de métricas de retrieval — 2026-10-05

RetrievalMetrics ahora registra latencia, media/máximo de relevancia, diversidad por capas, cobertura de procedencia y utilización del contexto, además de conteo de fragmentos, fuentes, capas y duplicados. Son métricas operativas/proxy; recall y precision reales requieren un conjunto de consultas con ground truth y no se inventan en runtime.

No se ejecutaron pruebas locales.

### Barrido de causalidad avanzada y desacoplamiento — 2026-10-05

La causalidad dejó de ser únicamente un activador de consecuencias. Las consecuencias ahora pueden declarar efectos deterministas permitidos sobre:
- hechos conocidos;
- flags;
- presencia de NPCs;
- locación de escena;
- relojes.

ProposalValidator valida el tipo y los campos mínimos de cada efecto. El motor no ejecuta tipos arbitrarios ni interpreta código o texto como instrucciones.

StateManager.apply_causal_activation() aplica los efectos declarativos y registra el evento causal. El LLM continúa limitado a proponer; la mutación efectiva sigue siendo Python.

Se añadió narrator/core/narrator_service.py como fachada independiente de la interfaz. Expone las operaciones de dominio que necesitarán tanto Dear PyGui como la futura Flask:
- preparar turno;
- aplicar propuesta;
- evaluar causalidad;
- detectar sistema;
- obtener contexto;
- extraer/limpiar propuesta narrativa;
- resolver tiradas.

Flask todavía no fue creado. La decisión sigue siendo construirlo sobre esta fachada cuando el núcleo sea estable, evitando trasladar lógica de juego a rutas HTTP.

No se ejecutaron pruebas locales.

## Barrido de conocimiento por perspectiva y causalidad encadenada — 2026-10-05

Se añadió una separación persistente entre tres perspectivas:
- `conocimiento.mundo`: verdad objetiva de campaña.
- `conocimiento.personajes.<nombre>`: hechos que conoce explícitamente un personaje.
- `conocimiento.jugador`: información que el jugador conoce explícitamente.

`KnowledgeVisibility` construye una vista para el narrador sin exponer automáticamente la verdad objetiva. El Orchestrator incorpora esta vista al contexto narrativo. Esto evita el fallo clásico de un narrador omnisciente que revela secretos solo porque existen en el estado.

La causalidad ahora admite cascadas acotadas. Una consecuencia puede emitir un `event`, y ese evento puede activar otra consecuencia. También puede plantar una nueva `queue_consequence`. La profundidad máxima está limitada a 8 por defecto para impedir ciclos infinitos.

Se añadieron efectos declarativos de conocimiento:
- `world_fact`
- `character_fact`
- `player_fact`

El contrato de propuestas y el PromptBuilder documentan y validan estos efectos junto con `event` y `queue_consequence`. No existe ejecución arbitraria de código desde propuestas.

Se agregaron tests para aislamiento de conocimiento, cadenas causales y límite de profundidad. No fueron ejecutados localmente.

### Pendiente inmediato

El siguiente bloque puede formalizar el grafo social y causal: relaciones NPC/facción, frentes como entidades causales, propagación de relojes y provenance completa desde efecto → evento → consecuencia → turno. Después conviene endurecer la atomicidad de ProposalExecutor y medir la utilización real del contexto por turno.


## Barrido de grafo social, frentes y provenance — 2026-10-05

El estado persistente ahora contiene:
- `relaciones`: grafo dirigido de relaciones entre NPCs, facciones u otras entidades, con tipo, fuerza, razón y sesión.
- `provenance`: cadena técnica de hasta 500 operaciones causales recientes.

El Orchestrator construye un subgrafo limitado a los NPCs presentes en la escena y lo incorpora al contexto narrativo. No se inyecta indiscriminadamente todo el grafo de campaña.

La causalidad admite:
- `relation`: crea/modifica una relación dirigida.
- `front_clock_delta`: modifica declarativamente un reloj de frente.
- `event`: genera un evento que puede disparar otra consecuencia.
- `queue_consequence`: planta una consecuencia posterior.
- `world_fact`, `character_fact`, `player_fact`: mantiene la separación de perspectivas.

Cada activación causal recibe un identificador de provenance. Las consecuencias encadenadas heredan ese identificador como `parent_id`, formando una cadena auditable efecto → activación → nueva consecuencia.

Se añadieron tests para el grafo social, filtrado del subgrafo, provenance y propagación causal hacia relaciones/relojes. No fueron ejecutados localmente.

### Siguiente endurecimiento

Queda como siguiente bloque la atomicidad real de `ProposalExecutor`: evitar estados parciales cuando participan simultáneamente estado de campaña, ficha de personaje y escritura en vault. También conviene añadir un contrato explícito de relaciones/facciones a los System Packs y métricas de profundidad/ramificación de las cascadas causales.


## Barrido de atomicidad, frentes formales y métricas causales — 2026-10-05

Se endureció ProposalExecutor para tratar cada propuesta como una operación transaccional compensatoria:
- captura snapshot profundo del estado de campaña;
- captura snapshot de la ficha del personaje cuando participa;
- registra exclusivamente las entidades creadas durante la operación;
- ante una excepción, restaura estado y personaje;
- elimina únicamente archivos de NPC/locación creados por esa ejecución;
- devuelve rolled_back=True, error técnico y una incidencia proposal_execution_failed.

VaultWriter.rollback_created_entities() nunca elimina entidades preexistentes; solo recibe las rutas que el propio executor obtuvo como resultado de creación en la transacción.

El modelo de frentes se formalizó sobre la estructura existente de relojes. StateManager mantiene frentes con nombre, facción, objetivo, estado, prioridad, descripción y referencia al reloj operativo. Los relojes existentes continúan siendo compatibles. get_active_fronts() ordena los frentes por prioridad y expone progreso llenos/segmentos para el contexto del turno.

ProposalValidator endureció efectos causales: fuerza de relaciones entre -100 y 100; front_clock_delta.delta debe ser entero.

CausalityEngine ahora expone métricas deterministas de cada cascada: cantidad de activaciones, profundidad máxima, distribución por motivo, provenance IDs y consecuencias pendientes restantes. Orchestrator.evaluate_causality() devuelve estas métricas junto con el resumen y la trazabilidad.

Tests agregados para rollback transaccional, frentes formales, métricas causales y límites de efectos. No se ejecutaron localmente.

### Estado de arquitectura

La frontera queda: LLM -> propuesta estructurada -> validación -> executor Python -> estado/vault/ficha.

La causalidad queda: estado pendiente -> activación determinista -> efectos declarativos -> provenance -> posibles eventos/causas posteriores.

Flask continúa diferido. No se agregó lógica de juego a la futura capa HTTP.

### Próximo bloque recomendado

1. Reducir escrituras redundantes durante cascadas causales mediante una sesión/batch de persistencia del StateManager.
2. Añadir contrato explícito de facciones y frentes para evitar que el LLM improvise identificadores incompatibles.
3. Integrar métricas causales en TurnContract.state_delta y en el registro técnico del turno.
4. Construir un pequeño conjunto de escenarios sintéticos para medir retrieval + causalidad + continuidad sin depender todavía de pruebas locales completas.


### Ajuste final de rollback

El rollback también contempla el caso en que el archivo de estado todavía no existía: si la propuesta falla antes de la primera persistencia, no deja un estado nuevo artificial. Además, el executor tolera implementaciones de VaultWriter que no expongan rollback, manteniendo compatibilidad con adaptadores/fakes existentes.


## Pasada de reducción de pendientes — persistencia, contratos y escenarios — 2026-10-05

Se cerró el bloque de persistencia batch:
- StateManager.begin_batch() / end_batch() permiten agrupar escrituras.
- save() queda diferido durante un batch.
- CausalityEngine.evaluate() ejecuta la cascada dentro de un batch y persiste una sola vez al finalizar.
- Los batches son anidables.

Se formalizó el contrato de System Pack para facciones/frentes:
- factions y fronts son estructuras declarativas opcionales.
- Los frentes pueden referenciar una facción declarada.
- validate_front_contract() detecta referencias incompatibles.
- front_definition() permite consultar la definición declarativa.

Se conectó ese contrato con las propuestas:
- el Orchestrator configura los frentes permitidos combinando System Pack + frentes de campaña;
- front_clock_delta contra un frente no declarado se rechaza cuando existe contrato activo.

Se amplió el estado de campaña con un registro de facciones: slug, nombre, descripción, agenda y estado, con consulta de facciones activas.

Se completó la telemetría de turno:
- TurnContract.causal_metrics;
- serialización de métricas;
- persistencia en StateManager.record_turn();
- prepare_turn() incorpora las métricas de causalidad al state_delta.

Se añadieron escenarios sintéticos deterministas que cubren: contexto por capas + cascada causal + continuidad; aislamiento de secretos entre mundo/personaje/jugador; rechazo de conflictos de continuidad antes de mutar estado.

No se ejecutaron pruebas locales.

### Pendientes que permanecen

El núcleo determinista ya tiene cubiertos retrieval, separación de conocimiento, resolución, continuidad, propuestas, causalidad, provenance, relaciones, facciones/frentes y trazabilidad de turno.

Quedan principalmente tareas de integración y endurecimiento de nivel superior:
- ampliar el conjunto de escenarios con retrieval real sobre el índice de cerebro;
- medir precision/recall con ground truth;
- optimización posterior del índice/modelo local;
- integrar de forma definitiva el flujo completo de respuesta LLM -> propuesta -> executor en todas las rutas de UI;
- Flask como capa final;
- pruebas locales y validación de extremo a extremo;
- integración posterior de configuración/entidades de campaña reales.


## Actualización posterior al merge — evaluación reproducible del retrieval

Se añadió una capa offline para medir la calidad del retrieval sin depender de la ejecución local del modelo de embeddings.

Componentes:
- narrator/core/retrieval_evaluator.py: ground truth + precision@k + recall@k + MRR + nDCG@k + cobertura de capas.
- narrator/core/retrieval_benchmark.py: adapta KnowledgeRouter al evaluador y extrae IDs/procedencia de los fragmentos reales.
- data/evaluation/retrieval_ground_truth.yaml: batería inicial de consultas universales, sin texto de manuales.
- tests/test_retrieval_evaluator.py y tests/test_retrieval_benchmark.py: cobertura matemática y de integración con router mediante fixture determinista.
- docs/adr/ADR-2026-10-05-evaluacion-retrieval.md: decisión arquitectónica y criterio de comparación.

Importante: todavía no se ejecutó el benchmark contra el índice real ni se informan métricas empíricas. Para eso hace falta disponer localmente del índice de neuronas y del modelo de embeddings. Los tests quedaron escritos para esa futura ejecución.
