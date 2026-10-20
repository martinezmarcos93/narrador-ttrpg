# Pipeline de manuales → cerebro

```
PDF ─► identify_manual()  ─► ¿está en data/cerebro/fuentes.yaml?
         sistema + edición        ├─ sí → barredor (secciones, jerarquía, poderes, enlaces)
         + confianza + aviso      └─ no → document_loader (chunks con hash y provenance)
                                              │
                         IndiceCerebro.build() ◄┘  embeddings incrementales por hash
                                              │
                         audit_brain(profile)  ─► esquema, IDs = ruta, enlaces rotos
```

Comando único: `python scripts/manual_pipeline.py <manual.pdf>` (`--dry-run` muestra el plan).

## Garantías

- **Determinista**: ninguna etapa llama al LLM. Mismo PDF → mismas neuronas.
- **Procedencia**: cada neurona guarda libro, páginas y fuente; el router las cita.
- **Copyright**: el texto barrido vive en `cerebro/` (ignorado por git); en el repo solo
  se versionan rutas y metadatos (`data/cerebro/fuentes.yaml`).
- **Seguridad**: al llegar al prompt, el texto pasa por `injection_guard`.
- **Ediciones**: si el manual no coincide con la edición del pack, se avisa.

## Durante una sesión

El manual adjunto en la GUI no se indexa en el cerebro: `ManualIndex` lo trocea en
pasajes de ~180 palabras con página y el router entrega los 2 más relevantes (BM25).
