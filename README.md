# Narrador TTRPG — Motor de Rol con Agentes y Ollama

Sistema narrador de TTRPG impulsado por LLMs locales. Un ecosistema de agentes especializados mantiene la coherencia del mundo mientras un modelo pequeño (7B) narra las escenas.

> **Principio fundamental:** El LLM es el pincel, no el cerebro. El sistema mantiene la coherencia; el modelo solo pinta las escenas.

---

## Instalación rápida

### 1. Ollama (IA local)

```bash
# Instalar Ollama → https://ollama.com
ollama pull mistral        # ~4GB - buena calidad narrativa (recomendado)
ollama pull llama3.2       # ~2GB - más rápido
ollama pull llama3.1:8b    # ~5GB - mejor calidad
ollama pull gemma3:12b     # ~8GB - excelente

# Opcional — búsqueda semántica
ollama pull nomic-embed-text
```

### 2. Dependencias Python

```bash
pip install -e .
# o manualmente:
pip install dearpygui requests PyMuPDF pyyaml python-frontmatter jinja2
```

### 3. Ejecutar

```bash
python main.py
```

---

## Cómo usar

### Flujo básico

1. **Abrir** → se conecta a Ollama automáticamente
2. **Cargar PDF** → seleccioná el manual de tu juego de rol
3. **Construir Vault** → los agentes analizan el manual y crean el mundo (NPCs, locaciones, frentes)
4. **Crear personaje** → el narrador te guía con menús basados en el sistema detectado; la planilla se rellena automáticamente con las secciones correctas para tu clan/clase
5. **Jugar** → escribí acciones, usá los dados, el mundo reacciona
6. **Guardar sesión** → continuar después desde donde dejaste
7. **Nueva sesión** → exporta el log automáticamente e incrementa el número de sesión

### Panel de dados

Seleccioná cantidad y tipo (D4 / D6 / D8 / D10 / D12 / D20). El resultado se envía al narrador con un click.

### Tab Estado

Muestra los relojes de frentes activos con barras de progreso ASCII, el número de sesión y el sistema de juego actual.

### Exportar log

El log de sesión se exporta como Markdown e incluye la transcripción completa, snapshot JSON del personaje y estado de los relojes de frentes. Se exporta automáticamente al iniciar una nueva sesión.

---

## Arquitectura

```
PDF
 └─► [Extractor Agent] ─► índice semántico (nomic-embed-text)
          │
          ▼
     VAULT (MD/YAML)          ← memoria compartida entre agentes
     NPCs/ Locaciones/
     Frentes/ Misterios/
          │
          ▼
     [Orquestador]            ← Python puro, sin LLM
     /    |    |    \
[Narrador][Mundo][NPCs][Motor de Teoría Rolera]
          │
          ▼
     GUI (Dear PyGui)
```

Cada agente recibe solo el fragmento del vault que necesita. Esto permite usar modelos de 7B con contexto limitado (~2000 palabras) sin perder coherencia.

### Motor de Teoría Rolera Universal — todos conectados

Los 4 agentes de teoría se instancian en el Orquestador y contribuyen al system prompt en cada turno:

| Agente | Archivo | Sección en prompt | Cuándo actúa |
|--------|---------|-------------------|--------------|
| MasterMoveEngine | `master_move_engine.py` | MOVIMIENTO DEL MÁSTER SUGERIDO | Cada turno |
| PacingToneAgent | `pacing_tone_agent.py` | RITMO Y TONO | Cada turno |
| WorldSimulationEngine | `world_simulation_engine.py` | ESTADO DEL MUNDO | Cada turno |
| InvestigationEngine | `investigation_engine.py` | INVESTIGACIÓN | ≥4 turnos sin avance en misterio |

El `PacingToneAgent` acumula eventos del jugador vía `record_event()` — el tipo de acción (combate, exploración, diálogo, etc.) se detecta automáticamente del texto y alimenta el análisis de ritmo.

El `InvestigationEngine` aplica la **Regla de los 3 indicios**: si el jugador lleva varios turnos sin avanzar en un misterio activo, el motor inyecta una instrucción de desbloqueo narrativo al narrador.

Archivos de configuración (YAML):
- `universal_master_moves.yaml` — Movimientos agnósticos del Máster
- `universal_narrative_tools.yaml` — Herramientas narrativas y reglas de investigación
- `universal_world_tools.yaml` — Frentes, Relojes y Consecuencias sociales

