# ROADMAP MAESTRO — Narrador TTRPG
## Estado consolidado al 2026-10-05

> Fuente de verdad de planificación.
>
> Este documento consolida el roadmap histórico, la arquitectura actualmente implementada y todos los pendientes conocidos.
> Los ADR documentan decisiones arquitectónicas; los handoffs documentan el estado de una sesión.
> Si existe una contradicción, este roadmap define el orden de trabajo y el handoff más reciente define el estado operativo inmediato.

## 0. Reglas permanentes de trabajo

### 0.1 Orden de complejidad
Cada pasada debe comenzar por la solución más sencilla que desbloquee valor y avanzar progresivamente hacia la más compleja.

Orden general: contrato/modelo de datos → lógica determinista aislada → integración entre componentes → persistencia → LLM → campaña real → interfaz/API → optimización → E2E/release.

### 0.2 Máxima cobertura por pasada
Una pasada debe cubrir la mayor cantidad posible de integraciones relacionadas sin sacrificar claridad arquitectónica. La unidad preferida es un vertical slice progresivo: componente sencillo → integración → persistencia → siguiente integración → escenario/regresión.

### 0.3 No bloquear por pruebas locales
Todo trabajo que pueda realizarse mediante código, tests, fixtures, documentación, contratos, validadores, benchmarks preparados o refactors seguros debe realizarse sin esperar una prueba local. Todo lo que requiera explícitamente el entorno local queda marcado como LOCAL PENDIENTE. No ejecutar pruebas locales hasta autorización expresa del usuario.

### 0.4 Autoridad del motor
Python determina la verdad; el LLM interpreta, propone y narra. Python controla reglas, dados, cálculos, restricciones, estado canónico, causalidad, persistencia, validación, continuidad y permisos de conocimiento. El LLM no es autoridad mecánica ni propietario del estado persistente.

### 0.5 Cerebro y manuales
El cerebro universal contiene conceptos generales de TTRPG. La biblioteca documental/manuales conserva reglas específicas, ediciones, excepciones, lore, razas, clases, clanes, creación de personajes y contenido propio de cada sistema. Los manuales/PDF siguen siendo fundamentales.

Precedencia: STATE > MANUAL > SYSTEM PACK > UNIVERSAL BRAIN > conocimiento general del LLM.

## 1. Estado actual

### 1.1 Ya implementado
- Desktop app con Dear PyGui.
- NarratorService como fachada UI-independiente.
- Orchestrator, NarratorAgent y RuleArbiter determinista.
- StateManager, VaultWriter, CausalityEngine, ContinuityValidator.
- NarrativeProposal y ProposalExecutor.
- KnowledgeVisibility y KnowledgeRouter.
- Context Contract y System Pack.
- Cerebro universal e índice persistente.
- Recuperación híbrida semántica + léxica y expansión de grafo.
- Provenance y métricas operativas de retrieval.
- Evaluador offline, ground truth inicial y benchmark.
- Rollback compensatorio, persistencia en batch y rollback de entidades.
- Relaciones sociales, facciones, fronts y conocimiento por perspectiva.
- Cadenas causales deterministas.
- ADR y handoff del núcleo.

### 1.2 Rama actual
feat/retrieval-evaluation. Está 101 commits por delante de main y 1 por detrás; main avanzó externamente y no se realizó rebase. El último commit pertenece a la pasada de consolidación de continuidad/causalidad del 2026-10-05. No mergear sin autorización expresa.

## 2. FASE A — Consolidación del núcleo

### A1. Contratos y arquitectura
- HECHO: Turn Contract.
- HECHO: System Pack contract.
- HECHO: Context Contract.
- HECHO: NarrativeProposal contract.
- HECHO: Knowledge Router.
- HECHO: Service Boundary inicial.
- HECHO: NarratorService reutiliza el NarratorAgent del Orchestrator.
- HECHO: UI usa NarratorService para detección de sistema, eventos, preparación de turno, propuestas y persistencia del contrato.
- PARCIAL: quedan accesos internos de UI necesarios para compatibilidad/estado visual y deben aislarse en una pasada posterior.
- PENDIENTE: formalizar interfaces públicas Core/Service/UI.
- PENDIENTE: formalizar interfaces públicas Core/Service/UI.

