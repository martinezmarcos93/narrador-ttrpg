---
id: universal-estado-persistente
title: Estado persistente de campaña
system: universal
kind: architecture
tags: [estado, persistencia, memoria, campaña]
---

El estado de campaña debe representar hechos que continúan siendo verdaderos después de una respuesta del modelo.

Ejemplos: posición actual, heridas, condiciones, recursos, relaciones, relojes, frentes, pistas descubiertas, NPC conocidos, objetos obtenidos y decisiones con consecuencias.

La narración puede describir el estado, pero no debe ser la única fuente del estado. Python debe conservar los valores estructurados y aplicar sus cambios de forma determinista.