Estado persistente (generados automáticamente, no commitear):
- `world_state.json`
- `investigation_state.json`

### Planilla de personaje schema-driven

Cada sistema define en su YAML una `character_sheet_schema` con secciones base y secciones condicionales según el arquetipo elegido (clan en VtM, clase en D&D/PF2e, ocupación en CoC). La GUI renderiza la planilla correcta automáticamente:

- **Atributos VtM** → formato dots `●●●○○`
- **Atributos D&D/PF2e** → formato stat block `16 (+3)`
- **Disciplinas por clan** → sección que aparece solo cuando el clan está definido
- **Campos extra del LLM** → sección "Otros" como fallback

---

## Estructura del repositorio

```
narrador-ttrpg/
├── main.py                    ← punto de entrada
├── pyproject.toml             ← dependencias y packaging
├── config/
│   └── config.yaml            ← configuración global
├── narrator/                  ← paquete principal
│   ├── app.py                 ← GUI (Dear PyGui)
│   ├── core/
│   │   ├── llm_client.py      ← wrapper Ollama (streaming + sync)
│   │   ├── retriever.py       ← búsqueda keyword + semántica en vault
│   │   ├── embedder.py        ← embeddings via nomic-embed-text
│   │   ├── state_manager.py   ← relojes, frentes, flags, historial de sesiones
│   │   ├── prompt_builder.py  ← ensamblado de prompts desde system YAML + vault
│   │   ├── vault_writer.py    ← escritura en tiempo real al vault (Obsidian)
│   │   └── theory_engine/     ← agentes de teoría rolera universal
│   │       ├── master_move_engine.py
│   │       ├── world_simulation_engine.py
│   │       ├── pacing_tone_agent.py
│   │       ├── investigation_engine.py
│   │       └── *.yaml         ← configuración universal
│   └── agents/
│       ├── orchestrator.py    ← coordinador central (Python puro, sin LLM)
│       ├── extractor_agent.py ← PDF → vault + indexación semántica
│       ├── narrator_agent.py  ← post-procesamiento de respuestas
│       ├── npc_routines.py    ← simulación de NPCs entre sesiones
│       └── world_agent.py     ← avance autónomo del mundo (downtime)
├── data/
│   └── systems/               ← configs YAML por sistema de juego
│       ├── vtm_v20.yaml       ← VtM V20 (9 clanes con Disciplinas)
│       ├── dnd_5e.yaml        ← D&D 5e (7 clases)
│       ├── coc_7e.yaml        ← La Llamada de Cthulhu 7e
│       ├── pathfinder_2e.yaml ← Pathfinder 2e
│       └── generic.yaml       ← Sistema genérico
└── docs/
    ├── prompts/               ← guía de worldbuilding desde sourcebook
    └── *.md                   ← técnicas narrativas y diseño
```

---

## Sistemas de juego soportados

| Sistema | Archivo config | Clanes/Clases con planilla | Estado |
|---------|---------------|---------------------------|--------|
| Vampiro: La Mascarada V20 | `data/systems/vtm_v20.yaml` | 9 clanes (Brujah, Malkavian, Nosferatu, Toreador, Tremere, Ventrue, Gangrel, Lasombra, Tzimisce) | Completo |
| Dungeons & Dragons 5e | `data/systems/dnd_5e.yaml` | 7 clases (Mago, Guerrero, Clérigo, Pícaro, Bárbaro, Paladín, Brujo) | Completo |
| La Llamada de Cthulhu 7e | `data/systems/coc_7e.yaml` | Ocupaciones | Completo |
| Pathfinder 2e | `data/systems/pathfinder_2e.yaml` | 5 clases | Completo |
| Genérico (cualquier TTRPG) | `data/systems/generic.yaml` | — | Completo |

La detección de sistema es automática al cargar el PDF. Para cambiarlo manualmente, editá `sistema_activo` en `config/config.yaml`.

---

## Vault y Obsidian

El vault es una carpeta de archivos Markdown con frontmatter YAML, 100% compatible con Obsidian.

```
vault/
  00_Dashboard.md       ← punto de entrada con estado de campaña
  .embeddings.json      ← índice semántico (generado automáticamente)
  NPCs/                 ← un archivo por NPC
  Locaciones/           ← un archivo por locación
  Cofradias/            ← facciones, coteries, manadas
  Frentes/              ← amenazas activas con relojes
  Misterios/            ← investigaciones con nodos y pistas
  Recursos/             ← bangs, tablas, handouts
  Sesiones/             ← log de sesiones + downtime en tiempo real
```

