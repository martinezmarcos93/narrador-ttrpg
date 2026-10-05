# Cerebro: ingestión, indexación y evaluación — 2026-10-05

## Pipeline

`PDF -> loader -> chunks Markdown -> metadata/provenance -> brain index -> hybrid retrieval -> KnowledgeRouter -> prompt`

La ingestión no llama al LLM. La indexación de embeddings es una segunda etapa local y pesada.

## Loader

`narrator/cerebro/document_loader.py`:

- extrae páginas con PyMuPDF;
- conserva ruta de origen;
- divide por párrafos con límite de caracteres;
- calcula SHA-256 por chunk;
- genera metadatos explícitos;
- escribe neuronas Markdown.

Metadatos mínimos:

- id;
- title;
- source;
- system;
- campaign;
- kind;
- layer;
- chunk_index;
- content_hash.

Esto evita que el origen de un fragmento desaparezca durante la recuperación.

## Indexación

`narrator/cerebro/indexador.py` mantiene:

- `.brain_embeddings.json`;
- `.brain_index.yaml`.

La indexación es incremental mediante hash de contenido. Usa embeddings locales y no requiere enviar documentos a un servicio externo.

## Recuperación

`RecuperadorCerebro` combina:

1. similitud semántica;
2. coincidencia léxica;
3. filtro de sistema;
4. filtro de campaña;
5. filtro por kind;
6. expansión de grafo.

Las fuentes universales/genéricas siguen siendo compartibles; los documentos con campaign específica solo deben entrar cuando coincide la campaña solicitada.

## Evaluación

`scripts/evaluate_retrieval.py` ejecuta localmente casos de:

- investigación;
- combate;
- continuidad;
- VtM;
- D&D;
- Call of Cthulhu;
- Pathfinder.

Métricas:

- precision@k;
- recall@k;
- MRR;
- nDCG;
- layer coverage.

La ejecución real queda deliberadamente para el entorno local porque requiere el corpus real y, para retrieval semántico, Ollama/embeddings.

## Ingestión local

Ejemplo conceptual:

`python scripts/ingest_brain.py manual.pdf --system dnd_5e --campaign mi-campana`

Luego:

`python -m narrator.cerebro.indexador --path cerebro`

Finalmente:

`python scripts/evaluate_retrieval.py --brain cerebro --k 5`

Primero revisar los Markdown generados. No indexar ciegamente PDFs completos sin verificar metadata, sistema y campaña.

## Regla de autoridad

El cerebro no puede convertir una fuente privada en conocimiento narrativo. La visibilidad sigue siendo responsabilidad de KnowledgeRouter/KnowledgeVisibility y del contrato de contexto.

`Python determines truth; LLM interprets/proposes/narrates.`
