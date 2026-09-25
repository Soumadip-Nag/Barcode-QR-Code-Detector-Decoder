"""Central configuration. All secrets come from environment variables."""
import os


def _get(name, default=""):
    return os.environ.get(name, default)


# Roboflow YOLO model (from your original script)
ROBOFLOW_API_KEY = _get("ROBOFLOW_API_KEY", "fiej1fU8ihvQtoo5V3mo")
ROBOFLOW_PROJECT = _get("ROBOFLOW_PROJECT", "barcode-qr-code-detection-mine")
ROBOFLOW_VERSION = int(_get("ROBOFLOW_VERSION", "4"))

ROBOFLOW_CONFIDENCE = int(_get("ROBOFLOW_CONFIDENCE", "40"))
ROBOFLOW_OVERLAP = int(_get("ROBOFLOW_OVERLAP", "30"))

# Flask
SECRET_KEY = _get("SECRET_KEY", "barcode-reader-dev-secret")
MAX_UPLOAD_MB = int(_get("MAX_UPLOAD_MB", "10"))

# ---- Database: MySQL (primary) with SQLite fallback for local/Vercel demo ----
# Set either DATABASE_URL or the MYSQL_* parts below.
# Example MySQL URL: mysql+pymysql://user:pass@localhost:3306/barcode_db
MYSQL_HOST = _get("MYSQL_HOST", "localhost")
MYSQL_PORT = _get("MYSQL_PORT", "3306")
MYSQL_USER = _get("MYSQL_USER", "root")
MYSQL_PASSWORD = _get("MYSQL_PASSWORD", "")
MYSQL_DB = _get("MYSQL_DB", "barcode_db")

DATABASE_URL = _get("DATABASE_URL", "")
if not DATABASE_URL:
    # Use MySQL only when explicitly configured (password given or
    # MYSQL_USE=1); otherwise local SQLite so the app runs out-of-the-box.
    _want_mysql = bool(MYSQL_PASSWORD) or _get("MYSQL_USE", "0") == "1"
    if _want_mysql:
        DATABASE_URL = (
            f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
            f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
        )
    elif _get("VERCEL", ""):
        # Vercel serverless FS is read-only except /tmp: ephemeral sqlite
        # unless a hosted MySQL DATABASE_URL is provided.
        DATABASE_URL = "sqlite:////tmp/barcode.db"
    else:
        DATABASE_URL = "sqlite:///barcode.db"

SQLALCHEMY_DATABASE_URI = DATABASE_URL
SQLALCHEMY_TRACK_MODIFICATIONS = False
