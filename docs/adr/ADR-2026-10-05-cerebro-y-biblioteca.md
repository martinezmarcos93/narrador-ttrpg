# ADR — Cerebro permanente + biblioteca documental

- Fecha: 2026-10-05
- Estado: aceptado para implementación
- Rama: feat/cerebro-integracion

## Contexto

El narrador necesita conocimiento rolistico general antes de comenzar una
crónica, pero también debe poder consultar manuales PDF específicos durante la
creación de personajes y la partida.

Los manuales contienen excepciones y detalles demasiado específicos para
convertirlos todos en conocimiento universal.

## Decisión

Se mantienen dos capas complementarias:

1. **Cerebro permanente**: conceptos universales, patrones narrativos,
   conceptos mecánicos, diseño de campaña y conocimiento previamente
   normalizado en neuronas.
2. **Biblioteca documental**: PDFs y documentos de la crónica/sistema. El
   barrido PDF puede convertirlos en neuronas específicas y el sistema puede
   conservar además el documento original como fuente de referencia.

El cerebro usa el mismo componente Embedder/Retriever de la aplicación. No se
crea un segundo pipeline de RAG independiente.

## Precedencia

Cuando haya conflicto, el conocimiento específico tiene prioridad:

estado de campaña > regla específica recuperada > pack de sistema >
conocimiento universal > conocimiento general del LLM.

El cerebro universal nunca debe inventar una excepción de un reglamento.

## Consecuencia

La carga de un PDF sigue siendo una operación fundamental. El cerebro reduce
el trabajo repetitivo y aporta vocabulario/conceptos rolisticos desde el inicio;
el manual aporta precisión de sistema, opciones de personaje, excepciones,
lore y tono específico.
