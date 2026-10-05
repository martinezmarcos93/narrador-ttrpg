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
