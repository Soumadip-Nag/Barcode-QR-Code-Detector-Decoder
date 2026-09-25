# Barcode & QR Code Detector / Decoder

Web app (Flask) matching the shared Scanner UI. Backend keeps your full pipeline functional:

- **ML detection:** Roboflow YOLO (`barcode-qr-code-detection-mine` v4) via API
- **Decoding:** `pyzxing` (**ZXing-Java** port, `BarCodeReader`, `try_harder=True`) + your 6-stage OpenCV enhancement + 4-angle rotation retry
- **Database:** MySQL (SQLAlchemy) — scans / scan_results / products
- **Frontend:** Scanner (upload + live camera), Scan history, Product catalog, Analytics — pure HTML/CSS/JS

## Run locally (Windows)

```powershell
cd "C:\Users\Soumadip Nag\Documents\Default Project\Barcode&QRCodeDetect-and-Decode"
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# MySQL (XAMPP / MySQL Server): create DB then import schema
mysql -u root -e "CREATE DATABASE IF NOT EXISTS barcode_db CHARACTER SET utf8mb4;"
mysql -u root barcode_db < schema.sql

# env (PowerShell)
$env:MYSQL_HOST="localhost"; $env:MYSQL_USER="root"; $env:MYSQL_PASSWORD=""; $env:MYSQL_DB="barcode_db"
$env:ROBOFLOW_API_KEY="fiej1fU8ihvQtoo5V3mo"
python app.py
# open http://localhost:5000
```

Without MySQL the app falls back to `barcode.db` (SQLite) so it still runs.

## Deploy on Vercel (24/7)

1. Push this folder to GitHub: `Soumadip-Nag/Barcode-QR-Code-Detector-Decoder`
2. Vercel → New Project → import that repo. Framework: Other. Entry: `api/index.py` (see `vercel.json`).
3. Environment variables: `ROBOFLOW_API_KEY`, `DATABASE_URL` (use a hosted MySQL, e.g. PlanetScale/Aiven: `mysql+pymysql://user:pass@host:3306/barcode_db`), `SECRET_KEY`.
4. Deploy. Vercel keeps it online 24/7 on its edge network.

> Note: Vercel serverless has no Java runtime, so `pyzxing` is attempted first and the app gracefully supplements with OpenCV decode there. On your PC / any VM with Java, pure ZXing-Java path is used.

## API

- `POST /api/scan` (multipart `image`) → `{scan_id, summary, detections[], annotated_image, engine}`
- `GET /api/history`, `DELETE /api/history`
- `GET/POST /api/catalog`
- `GET /api/analytics`, `GET /health`
