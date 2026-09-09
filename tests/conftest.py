import atexit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
atexit.register(lambda: os.path.exists(_db_path) and os.remove(_db_path))

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("META_TOKEN", "test-meta-token")
os.environ.setdefault("PHONE_NUMBER_ID", "123456")
os.environ.setdefault("NUMERO_ASESOR", "5210000000000")
os.environ.setdefault("META_APP_SECRET", "testsecret")
os.environ.setdefault("VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("HISTORIAL_DB_PATH", _db_path)
