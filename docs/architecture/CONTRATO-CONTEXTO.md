# Contrato de contexto y procedencia

Toda información que llegue al prompt del narrador debe poder clasificarse en
cinco capas:

| Capa | Función | Autoridad |
|---|---|---:|
| state | hechos persistentes de esta partida | 50 |
| campaign · regla de la casa | excepción formal: nota con `tipo: regla_casa` | 45 |
| manual | regla/lore específico recuperado de documentos | 40 |
| system | configuración del sistema activo | 30 |
| campaign | material propio de la crónica | 20 |
| universal | conceptos rolisticos generales | 10 |

La autoridad no significa que una capa pueda contradecir silenciosamente otra.
Si existe conflicto, el sistema debe conservar ambas procedencias y resolver la
contradicción de forma explícita.

El cerebro universal nunca se interpreta como reglamento específico.

El manual sigue siendo consultable para reglas especiales y detalles de
creación de personajes. El estado de campaña tiene prioridad para hechos que
ya ocurrieron en esa partida.


## Excepciones formales

- **Reglas de la casa**: una nota del vault con `tipo: regla_casa` (o `house_rule: true`)
  es capa `campaign` pero con autoridad 45: prevalece sobre el manual y nunca sobre el
  estado. Si en el mismo contexto aparecen una regla de la casa y un pasaje del manual,
  el render antepone una línea de PRECEDENCIA explícita.
- **Ediciones**: si el manual adjunto es de otra edición que la del System Pack,
  `identify_manual()` lo advierte (ver `narrator/core/system_detection.py`).

## Documentos como datos

Todo texto de capas documentales pasa por `injection_guard.sanitize_document_text`
antes de llegar al prompt; la capa `state` (generada por Python) no se sanea. Cada
fragmento expone `citation` (manual con página, libro con páginas o id de neurona).
