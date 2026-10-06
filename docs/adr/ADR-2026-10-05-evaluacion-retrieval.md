# ADR — Evaluación reproducible del retrieval

## Contexto

El cerebro ya dispone de recuperación híbrida semántica + léxica + grafo y el
router conserva la procedencia por capas. Los indicadores actuales son
telemetría operativa, no una medición de precisión.

## Decisión

Separar la telemetría del runtime de una evaluación offline con ground truth.

Cada caso define consulta, IDs relevantes, relevancia graduada opcional, sistema
y capas esperadas. El evaluador calcula precision@k, recall@k, MRR y nDCG@k.

El evaluador no crea embeddings, no llama al LLM y no modifica estado de campaña.
Puede ejecutarse con fixtures deterministas o conectarse posteriormente al
índice real.

## Criterio

No se considerará que el retrieval mejoró por una caída de latencia o por una
media de similitud mayor. Una mejora debe observarse sobre el mismo conjunto de
consultas y ground truth.

## Próximo paso

Conectar esta batería al índice real cuando el entorno local disponga del
modelo de embeddings. Hasta entonces, los tests validan las métricas y la
estructura del benchmark, no la calidad empírica del modelo.
