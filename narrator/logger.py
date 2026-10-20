import logging
import sys


def setup_logger(name: str = "narrator") -> logging.Logger:
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)
        # En consola Windows (cp1252) un log con emoji/símbolos fuera de ese
        # charset (💡 ⚖ 🎲 🔴...) rompía el proceso con UnicodeEncodeError.
        # errors="replace" evita el crash (sustituye por "?") sin cambiar el
        # encoding real de stdout.
        stream = sys.stderr
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass
        handler = logging.StreamHandler(stream)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

# Instancia global por defecto
logger = setup_logger()
