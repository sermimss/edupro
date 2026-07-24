import sqlite3
import threading
from datetime import datetime, timezone
from config import DB_PATH, log

_db_lock = threading.Lock()


def conectar():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=10000")
    return con


def inicializar_db():
    con = conectar()
    con.execute("""
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT NOT NULL,
            rol TEXT NOT NULL,
            contenido TEXT NOT NULL,
            creado_en TEXT NOT NULL
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_historial_numero ON historial(numero)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS mensajes_procesados (
            wamid TEXT PRIMARY KEY,
            procesado_en TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()


def guardar_mensaje(numero: str, rol: str, contenido: str):
    with _db_lock:
        con = conectar()
        try:
            con.execute(
                "INSERT INTO historial (numero, rol, contenido, creado_en) VALUES (?, ?, ?, ?)",
                (numero, rol, contenido, datetime.now(timezone.utc).isoformat()),
            )
            con.commit()
        finally:
            con.close()


def obtener_historial(numero: str, limite: int = None):
    if limite is None:
        from config import VENTANA_HISTORIAL
        limite = VENTANA_HISTORIAL
    con = conectar()
    try:
        filas = con.execute(
            "SELECT rol, contenido FROM historial WHERE numero = ? ORDER BY id DESC LIMIT ?",
            (numero, limite),
        ).fetchall()
    finally:
        con.close()
    filas.reverse()
    return [{"role": rol, "content": contenido} for rol, contenido in filas]


def limpiar_historial_antiguo(numero: str):
    from config import DIAS_RETENCION_HISTORIAL, MAX_GUARDADOS_POR_NUMERO
    with _db_lock:
        con = conectar()
        try:
            con.execute(
                """
                DELETE FROM historial
                WHERE numero = ? AND id NOT IN (
                    SELECT id FROM historial WHERE numero = ? ORDER BY id DESC LIMIT ?
                )
                """,
                (numero, numero, MAX_GUARDADOS_POR_NUMERO),
            )
            con.execute(
                "DELETE FROM historial WHERE creado_en < datetime('now', ?)",
                (f"-{DIAS_RETENCION_HISTORIAL} days",),
            )
            con.commit()
        finally:
            con.close()


def ya_procesado(wamid: str) -> bool:
    if not wamid:
        return False
    con = conectar()
    try:
        fila = con.execute(
            "SELECT 1 FROM mensajes_procesados WHERE wamid = ?", (wamid,)
        ).fetchone()
    finally:
        con.close()
    return fila is not None


def marcar_procesado(wamid: str):
    if not wamid:
        return
    with _db_lock:
        con = conectar()
        try:
            con.execute(
                "INSERT INTO mensajes_procesados (wamid, procesado_en) VALUES (?, ?)",
                (wamid, datetime.now(timezone.utc).isoformat()),
            )
            con.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            con.close()


def limpiar_mensajes_procesados_antiguos():
    with _db_lock:
        con = conectar()
        try:
            con.execute(
                "DELETE FROM mensajes_procesados WHERE procesado_en < datetime('now', '-7 days')"
            )
            con.commit()
        finally:
            con.close()


inicializar_db()
