# Línea base de retrieval (2026-10-19)

Primera medición real (B2/I/J del roadmap) sobre el corpus local:
7.292 neuronas = 32 universales (versionadas) + 7.260 de manuales barridos
(V20, CoC 7e, W20; generadas localmente, ignoradas por git).

- Embeddings: `nomic-embed-text` vía Ollama (el default anterior `bge-m3` no estaba
  instalado ni documentado; el README ya usaba nomic para el vault).
- Ground truth: `data/evaluation/retrieval_ground_truth.yaml` (20 casos, k=5).
- Resultados versionados en `data/evaluation/baselines/`.

## Cómo reproducir

```bash
python -m narrator.cerebro.indexador --path cerebro          # índice (incremental)
python scripts/evaluate_retrieval.py                          # solo cerebro
python tools/evaluate_retrieval.py                            # KnowledgeRouter completo
python scripts/audit_brain.py                                 # auditoría del cerebro
```

## Evolución (KnowledgeRouter, 14 casos originales salvo indicación)

| Paso | P@5 | R@5 | MRR | nDCG@5 |
|---|---|---|---|---|
| Inicial | 0,143 | 0,298 | 0,518 | 0,370 |
| Filtro por capa dentro de la búsqueda | 0,257 | 0,524 | 0,699 | 0,547 |
| Peso semántico 0,72 → 0,9 | 0,257 | 0,524 | 0,673 | 0,576 |
| + 6 casos nuevos (20 casos) | **0,270** | **0,617** | **0,696** | **0,615** |

Solo cerebro (20 casos): P@5 0,300 · R@5 0,675 · MRR 0,696 · nDCG 0,642.

## Hallazgos y decisiones

1. **Bug de capas**: el router buscaba la capa universal entre las 7.292 neuronas y
   filtraba después; las neuronas de manuales ocupaban el top-N y la capa universal
   quedaba vacía. Ahora `RecuperadorCerebro.search(layer=...)` filtra antes de rankear.
2. **Latencia**: cada búsqueda releía y parseaba el YAML de todas las neuronas
   (~33 s/consulta, 15 s de carga). Con metadata JSON, caché léxica y coseno
   vectorizado: 0,1–0,5 s/consulta y 2,3 s de carga.
3. **Prefijos de nomic** (`search_query:`/`search_document:`): empeoran en castellano
   (MRR 0,78 → 0,68 sobre la capa universal). No se usan.
4. **Peso semántico**: grilla 0,3–1,0 sobre la capa universal; 0,9 da la mejor
   precisión/recall sin perder el aporte léxico para términos exactos de reglas.
5. **Casos por sistema** (`system_*`) siguen bajos: el ground truth solo etiqueta
   neuronas universales y las neuronas de manuales (IDs locales) no están etiquetadas.
   D&D 5e y Pathfinder 2e no tienen manuales barridos en este equipo.

## Pendiente

- Etiquetar casos con neuronas de sistema (requiere IDs estables del barredor por máquina
  o un ground truth local no versionado).
- Barrer manuales de D&D 5e y Pathfinder 2e si se van a usar.
