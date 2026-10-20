# Rendimiento medido (Fase J, 2026-10-20)

Equipo local, CPU, Ollama 0.33, `qwen3:1.7b` (narrador) y `nomic-embed-text`.
Cerebro: 7.292 neuronas. Campaña: `data/campaigns/noches_de_ceniza.yaml`.

| Etapa | Antes | Ahora |
|---|---|---|
| Carga del índice del cerebro | 15 s | 2,3 s |
| Búsqueda en el cerebro (por consulta) | ~33 s | 0,1–0,5 s |
| `prepare_turn` (frío, primer turno) | — | 3,1 s |
| `prepare_turn` (caliente) | 0,45 s | ~0,3 s (caché del System Pack) |
| Turno completo con LLM (5 turnos, media) | 31 s* | 18,6 s |

\* con el razonamiento de qwen3 activado; ahora se desactiva (`think=false`).

## Dónde está el tiempo

El LLM domina (>95 % del turno). El prompt ronda 1.700 palabras (~3.000 tokens):
contexto recuperado ~730, reglas de propuesta ~240, hechos canónicos ~180.

## Palancas

- Modelo: con GPU o un modelo 7B cuantizado (Q4_K_M) la calidad sube mucho; con
  CPU, 1,7–3B es lo jugable.
- `max_words` del router (700 por defecto) controla el contexto recuperado.
- Streaming (GUI y SSE) hace que el primer texto aparezca en ~2–4 s aunque el
  turno completo tarde más.
- Reproducir: `python scripts/play_campaign.py data/campaigns/noches_de_ceniza.yaml --turns 5`.