### A2. Estado y transacciones
- HECHO: StateManager, persistencia, batch, snapshots y rollback.
- HECHO: rollback de entidades externas y creación parcial.
- HECHO: API pública rollback_batch().
- HECHO: ProposalExecutor utiliza la frontera pública de rollback.
- HECHO: escenario básico de rollback de batch.
- HECHO: frontera pública de batch expuesta mediante `batch_depth`.
- HECHO: ProposalExecutor respeta un batch externo sin cerrar la transacción del llamador.
- HECHO: escenarios de fallo en creación parcial de entidades y mutación de personaje.
- HECHO: regresión de fallo dentro de `StateManager.apply_proposal()` con rollback de estado y entidades.
- HECHO: persistencia de estado mediante escritura temporal + `fsync` + reemplazo atómico.
- HECHO: regresión que garantiza que un fallo de reemplazo conserva el archivo anterior.
- HECHO: contrato de turno conserva cambios de propuesta, errores de validación y provenance sin perder deltas causales.
- HECHO: escritura temporal + fsync + replace atómico.
- HECHO: regresión de fallo de replace conserva el archivo anterior y elimina temporales.
- HECHO: regresión de fallo de serialización conserva el archivo anterior y limpia temporales.
- HECHO: recuperación de estado corrupto mediante cuarentena/backup antes de continuar.

### A3. Continuidad
- HECHO: conflictos de facts, eventos duplicados y regresión temporal.
- HECHO: validación de clocks inexistentes, deltas no enteros y límites 0..segmentos.
- HECHO: referencias de NPCs y locaciones conocidas, entidades creadas dentro de la misma propuesta y duplicados internos.
- HECHO: relaciones, fuerza -100..100, entidades de relación y fronts declarativos.
- HECHO: estructura de consecuencias, triggers/due, efectos permitidos y referencias causales.
- HECHO: acumulación de múltiples cambios sobre un mismo clock dentro de una propuesta.
- HECHO: ejecución determinista de todos los efectos causales declarados por contrato.
- PENDIENTE: registro global formal de entidades del campaign vault para validar NPCs/locaciones existentes fuera del estado vivo.
- PENDIENTE: agregación de clocks/fronts entre múltiples consecuencias antes de activarlas.
- PENDIENTE: validaciones de incompatibilidades de dominio específicas de cada System Pack.

## 3. FASE B — Cerebro + biblioteca documental

### B1. Cerebro universal
- HECHO: mapa y conceptos de investigación, fallo, consecuencias, estado, continuidad, conflicto social, incertidumbre, conocimiento, escenas, contexto y causalidad.
- PENDIENTE: auditoría de cobertura conceptual.
- PENDIENTE: detección de huecos conceptuales.
- PENDIENTE: normalización definitiva de IDs.

### B2. Retrieval
- HECHO: índice, embeddings, búsqueda semántica/léxica, filtros, grafo, reranking, deduplicación, métricas, evaluador y benchmark.
- HECHO: IDs iniciales verificados contra el cerebro universal.
- HECHO: ground truth ampliado con agencia, frentes, conocimiento, combate y causalidad.
- HECHO: casos ambiguos y multi-capa añadidos al ground truth.
- HECHO: casos específicos por sistema añadidos para V20 y D&D.
- LOCAL PENDIENTE: validar resultados reales contra esos casos.
- PENDIENTE: benchmark sobre manuales y campaña.
- LOCAL PENDIENTE: ejecutar benchmark real.
- LOCAL PENDIENTE: ajustar pesos según resultados reales.

### B3. Manuales
- HECHO: manual como ContextFragment, layer manual y provenance.
- PENDIENTE: pipeline PDF → conocimiento formal.
- PENDIENTE: identificar sistema/edición y asociar manual ↔ System Pack.
- PARCIAL: precedencia de ContextFragment implementada como STATE > MANUAL > SYSTEM > CAMPAIGN > UNIVERSAL y cubierta por regresión.
- PENDIENTE: precedencia formal, excepciones y retrieval específico de manuales.
- PENDIENTE: evaluación de citas/provenance.
- PENDIENTE: protección ante prompt injection en documentos.

## 4. FASE C — Motor de turno completo
Objetivo: input → interpretation → intent → rule_need → retrieval → resolution → state_update → context_selection → narrative_prompt → LLM → post_process → persist.

