"""Flask backend: Roboflow YOLO detection + pyzxing-Java decode + MySQL."""
import os
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

import config
from detector import ZXING_ENGINE, annotated_base64, scan_image_bytes
from models import Product, Scan, ScanResult, db

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"}


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = config.SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024

    CORS(app)
    db.init_app(app)

    upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    with app.app_context():
        db.create_all()
        if Product.query.count() == 0:
            db.session.add_all([
                Product(code="0128016691675", name="Demo Milk 1L",
                        brand="Demo Dairy", category="Grocery"),
                Product(code="4606453849072", name="Demo Biscuits 400g",
                        brand="Demo Foods", category="Grocery"),
            ])
            db.session.commit()

    # ---------- Pages ----------
    @app.get("/")
    def index():
        return render_template("index.html", engine=ZXING_ENGINE)

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "engine": ZXING_ENGINE})

    @app.get("/uploads/<path:name>")
    def uploads(name):
        return send_from_directory(upload_dir, name)

    # ---------- Scan ----------
    @app.post("/api/scan")
    def api_scan():
        if "image" not in request.files:
            return jsonify({"error": "No image file (field 'image')"}), 400
        f = request.files["image"]
        if not f or not f.filename:
            return jsonify({"error": "Empty filename"}), 400
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in ALLOWED_EXT:
            return jsonify({"error": f"Unsupported type .{ext}"}), 400

        raw = f.read()
        if not raw:
            return jsonify({"error": "Empty file"}), 400

        use_ml = request.form.get("use_ml", "1") != "0"
        try:
            detections, annotated, meta = scan_image_bytes(raw, use_ml=use_ml)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"Scan failed: {exc}"}), 500

        # Persist upload + results (MySQL)
        fname = f"{uuid.uuid4().hex}_{secure_filename(f.filename)}"
        try:
            with open(os.path.join(upload_dir, fname), "wb") as fh:
                fh.write(annotated)
        except OSError:
            fname = ""

        barcodes = sum(1 for d in detections if d["type"] == "BARCODE")
        qrs = sum(1 for d in detections if d["type"] == "QR")
        scan = Scan(filename=f.filename, image_path=fname,
                    codes_found=len(detections), barcodes=barcodes,
                    qr_codes=qrs, engine=ZXING_ENGINE,
                    ml_error=(meta.get("ml_error") or "")[:2000])
        try:
            db.session.add(scan)
            db.session.flush()
            for d in detections:
                db.session.add(ScanResult(
                    scan_id=scan.id, code_index=d["id"],
                    code_type=d["type"], code_format=d["format"],
                    data=d["data"][:2000], valid=d["valid"],
                    note=d["note"][:255], confidence=d["confidence"]))
            db.session.commit()
            scan_id = scan.id
        except Exception as exc:
            db.session.rollback()
            print("DB save failed:", exc)
            scan_id = None

        summary = (f"{len(detections)} code(s) detected "
                   f"({barcodes} barcode(s), {qrs} QR)")
        return jsonify({
            "scan_id": scan_id,
            "summary": summary,
            "barcodes": barcodes,
            "qr_codes": qrs,
            "detections": detections,
            "annotated_image": "data:image/jpeg;base64," + annotated_base64(annotated),
            "engine": ZXING_ENGINE,
            "ml_error": meta.get("ml_error"),
        })

    # ---------- History ----------
    @app.get("/api/history")
    def api_history():
        limit = min(int(request.args.get("limit", 50)), 200)
        scans = (Scan.query.order_by(Scan.id.desc()).limit(limit).all())
        return jsonify([s.to_dict() for s in scans])

    @app.delete("/api/history")
    def api_history_clear():
        try:
            ScanResult.query.delete()
            Scan.query.delete()
            db.session.commit()
            return jsonify({"ok": True})
        except Exception as exc:
            db.session.rollback()
            return jsonify({"error": str(exc)}), 500

    # ---------- Catalog ----------
    @app.get("/api/catalog")
    def api_catalog():
        q = (request.args.get("q") or "").strip()
        query = Product.query
        if q:
            like = f"%{q}%"
            query = query.filter(
                (Product.code.like(like)) | (Product.name.like(like)))
        return jsonify([p.to_dict()
                        for p in query.order_by(Product.id.desc()).limit(100)])

    @app.post("/api/catalog")
    def api_catalog_add():
        body = request.get_json(force=True, silent=True) or {}
        code = (body.get("code") or "").strip()
        if not code:
            return jsonify({"error": "code is required"}), 400
        if Product.query.filter_by(code=code).first():
            return jsonify({"error": "code already exists"}), 409
        p = Product(code=code, name=body.get("name", "")[:255],
                    brand=body.get("brand", "")[:255],
                    category=body.get("category", "")[:255])
        db.session.add(p)
        db.session.commit()
        return jsonify(p.to_dict()), 201

    # ---------- Analytics ----------
    @app.get("/api/analytics")
    def api_analytics():
        total_scans = Scan.query.count()
        total_codes = sum(s.codes_found for s in Scan.query.all()) or 0
        total_qr = sum(s.qr_codes for s in Scan.query.all()) or 0
        total_bc = sum(s.barcodes for s in Scan.query.all()) or 0
        ok = ScanResult.query.filter_by(valid=True).count()
        total_res = ScanResult.query.count()
        recent = [s.to_dict(include_results=False)
                  for s in Scan.query.order_by(Scan.id.desc()).limit(7)]
        return jsonify({
            "total_scans": total_scans,
            "total_codes": total_codes,
            "barcodes": total_bc,
            "qr_codes": total_qr,
            "success_rate": round(100 * ok / total_res, 1) if total_res else 0,
            "recent": recent,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
