"""
Import/export de NPCs como SillyTavern V2 character card — PNG con chunk
tEXt "chara" (JSON del personaje codificado en base64), formato público
del ecosistema SillyTavern. Solo lee/escribe el chunk de datos; no genera
ni edita el arte del PNG. Sin dependencias nuevas (stdlib: zlib/struct/base64).
"""

import base64
import json
import struct
import zlib

from narrator.logger import logger

_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _read_chunks(data: bytes):
    """Generador de (tipo, contenido, offset_del_chunk) sobre un PNG."""
    pos = len(_SIGNATURE)
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        content = data[pos + 8:pos + 8 + length]
        yield ctype, content, pos
        pos += 12 + length


def _make_text_chunk(keyword: bytes, text: bytes) -> bytes:
    data = keyword + b"\x00" + text
    crc = zlib.crc32(b"tEXt" + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + b"tEXt" + data + struct.pack(">I", crc)


def write_chara_chunk(png_bytes: bytes, character: dict) -> bytes:
    """Devuelve una copia del PNG con un chunk tEXt "chara" (JSON del
    personaje en base64) insertado después de IHDR."""
    if not png_bytes.startswith(_SIGNATURE):
        raise ValueError("No es un PNG válido (falta firma).")
    encoded = base64.b64encode(json.dumps(character, ensure_ascii=False).encode("utf-8"))
    new_chunk = _make_text_chunk(b"chara", encoded)

    for ctype, _content, offset in _read_chunks(png_bytes):
        if ctype == b"IHDR":
            length = struct.unpack(">I", png_bytes[offset:offset + 4])[0]
            insert_at = offset + 12 + length
            return png_bytes[:insert_at] + new_chunk + png_bytes[insert_at:]
    raise ValueError("PNG sin chunk IHDR.")


def read_chara_chunk(png_bytes: bytes) -> "dict | None":
    """Lee el chunk tEXt "chara" de un PNG y devuelve el JSON decodificado.
    None si no existe el chunk, no es un PNG válido o el contenido está
    corrupto (nunca lanza)."""
    if not png_bytes.startswith(_SIGNATURE):
        return None
    for ctype, content, _offset in _read_chunks(png_bytes):
        if ctype == b"tEXt" and content.startswith(b"chara\x00"):
            try:
                decoded = base64.b64decode(content[len(b"chara\x00"):])
                return json.loads(decoded.decode("utf-8"))
            except Exception as e:
                logger.warning("Chunk 'chara' de la card PNG ilegible: %s", e)
                return None
    return None
