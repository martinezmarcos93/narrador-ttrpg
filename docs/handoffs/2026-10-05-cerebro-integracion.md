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
