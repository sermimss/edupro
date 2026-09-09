import os
import sys
import logging
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests

load_dotenv()

# Configuración de codificación para Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
        sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
    except AttributeError:
        pass

LOG_FILE = os.environ.get("LOG_FILE")
log_handlers = [logging.StreamHandler()]
if LOG_FILE:
    log_handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=log_handlers,
)
log = logging.getLogger("cess_bot")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_CONTEXTO = os.environ.get("RUTA_CONTEXTO", os.path.join(BASE_DIR, "contextoies.md"))

API_VERSION = "v25.0"

VARIABLES_REQUERIDAS = [
    "OPENAI_API_KEY",
    "META_TOKEN",
    "PHONE_NUMBER_ID",
    "NUMERO_ASESOR",
    "META_APP_SECRET",
]

faltantes = [v for v in VARIABLES_REQUERIDAS if not os.environ.get(v)]
if faltantes:
    log.error(f"❌ Faltan variables de entorno obligatorias: {', '.join(faltantes)}")
    sys.exit(1)

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
META_TOKEN = os.environ["META_TOKEN"]
PHONE_NUMBER_ID = os.environ["PHONE_NUMBER_ID"]
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "vibecode")
if VERIFY_TOKEN == "vibecode":
    log.warning(
        "⚠️ VERIFY_TOKEN sigue en su valor por defecto ('vibecode'). "
        "Configura un valor único en producción para evitar que sea adivinado."
    )
NUMERO_ASESOR = os.environ["NUMERO_ASESOR"]
META_APP_SECRET = os.environ["META_APP_SECRET"]

VENTANA_HISTORIAL = int(os.environ.get("VENTANA_HISTORIAL", "10"))
MAX_GUARDADOS_POR_NUMERO = 30
DIAS_RETENCION_HISTORIAL = int(os.environ.get("DIAS_RETENCION_HISTORIAL", "90"))

DB_PATH = os.environ.get("HISTORIAL_DB_PATH", "/tmp/historial_cess.db")
PORT = int(os.environ.get("PORT", "5000"))
ASISTENTE_INSCRIPCION_NUMERO = os.environ.get("ASISTENTE_INSCRIPCION_NUMERO", "6142015283")
ASISTENTE_INSCRIPCION_WA = os.environ.get("ASISTENTE_INSCRIPCION_WA", "526142015283")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_STORE_RESPONSES = os.environ.get("OPENAI_STORE_RESPONSES", "false").lower() in ("1", "true", "yes")
OPENAI_TIMEOUT = float(os.environ.get("OPENAI_TIMEOUT", "60"))
META_BASE_URL = "https://graph.facebook.com"
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "15"))
REQUEST_RETRIES = int(os.environ.get("REQUEST_RETRIES", "2"))

executor = ThreadPoolExecutor(max_workers=int(os.environ.get("MAX_WORKERS", "8")))

session = requests.Session()
retry_strategy = Retry(
    total=3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["POST", "GET"],
    backoff_factor=0.5,
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)
