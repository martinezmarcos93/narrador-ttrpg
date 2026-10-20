"""Servidor de la API/GUI web: ``python -m narrator.web``.

Escucha solo en 127.0.0.1 por defecto: para exponerlo, ponelo detrás de un
reverse proxy con HTTPS (ver docs/DEPLOY-WEB.md). Si ``waitress`` está
instalado se usa como servidor WSGI; si no, el servidor de werkzeug con aviso.
"""
from __future__ import annotations

import argparse
import os

from narrator.logger import logger


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("NARRATOR_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("NARRATOR_PORT", "8765")))
    args = parser.parse_args()

    from narrator.web.app import create_app

    app = create_app()
    try:
        from waitress import serve
    except ImportError:
        logger.warning("waitress no está instalado: uso el servidor de desarrollo de werkzeug")
        from werkzeug.serving import run_simple

        run_simple(args.host, args.port, app, threaded=True)
        return
    serve(app, host=args.host, port=args.port, threads=8)


if __name__ == "__main__":
    main()
