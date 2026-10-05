"""
Cerebro — base de conocimiento del narrador en neuronas Markdown (Obsidian).

Tres capas, cada una en su carpeta del vault:
- universal/    conceptos roleros válidos para cualquier juego
- sistemas/     reglas y ambientación de cada juego, barridas de los manuales
- propias/      notas escritas a mano (nunca las pisa el barredor)

El contenido del vault NO se versiona: lo regenera `barredor` a partir de
`data/cerebro/fuentes.yaml` y de la biblioteca local de manuales.
"""
