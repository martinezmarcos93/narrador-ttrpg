"""
Vault Retriever — busca archivos en el vault y extrae contexto relevante.
El vault son archivos Markdown con frontmatter YAML.
Sprint 3: búsqueda semántica via Embedder (fallback a keyword si no disponible).
"""

import re
from narrator.logger import logger
from narrator.core import lorebook
from narrator.core.npc_psyche import format_psyche_line
from pathlib import Path
from typing import Optional

try:
    import frontmatter as fm
    _HAS_FRONTMATTER = True
except ImportError:
    _HAS_FRONTMATTER = False

from narrator.core.embedder import Embedder
from narrator.cerebro.recuperador import RecuperadorCerebro
from narrator.core.context_contract import ContextFragment, render_context


def _parse_file(path: Path) -> tuple[dict, str]:
    """Returns (metadata_dict, body_text). Graceful fallback si falta python-frontmatter."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    if _HAS_FRONTMATTER:
        try:
            post = fm.loads(text)
            return dict(post.metadata), post.content
        except Exception as e:
            logger.error(f"Error inesperado: {e}", exc_info=True)
    return {}, text


class VaultRetriever:
    def __init__(self, vault_path: str = "./vault", brain_path: str = "./cerebro", brain_embedding_model: str = "bge-m3"):
        self.vault_path = Path(vault_path)
        self._embedder = Embedder()
        self._index: Optional[dict[str, list[float]]] = None
        # Comparte infraestructura de embeddings, pero mantiene el índice
        # y los documentos del cerebro separados del vault de campaña.
        self.brain = RecuperadorCerebro(brain_path=brain_path, embedding_model=brain_embedding_model)


    def _all_md_files(self) -> list[Path]:
        if not self.vault_path.exists():
            return []
        return list(self.vault_path.rglob("*.md"))

    def _get_index(self) -> dict[str, list[float]]:
        if self._index is None:
            self._index = self._embedder.load_index(self.vault_path)
        return self._index

    # ── Contexto combinado y procedencia ─────────────────────
    def get_context_fragments(
        self,
        query: str,
        system: str | None = None,
        max_brain: int = 4,
        max_vault: int = 4,
    ) -> list[ContextFragment]:
        """Une cerebro + vault sin borrar la procedencia de cada fuente."""
        fragments: list[ContextFragment] = []

        for result in self.brain.search(
            query,
            max_results=max_brain,
            system=system,
            expand_graph=True,
        ):
            fragments.append(result["fragment"])

        for result in self.search(query, max_results=max_vault):
            meta, body = result["meta"], result["body"]
            layer = str(meta.get("capa", meta.get("layer", ""))).lower()
            if layer == "sistema":
                layer = "system"
            elif meta.get("origen") == "manual":
                layer = "manual"
            elif not layer:
                layer = "campaign"
            if layer not in {"universal", "system", "manual", "campaign", "state"}:
                layer = "campaign"
            fragments.append(ContextFragment(
                text=body,
                source=str(meta.get("fuente", meta.get("source", "vault"))),
                layer=layer,
                title=str(meta.get("nombre", Path(result["path"]).stem)),
                score=float(result.get("score", 0.0)),
                metadata=meta,
            ))

        return fragments

    def get_combined_context(
        self,
        query: str,
        max_words: int = 700,
        system: str | None = None,
    ) -> str:
        return render_context(
            self.get_context_fragments(query, system=system),
            max_words=max_words,
        )

    # ── Cerebro permanente ─────────────────────────────────────
    def get_brain_context(self, query: str, max_words: int = 500, system: str | None = None, kind: str | None = None) -> str:
        """Consulta conocimiento persistente del cerebro."""
        try:
            return self.brain.get_context(query, max_words=max_words, system=system, kind=kind)
        except Exception as exc:
            logger.warning("Cerebro no disponible: %s", exc)
            return ""

    def index_brain(self, on_progress=None) -> int:
        """Construye/actualiza el índice persistente de neuronas."""
        return self.brain.build_index(on_progress=on_progress)

    # ── Búsqueda global cross-entidad (Fase 18) ───────────────
    def search_all(self, query: str, tipo: "str | None" = None, max_results: int = 20) -> "list[dict]":
        """Búsqueda por texto libre sobre TODO el vault (NPCs, Locaciones,
        Frentes, Misterios, Cofradías, Eventos...), opcionalmente filtrada
        por `tipo`. Keyword simple (conteo de ocurrencias), navegación
        rápida durante sesión — no reemplaza get_relevant_context."""
        query_lower = (query or "").lower().strip()
        if not query_lower:
            return []
        scored = []
        for path in self._all_md_files():
            meta, body = _parse_file(path)
            if tipo and meta.get("tipo") != tipo:
                continue
            full_text = str(meta) + " " + body
            score = full_text.lower().count(query_lower)
            if score > 0:
                scored.append((score, {
                    "tipo": meta.get("tipo", "?"),
                    "nombre": meta.get("nombre", path.stem),
                    "path": str(path),
                    "score": score,
                }))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:max_results]]

    def invalidate_cache(self):
        """Fuerza recarga del índice semántico y re-chequeo de Ollama.
        Llamar tras construir/reconstruir el vault: el índice cacheado
        antes de la construcción quedaba vacío hasta reiniciar la app."""
        self._index = None
        self._embedder._available = None

    # ── Por tipo ──────────────────────────────────────────────
    def get_by_type(self, tipo: str, max_files: int = 10) -> list[dict]:
        """Devuelve todos los archivos del vault con el tipo dado (npc, locacion, frente…)"""
        results = []
        for path in self._all_md_files():
            meta, body = _parse_file(path)
            if meta.get("tipo") == tipo:
                results.append({"meta": meta, "body": body, "path": str(path)})
            if len(results) >= max_files:
                break
        return results

    # ── Búsqueda semántica ────────────────────────────────────
    def search_semantic(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Búsqueda semántica via embeddings. Carga el índice de vault/.embeddings.json.
        Devuelve [] si el modelo de embeddings no está disponible.
        """
        if not self._embedder.is_available():
            return []

        query_vec = self._embedder.embed(query)
        if not query_vec:
            return []

        index = self._get_index()
        if not index:
            return []

        scored = []
        for path_str, vec in index.items():
            score = Embedder.cosine_similarity(query_vec, vec)
            if score > 0.0:
                scored.append((score, path_str))

        scored.sort(reverse=True)
        results = []
        for _, path_str in scored[:max_results]:
            p = Path(path_str)
            if p.exists():
                meta, body = _parse_file(p)
                results.append({"meta": meta, "body": body, "path": path_str})

        return results

    # ── Búsqueda por keyword ──────────────────────────────────
    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Búsqueda combinada: semántica si está disponible, keyword como fallback.
        """
        semantic = self.search_semantic(query, max_results=max_results)
        if semantic:
            return semantic

        query_lower = query.lower()
        scored = []
        for path in self._all_md_files():
            meta, body = _parse_file(path)
            full_text = str(meta) + " " + body
            score = full_text.lower().count(query_lower)
            if score > 0:
                scored.append((score, {"meta": meta, "body": body, "path": str(path)}))
        scored.sort(reverse=True)
        return [item for _, item in scored[:max_results]]

    # ── Contexto compacto ─────────────────────────────────────
    def get_relevant_context(
        self, query: str, max_words: int = 400, lorebook_entries: "list[dict] | None" = None
    ) -> str:
        """
        Devuelve un bloque de texto con contenido del vault relevante para la query.
        Se mantiene dentro del budget de palabras para no inflar el contexto del LLM.

        `lorebook_entries` (Fase 5): reglas del sistema activo indexadas por
        keyword (narrator.core.lorebook). Se usan como complemento SOLO cuando
        no hay búsqueda semántica disponible (sin nomic-embed-text) — con
        embeddings activos, el vault ya cubre ese rol mejor.
        """
        results = self.search(query, max_results=3)
        if not results:
            results = (
                self.get_by_type("npc", max_files=2)
                + self.get_by_type("frente", max_files=2)
            )

        parts = []
        total_words = 0
        for r in results:
            meta = r["meta"]
            name = meta.get("nombre", Path(r["path"]).stem)
            tipo = meta.get("tipo", "entrada")
            body_snippet = r["body"][:600]
            snippet = f"[{tipo.upper()}] {name}\n{body_snippet}"
            words = len(snippet.split())
            if total_words + words > max_words:
                break
            parts.append(snippet)
            total_words += words

        if lorebook_entries and not self._embedder.is_available():
            remaining = max_words - total_words
            if remaining > 20:
                lore_text = lorebook.get_matching_content(lorebook_entries, query, max_words=remaining)
                if lore_text:
                    parts.append(lore_text)

        return "\n---\n".join(parts) if parts else ""

    # ── Indexación incremental ────────────────────────────────
    def index_new_files(self, on_progress=None) -> int:
        """
        Indexa semánticamente los archivos del vault que no están en el índice.
        Devuelve el número de archivos nuevos indexados.
        """
        if not self._embedder.is_available():
            return 0

        index = self._get_index()
        updated = 0

        for md_file in self._all_md_files():
            if str(md_file) in index:
                continue
            content = md_file.read_text(encoding="utf-8", errors="ignore")
            if self._embedder.index_file(md_file, content, index):
                updated += 1
                on_progress and on_progress(f"  Indexado: {md_file.name}")

        if updated:
            self._embedder.save_index(index, self.vault_path)

        return updated

    # ── Resúmenes de estado ───────────────────────────────────
    def get_active_npcs_summary(self, max_npcs: int = 6) -> str:
        """Resumen compacto de NPCs del vault para el contexto del narrador."""
        npcs = self.get_by_type("npc", max_files=max_npcs)
        if not npcs:
            return ""
        lines = []
        for npc in npcs:
            m = npc["meta"]
            name = m.get("nombre", "?")
            grupo = m.get("clan", m.get("raza", m.get("ocupacion", m.get("tipo", ""))))
            rol = m.get("rol", "")
            amenaza = m.get("amenaza", "")
            amenaza_str = f" [amenaza:{amenaza}]" if amenaza else ""
            # Psicología (C1): línea conductual para diálogos consistentes
            psyche = format_psyche_line(m)
            psyche_str = f" | {psyche}" if psyche else ""
            # Metadata de token (Fase 8): icono por amenaza + estado/condiciones
            # narrativas si cambiaron durante la partida (default: vivo, sin cond.)
            icono = m.get("icono", "")
            icono_str = f"{icono} " if icono else ""
            estado = m.get("estado", "vivo")
            estado_str = f" [{estado.upper()}]" if estado and estado != "vivo" else ""
            condiciones = m.get("condiciones") or []
            cond_str = f" (condiciones: {', '.join(condiciones)})" if condiciones else ""
            lines.append(
                f"- {icono_str}{name} ({grupo}){amenaza_str}{estado_str}{cond_str}: {rol}{psyche_str}"
            )
        return "\n".join(lines)

    def get_active_fronts_summary(self) -> str:
        """Resumen de frentes activos para el contexto del narrador."""
        fronts = self.get_by_type("frente")
        if not fronts:
            return ""
        lines = []
        for f in fronts:
            m = f["meta"]
            name = m.get("nombre", "?")
            estado = m.get("estado", "?")
            escasez = m.get("escasez", "")
            lines.append(f"- {name} [{estado}]{': ' + escasez if escasez else ''}")
        return "\n".join(lines)

    def get_fronts_with_clocks(self) -> list[dict]:
        """
        Devuelve frentes con información de reloj para el panel de estado.
        Cada item: {"nombre": str, "estado": str, "escasez": str, "tick": int, "max": int}
        """
        fronts = self.get_by_type("frente")
        result = []
        for f in fronts:
            m = f["meta"]
            body = f["body"]
            # Solo casillas de checklist reales: \[.\] contaba falsos ticks
            # con [1], [a], etc. en el cuerpo del frente.
            checked = len(re.findall(r"\[[xX]\]", body))
            total = checked + len(re.findall(r"\[ \]", body))
            result.append({
                "nombre": m.get("nombre", "?"),
                "estado": m.get("estado", "latente"),
                "escasez": m.get("escasez", ""),
                "tick": checked,
                "max": total if total > 0 else 6,
            })
        return result

    def vault_is_empty(self) -> bool:
        return len(self._all_md_files()) == 0