- HECHO: Turn Contract y RuleArbiter.
- PENDIENTE: clasificador formal de intención y detección de acciones mecánicas, lore, investigación y social.
- PENDIENTE: primitivas mecánicas adicionales por System Pack.
- HECHO: RuleArbiter y TurnContract están integrados en el flujo principal de UI.
- HECHO: cardinalidad de dados incompatible con una mecánica de tirada única se rechaza.
- HECHO: salidas estructuradas de personaje y entidades pasan por NarratorService/ProposalExecutor en lugar de mutar directamente el estado.
- HECHO: postprocesado LLM convergido en una única propuesta compuesta por turno.
- HECHO: JSON legacy, [state:], propuesta narrativa y entidades se deduplican antes de ejecutar.
- HECHO: auditoría del postprocesado no encontró otro bypass de personaje/entidades en app/orchestrator.
- HECHO: propuesta inválida degrada explícitamente a narración-only y se registra en TurnContract.
- PENDIENTE: auditoría de writers/background persistence fuera del postprocesado.
- HECHO: resultado de propuesta y persistencia del contrato atraviesan NarratorService.

## 5. FASE D — Causalidad y mundo dinámico
- HECHO: CausalityEngine, cascadas acotadas, eventos, facts, relaciones, consecuencias, clocks, métricas y provenance.
- HECHO: escenarios compuestos de investigación, combate, conflicto social y fronts/relojes.
- HECHO: relaciones sociales forman parte del NarrativeProposal y persisten por StateManager.
- HECHO: límite de profundidad configurable y métrica `depth_limit_reached`.
- HECHO: regresiones de cadena larga y ciclo causal.
- HECHO: múltiples consecuencias en una cascada.
- HECHO: `front_clock_delta` valida reloj existente y límites acumulados.
- PENDIENTE: interacción cross-front entre múltiples relojes en campaña real.
- HECHO: contratos de facciones/fronts.
- PENDIENTE: reglas de avance, umbrales, interacción entre fronts y campaña real.
- HECHO: grafo social.
- PENDIENTE: tipos de relación, evolución temporal, consecuencias sociales e integración completa con NPC context.

## 6. FASE E — Visibilidad y conocimiento
- HECHO: world/character/player knowledge y KnowledgeVisibility.
- PENDIENTE: secretos de NPC/facción/localización, conocimiento parcial y descubrimiento gradual.
- PARCIAL: KnowledgeVisibility está integrada en el contexto narrativo.
- HECHO: KnowledgeRouter filtra documentos de campaña con `llm_visible=false` y visibilidad `secret/private/dm/hidden` (incluidas variantes en español).
- HECHO: regresiones de secreto no visible y precedencia STATE > MANUAL > SYSTEM/CAMPAIGN > UNIVERSAL.
- HECHO: recall por mención deja de saltarse KnowledgeRouter.
- HECHO: entidades restringidas no entran al conjunto de nombres recuperables por mención.
- HECHO: regresión router → prompt garantiza que un secreto excluido no llega al prompt final.
- PENDIENTE: fuga E2E completa con estado/perspectiva/campaña real.

## 7. FASE F — System Packs
Prioridad: Vampiro V20 → Hombre Lobo → Cthulhu → D&D → otros → Pathfinder.

Para cada sistema faltan, según corresponda: edición, vocabulario, character schema, resolución, lorebook, knowledge policy, brain mapping, manual mapping, reglas específicas, excepciones, ejemplos, casos de retrieval y regresión.

No ampliar sistemas hasta estabilizar el contrato del pack.

## 8. FASE G — Campaña real
PENDIENTE: campaign manifest, personajes, NPCs, locations, factions, fronts, secretos, relaciones, escenas, eventos, sesiones y manuales.
PENDIENTE: cargar campaña real, System Pack, manuales, estado inicial, índice, jugar turnos, persistir, continuar, activar consecuencias y comprobar visibilidad.

## 9. FASE H — Suite de regresión TTRPG
Construir escenarios compuestos, no solamente tests unitarios:
- investigación éxito;
- investigación fallo + consecuencia;
- consecuencia activada en turno posterior;
- conflicto social + cambio de relación;
- combate + daño + modificación de personaje;
- faction/front;
- secreto no visible;
- propuesta inválida;
- rollback;
- precedencia manual/system/universal;
- continuidad temporal;
- cadena causal;
- múltiples consecuencias;
- creación de entidades;
- fallo durante creación;
- recuperación tras reinicio.

