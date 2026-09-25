"""MySQL (via SQLAlchemy) models for scan history / catalog / analytics."""
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Scan(db.Model):
    __tablename__ = "scans"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), default="")
    image_path = db.Column(db.String(512), default="")
    codes_found = db.Column(db.Integer, default=0)
    barcodes = db.Column(db.Integer, default=0)
    qr_codes = db.Column(db.Integer, default=0)
    engine = db.Column(db.String(64), default="ZXing-Java engine")
    ml_error = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    results = db.relationship("ScanResult", backref="scan",
                              cascade="all, delete-orphan", lazy=True)

    def to_dict(self, include_results=True):
        d = {
            "id": self.id,
            "filename": self.filename,
            "codes_found": self.codes_found,
            "barcodes": self.barcodes,
            "qr_codes": self.qr_codes,
            "engine": self.engine,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_results:
            d["results"] = [r.to_dict() for r in self.results]
        return d


class ScanResult(db.Model):
    __tablename__ = "scan_results"

    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scans.id"), nullable=False)
    code_index = db.Column(db.Integer, default=1)
    code_type = db.Column(db.String(32), default="BARCODE")  # BARCODE | QR
    code_format = db.Column(db.String(64), default="Barcode")
    data = db.Column(db.Text, default="")
    valid = db.Column(db.Boolean, default=False)
    note = db.Column(db.String(255), default="")
    confidence = db.Column(db.Float, default=0.0)

    def to_dict(self):
        return {
            "id": self.code_index,
            "type": self.code_type,
            "format": self.code_format,
            "data": self.data,
            "valid": bool(self.valid),
            "note": self.note,
            "confidence": self.confidence,
        }


class Product(db.Model):
    """Simple product catalog rows users can link to decoded values."""
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255), default="")
    brand = db.Column(db.String(255), default="")
    category = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"id": self.id, "code": self.code, "name": self.name,
                "brand": self.brand, "category": self.category}
