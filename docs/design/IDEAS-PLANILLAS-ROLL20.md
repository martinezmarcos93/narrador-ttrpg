# Ideas para planillas tomadas de Roll20 (2026-10-19)

Fuente: https://github.com/Roll20/roll20-character-sheets (licencia MIT). Se revisó
**solo la estructura** de campos y secciones para inspirar los `character_sheet_schema`
de los System Packs. No se copió HTML, CSS, JS ni texto de reglas.

## Planillas revisadas

| Carpeta en Roll20 | Juego | Interés |
|---|---|---|
| `CWOD-V20`, `CWOD-Vampire` | Vampiro: La Mascarada 20 aniversario / clásica | alto (pack `vtm_v20`) |
| `CWOD-W20`, `CWOD-Werewolf` | Hombre Lobo: El Apocalipsis 20 aniversario | alto (pack `wta_w20`) |
| `CWOD-DAV20` | Vampiro: Edad Oscura 20 aniversario | medio (variante de V20) |
| `CWOD-M20`, `CWOD-Mage` | Mago: La Ascensión 20 aniversario | medio |
| `CWOD-Wr20` | Wraith: El Olvido 20 aniversario | bajo |
| `CWOD-C20` | Changeling: El Ensueño 20 aniversario | bajo |
| `CWOD-Hunter`, `CWOD-Demon` | Cazador / Demonio clásicos | bajo |
| `Call_of_Cthulhu_7th_Ed`, `Call_of_Cthulhu_Spanish` | La Llamada de Cthulhu 7e | alto (pack `coc_7e`) |
| `DnD_5e` | D&D 5e | medio (pack `dnd_5e`) |
| `Pathfinder Second Edition by Roll20` | Pathfinder 2e | bajo (pack `pathfinder_2e`) |
| `vampire-v5`, `WTA5e` | Vampiro V5 / Hombre Lobo W5 | futuro |

## Patrones comunes del Mundo de Tinieblas clásico (20 aniversario)

1. **Cabecera**: nombre, jugador, crónica, naturaleza, conducta, concepto + 3 rasgos de
   arquetipo (V20: clan, generación, sire; W20: raza, augurio, tribu, manada y tótem;
   M20: esencia, tradición/afiliación, cábala).
2. **Atributos 3×3** (físicos, sociales, mentales), 1–5 puntos, cada uno con su
   **especialidad** opcional (V20 la guarda como `<rasgo>_spec`).
3. **Habilidades 3×10** (talentos, técnicas, conocimientos), 0–5, con especialidad y
   2–3 huecos libres por columna para habilidades secundarias.
4. **Ventajas**: listas de nombre+puntos (disciplinas, trasfondos; W20: dones, ritos,
   fetiches; M20: esferas y rotes; Wr20: arcanoi, pasiones, grilletes).
5. **Virtudes y moralidad** (V20/DAV20/C20): conciencia/convicción, autocontrol/instinto,
   coraje; senda con 1–10 y su "aura" (bearing) asociada.
6. **Reservas permanente/temporal**: Fuerza de Voluntad siempre aparece como par
   (`willpower` y `willpower_used`). En W20: Furia, Gnosis y Renombre (gloria, honor,
   sabiduría) también tienen par permanente/temporal; en C20: Glamour y Banalidad.
7. **Reserva de sangre** con **máximo por turno** derivado de la generación (`bppt`).
8. **Salud como track de 7 niveles** con penalizador: Magullado (0), Lastimado (−1),
   Lesionado (−1), Herido (−2), Malherido (−2), Tullido (−5), Incapacitado; los niveles
   extra se agregan aparte (Fortaleza, formas de W20).
9. **Listas repetibles**: méritos, defectos, trasfondos extendidos, armas cuerpo a cuerpo
   y a distancia, armadura, refugios, vínculos de sangre, favores (boons), experiencia.
10. **Dados preparados**: "dice pools" con nombre = atributo + habilidad + especialidad.
11. **W20 – formas**: Homínido, Glabro, Crinos, Hispo, Lupus con modificadores de
    atributos y dificultad; el estado guarda la forma actual.

## La Llamada de Cthulhu 7e

- Características (FUE, DES, INT, CON, APA, POD, TAM, EDU) en percentil con mitad y
  quinto (éxito difícil y extremo) **derivados**, no cargados a mano.
- Suerte, Cordura (actual, inicial, máxima = 99 − Mitos de Cthulhu), PV, PM derivados.
- Habilidades con valor base, casilla de "marcada para mejorar" y mitad/quinto derivados.
- Secciones de trasfondo: ideología, personas significativas, lugares, posesiones,
  rasgos, lesiones, fobias/manías, tomos leídos, encuentros con entidades.

## D&D 5e / Pathfinder 2e

- Atributos con modificador derivado (`floor((v-10)/2)`, ya en `stat_modifier_formula`).
- Competencias por nivel derivadas; salvaciones y habilidades marcadas como competentes.
- Pathfinder 2e: rangos de competencia (no entrenado, entrenado, experto, maestro,
  legendario) y condiciones con valor (moribundo 1–4, herido N, condenado N).

## Qué adoptamos en los System Packs

| Idea | Implementación |
|---|---|
| Especialidades por rasgo | campo `especialidades` de tipo `map` (rasgo → especialidad) |
| Par permanente/temporal | dos campos `int` (`fuerza_voluntad`, `fuerza_voluntad_temp`) |
| Track de salud | sección con `display: track` y `levels` (etiqueta + penalizador) |
| Listas repetibles | campos `type: list` (méritos, defectos) o `map` (trasfondos → puntos) |
| Derivados | `derived:` en el schema con el DSL seguro de `derived_stats` |
| Formas (W20) | campo `forma` con valores permitidos + regla de continuidad |

Todo cambio se valida con `narrator/core/character_sheet.py` y los tests de packs.
