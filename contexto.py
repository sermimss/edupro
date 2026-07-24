import os
from config import RUTA_CONTEXTO, log

_contexto_cache = {"texto": "", "mtime": None}


def cargar_contexto():
    try:
        mtime_actual = os.path.getmtime(RUTA_CONTEXTO)
        if _contexto_cache["mtime"] != mtime_actual:
            with open(RUTA_CONTEXTO, "r", encoding="utf-8") as f:
                _contexto_cache["texto"] = f.read()
            _contexto_cache["mtime"] = mtime_actual
            log.info(f"📄 Hoja de contexto (re)cargada desde {RUTA_CONTEXTO}")
    except FileNotFoundError:
        log.error(f"⚠️ Archivo de contexto no encontrado: {RUTA_CONTEXTO}")
        _contexto_cache["texto"] = _contexto_cache["texto"] or ""
    return _contexto_cache["texto"]
