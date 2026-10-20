# Changelog

Todas las modificaciones relevantes de este proyecto se documentan acá.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-AR/1.1.0/);
versionado [semántico](https://semver.org/lang/es/).

## [Unreleased]

### Barrido 2026-10-19/20 (rama `claude/barrido-2026-10-19`)

#### Arreglado
- 28 tests en rojo; detrás había bugs reales: efectos causales propuestos que se
  descartaban, efectos de reloj aplicados dos veces, triggers por evento que nunca se
  activaban, estado guardado con tags Python ilegibles, lorebook desconectado.
- Retrieval: la capa universal quedaba vacía bajo las neuronas de manuales; búsqueda
  ~33 s → 0,1–0,5 s. API: rutas inexistentes daban 500.
- Disciplinas de clan Brujah y Malkavian en V20.

#### Añadido
- Frontera UI → NarratorService; registro de entidades del vault; reglas de
  continuidad por System Pack; agregación de relojes; frentes con umbrales,
  interacción y avance por sesión; dinámica social (niveles, historial, decaimiento).
- Secretos con descubrimiento gradual y detector de fugas; protección ante prompt
  injection; pasajes del manual con cita de página; reglas de la casa; identificación
  de sistema y edición del manual; pipeline de manuales; auditoría del cerebro.
- Pack Hombre Lobo W20; ficha V20 completa (ideas de planillas de Roll20);
  clasificador de intención; primitivas mecánicas (habilidad, heridas,
  especialidades, Fuerza de Voluntad, competencia, ventaja).
- Campañas declarativas con cargador validado y campaña de ejemplo; turno sin GUI
  (`run_turn`); partida IA contra IA con métricas; evaluación del motor (16 escenarios).
- API web: sesiones SQLite, claves multiusuario con rotación/revocación, turnos
  reales, SSE, límite de pedidos; GUI web; despliegue con HTTPS y systemd; respaldo y
  recuperación.


> 21 implementaciones tomadas de un análisis de 7 repos externos afines
> (ver `docs/INFORME_ANALISIS_REPOS_EXTERNOS_2026-07-24.md` y
> `docs/ROADMAP_IMPLEMENTACIONES_2026-07-24.md`). Pendiente: decidir
> versión semántica (0.6.0 → 0.7.0 sugerido, a confirmar).

### Añadido
- **DSL de estadísticas derivadas** (`narrator/core/derived_stats.py`):
  vocabulario fijo sin eval/exec; corrige un modificador espurio que se
  aplicaba a las características 1-99 de CoC 7e.
- **Tirada sugerida pendiente**: el narrador puede sugerir "5d10"/"1D20"
  y el panel de dados la precarga con un click.
- **Reparación de JSON malformado** (`narrator/core/json_repair.py`) +
  **field-locking** en `ExtractorAgent.regenerate_npc()`.
- **Factory de proveedores de LLM** (`narrator/core/providers.py`):
  Ollama first-class, conecta claves de `config.yaml` que estaban sin usar.
- **Lorebook por keywords** (`narrator/core/lorebook.py`): RAG liviano sin
  embeddings; 4 entradas reales en `vtm_v20.yaml`.
- **Ideas Inbox** (`narrator/core/ideas_inbox.py`): bandeja de borradores
  con workflow de estados y promoción a NPC/Locación, con UI en el tab Estado.
- **Cola de iniciativa** (`narrator/core/initiative.py`) para combate por
  turnos explícito.
- **Metadata de token en NPCs** (color/icono/estado/condiciones) +
  **recall automático por mención** (`narrator/core/mention_detector.py`).
- **Decorador `@tool`** (`narrator/core/tools.py`): schema de
  function-calling desde type hints — infraestructura, sin conectar aún.
- **Validación del bloque `resolution`** de los YAML de sistema
  (`narrator/core/resolution_schema.py`).
- **Auto-guardado de entidades + mutación de estado**: el narrador declara
  NPCs/Locaciones nuevos y cambios de HP/condiciones con etiquetas técnicas
  que el sistema aplica solo, sin pedírselo el jugador.
- **Modelo de facción enriquecido**: metas/métodos/recursos/influencia/relaciones.
- **Entidad Eventos**: timeline causa-efecto en `vault/Eventos/`.
- **Deduplicación de memoria episódica**: descarta resúmenes parafraseados.
- **Extracción de fichas PDF vía AcroForm** (`sheet_parser.extract_form_fields`).
- **Búsqueda global cross-entidad** en el vault (`retriever.search_all`).
- **Detector dice-first** (`narrator/core/dice_first_guard.py`): señala
  (no bloquea) cuando el narrador narra un resultado sin tirada previa.
- **Harness IA-vs-IA** (`narrator/agents/player_agent.py`,
  `scripts/playtest.py`): jugador simulado con 5 arquetipos, métricas de
  fuga de secretos y dice-first-miss, gate con exit code — implementa la
  Fase 4 (IA vs IA) que el roadmap del proyecto tenía pendiente.
- **Tarjetas SillyTavern V2** (`narrator/core/character_card.py`):
  import/export de NPCs vía PNG + chunk `chara`.
- **Motor de TTS local** (`narrator/core/tts_engine.py`, dependencia
  opcional `pyttsx3`): spike + implementación, sin conectar a la GUI aún.

### Arreglado
- **NPCs con contexto aislado**: `npc_routines.py` inyectaba relojes de
  Frentes y el resumen de última sesión (secretos del Máster) en el
  prompt de decisión de un NPC individual — habilitaba metagaming y fugas.
- **Logger en consola Windows (cp1252)**: un log con emoji (🔴💡⚖🎲)
  rompía el proceso con `UnicodeEncodeError`; ahora usa `errors="replace"`.

### Pendiente (fuera de esta tanda)
- Fase 19 del roadmap (fog-of-war/mapa visual): requiere decidir si un
  modo de mapa entra en el alcance del proyecto.
- Wiring de UI para el motor de TTS y las tarjetas SillyTavern.

## [0.6.0] — 2026-07-10

### Añadido
- **Psicología de NPCs** (`narrator/core/npc_psyche.py`): arquetipo
  jungiano dominante + rasgos dimensionales 0–1 en el frontmatter de
  cada NPC (asignados por el extractor, editables en Obsidian); los NPCs
  en escena llevan una línea conductual "psique:" al prompt del narrador.
- **Sistema de Escenas** (`narrator/core/scene_manager.py`): escenas en
  el vault (`tipo: escena`) con condiciones de desbloqueo determinísticas
  (keywords del jugador, flags, reloj lleno); ciclo bloqueada →
  disponible → jugada con flags otorgados; visibles en el tab Estado.
- **Fronts reactivos**: las acciones del jugador aceleran en vivo los
  relojes de los frentes sensibles (`reactivo_a`); un reloj llenado en
  vivo dispara un EVENTO FORZOSO que interrumpe la escena.

## [0.5.0] — 2026-07-10

### Añadido
- **Memoria episódica jerárquica** (`narrator/core/memory_manager.py`):
  al LLM va solo la ventana de los últimos 10 mensajes (capa 1); los
  turnos anteriores se resumen en background a viñetas factuales que
  entran al prompt como MEMORIA DE LA SESIÓN (capa 2); el RAG del vault
  sigue como capa 3. Evita el desborde de contexto de los modelos 7B
  en sesiones largas.
- Persistencia de la memoria episódica en `session.json`, con
  restauración al reabrir y reset en "Nueva sesión".

### Arreglado
- `.gitignore`: se excluyen artefactos de build (`*.egg-info/`,
  `build/`, `dist/`).

## [0.4.0] — 2026-07-10

### Añadido
- **Rule Arbiter** (`narrator/core/rule_arbiter.py`): resolución mecánica
  determinística de tiradas contra la planilla. Mecánicas: d20+mod vs CD
  (D&D 5e / PF2e, críticos naturales), pool d10 con éxitos netos y botch
  (VtM V20), percentil normal/duro/extremo/pifia (CoC 7e) y bandas por
  ratio (genérico).
- Sección `resolution` en los YAML de sistemas: escalera estándar de
  dificultades, keywords de acción→atributo y override del jugador
  ("CD 18").
- El veredicto se muestra en el chat (⚖) y se inyecta al prompt como
  sección RESOLUCIÓN MECÁNICA con instrucción de no recalcular.

### Cambiado
- La banda 10+/7-9/6- del MasterMoveEngine sale del veredicto real del
  arbiter; la heurística por ratio queda como fallback.

## [0.3.0] — 2026-07-10

### Añadido
- **Flujo de inicio guiado**: al abrir una sesión nueva, el sistema pregunta
  qué juego se jugará, pide el manual básico (PDF) y luego la planilla del
  jugador (PDF), sin intervención del LLM durante el setup.
- **Parser de planillas** (`narrator/core/sheet_parser.py`): la planilla
  adjunta se extrae con PyMuPDF y se estructura vía LLM a JSON para poblar
  la hoja de personaje. Reusable por el futuro Rule Arbiter.
- Botón "Planilla" en el header para (re)abrir el diálogo de carga.
- Tests del parser de planillas (8 casos).

### Cambiado
- **Creación de personaje in-app pospuesta**: se elimina el prompt de
  creación tras cargar el manual; el narrador usa la planilla provista y no
  inventa datos del personaje.
- **Layout responsive**: la GUI se reajusta al tamaño real del viewport
  (resize y barra de progreso incluidos); el input del chat y todos los
  botones quedan siempre visibles.
- "Nueva sesión" conserva el manual cargado y re-pide solo la planilla.

### Arreglado
- `pip install -e .` fallaba por descubrimiento de múltiples paquetes
  top-level en flat-layout (`data`, `config`, `narrator`); se limita el
  discovery a `narrator*` y se incluyen los YAML como package-data.

## [0.2.0] — anterior

- Motor de rol con agentes especializados y LLMs locales vía Ollama
  (base heredada; ver README).