Podés abrir `vault/` como vault de Obsidian para navegar el mundo, editar NPCs manualmente, ver el graph de conexiones entre entidades, y usar Dataview para dashboards dinámicos.

El narrador lee y escribe el vault en tiempo real. Los cambios que hacés en Obsidian se reflejan en la próxima sesión.

---

## Configuración

`config/config.yaml` controla el sistema activo, modelo LLM y rutas:

```yaml
sistema_activo: "vtm_v20"   # vtm_v20 | dnd_5e | coc_7e | pathfinder_2e | generic
llm:
  model: "mistral:7b"       # modelo de Ollama a usar
vault:
  live_updates: true        # actualización en tiempo real (Obsidian)
```

### Modelos recomendados

| Modelo | RAM | Calidad narrativa |
|--------|-----|-------------------|
| llama3.2 | ~2GB | ★★★☆☆ |
| mistral:7b | ~4GB | ★★★★☆ |
| llama3.1:8b | ~5GB | ★★★★☆ |
| gemma3:12b | ~8GB | ★★★★★ |

---

## Roadmap

### Fase 0 — Motor de Teoría Rolera Universal ✅ Completado

- 4 agentes implementados y conectados al Orquestador
- MasterMoveEngine, WorldSimulationEngine, PacingToneAgent, InvestigationEngine
- YAMLs de configuración universal validados
- Regla de los 3 indicios activa

### Fase 1 — Narrador con jugador humano 🔄 En progreso

- [x] GUI funcional (Dear PyGui) con dados, log de sesión, hoja de personaje
- [x] Integración Ollama con streaming
- [x] Carga y detección automática de sistema desde PDF
- [x] Arquitectura de agentes (`narrator/core/` + `narrator/agents/`)
- [x] Sistemas: VtM V20, D&D 5e, CoC 7e, Pathfinder 2e, Genérico
- [x] Vault compatible con Obsidian
- [x] Extractor agent (PDF → vault automático)
- [x] Vault writer (Obsidian live updates)
- [x] Búsqueda semántica en vault (nomic-embed-text via Ollama)
- [x] Tab Estado con relojes de frentes
- [x] Soporte multi-PDF (botón "Añadir suplemento")
- [x] Integración de los 4 agentes de teoría rolera al Orquestador
- [x] Detección de tipo de evento por turno (combate/exploración/diálogo/etc.)
- [x] StateManager extendido para frentes como recurso central
- [x] World agent — avance autónomo del mundo con sincronización post-downtime
- [x] Exportar log de sesión a Markdown (con snapshot de personaje y relojes)
- [x] Auto-export + incremento de sesión en botón "Nueva sesión"
- [x] Planilla de personaje schema-driven con secciones condicionales por clan/clase
- [ ] Bug pendiente (a reportar)

### Fase 2 — Soporte multi-sistema avanzado ⏳ Planificado

- Detección automática de sistema desde PDF sin configuración manual
- Soporte de sistemas adicionales con configs YAML

### Fase 3 — Estadísticas narrativas ⏳ Planificado

- Exportación de métricas: comportamiento del LLM, uso de movimientos del Máster, evolución de frentes

### Fase 4 — IA vs IA ⏳ Futuro

- Agente jugador IA que recibe escena y devuelve acción
- Loop autónomo narrador/jugador
- Métricas de coherencia narrativa emergente

---

## Contribuir

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para el flujo de ramas, convenciones de commits y archivos que no deben commitearse.

---

## Problemas comunes

**Sin Ollama:** Asegurate de que Ollama esté corriendo (`ollama serve`)

**GUI no abre:** Verificá Dear PyGui (`pip install dearpygui`)

**PDF no se carga:** Verificá PyMuPDF (`pip install PyMuPDF`)

**Sin búsqueda semántica:** Instalá el modelo de embeddings (`ollama pull nomic-embed-text`)

**El narrador no actualiza la hoja:** Pedile explícitamente que guarde los datos en formato JSON

---

## .gitignore

Los siguientes archivos se generan en tiempo de ejecución y no deben commitearse:

```
vault/
estado_campana.yaml
world_state.json
investigation_state.json
*.pyc
__pycache__/
.env
```

---

## Licencia

MIT — ver [LICENSE](LICENSE).