## 10. FASE I — Evaluación real
PENDIENTE: dataset de queries, ground truth amplio, precision@k, recall@k, MRR, nDCG, layer coverage, provenance coverage y evaluación por sistema/tipo de consulta.
PENDIENTE: scenario pass rate, state correctness, causal correctness, knowledge leakage, proposal validity y rollback correctness.
Todo lo que dependa del entorno local queda LOCAL PENDIENTE.

## 11. FASE J — Optimización
Solo después de medir correctness: embeddings, retrieval, reranking, context budget, índice, memoria, persistencia, cascadas, modelo local, cuantización, caching y latencia E2E.

## 12. FASE K — Flask/API
Después del núcleo estable. Arquitectura objetivo: Desktop UI y Flask API → NarratorService → Core.
PENDIENTE: API de turnos, estado, personajes, campaña, retrieval, propuestas, serialización, errores, sesiones, configuración, autenticación y autorización.
Flask no contiene lógica de juego.

## 13. FASE L — Seguridad
PENDIENTE: input validation, path traversal, acceso a archivos, límites, JSON malicioso, prompt injection desde PDFs/vault/LLM, sandboxing, permisos de herramientas, autenticación, autorización y aislamiento de campañas.

## 14. FASE M — UI final
No es prioridad hasta estabilizar el motor. PENDIENTE: estado, tiradas, contexto, consecuencias, relaciones, fronts, logs, errores, configuración, campaña y manuales.

## 15. FASE N — Release Candidate
PENDIENTE: arquitectura/contratos congelados, retrieval medido, System Packs, manuales, campaña real, LLM, causalidad, persistencia, rollback, knowledge visibility, regression suite, seguridad, performance, documentación, instalación limpia, backup/recuperación y E2E.

## 16. Prioridad
### P0
1. Consolidar Service Boundary.
2. Endurecer rollback.
3. Suite de escenarios TTRPG.
4. Alinear ground truth.
5. Retrieval real.
6. Turn end-to-end.
7. ContinuityValidator.
8. KnowledgeVisibility integrada.
9. Precedencia manual/system/universal.
10. Campaña real.

### P1
System Packs, causalidad avanzada, fronts, relaciones, evaluación E2E, seguridad y optimización.

### P2
Flask/API, UI avanzada e integraciones externas.

## 17. Orden operativo de cada pasada
1. Contrato/modelo más sencillo.
2. Lógica determinista.
3. Integración inmediata.
4. Persistencia.
5. Integración con el siguiente subsistema.
6. Escenario de regresión.
7. Documentación.

Cada pasada debe intentar cerrar el mayor número posible de puntos relacionados, avanzando de menor a mayor complejidad.

## 18. Documentación
Este archivo es la fuente de verdad de planificación.
Los ADR documentan decisiones arquitectónicas permanentes.
Los handoffs documentan el estado operativo de cada sesión.
Los tests documentan contratos ejecutables.
Los datasets de ground truth documentan qué significa retrieval correcto.

## 19. Regla para futuros chats
Al iniciar un nuevo chat de desarrollo se debe recuperar este roadmap, el handoff más reciente, los ADR relacionados y el estado de la rama.
Después se identifica el siguiente bloque P0, se empieza por lo más sencillo, se avanza hacia lo complejo, se integran tantos subsistemas relacionados como sea seguro, no se ejecutan pruebas locales y no se mergea sin autorización.

## 20. Definición de terminado
Una funcionalidad no se considera terminada simplemente porque existe código. Debe tener, según corresponda: contrato, implementación, integración, persistencia, validación, escenario de regresión, documentación y prueba local cuando sea necesaria.

## Principio final
El objetivo no es construir un chatbot que improvise partidas. Es construir un motor TTRPG determinista y persistente donde el cerebro aporta conocimiento general, los manuales reglas específicas, el System Pack define el sistema, retrieval selecciona evidencia, Python determina las reglas, el estado conserva la verdad, causalidad mueve el mundo, visibilidad controla quién sabe qué y el LLM interpreta y narra.