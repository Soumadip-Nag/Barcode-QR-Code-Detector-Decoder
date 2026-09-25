"""Detection + decode engine.

Port of the original desktop script, kept fully functional:
  - Roboflow YOLO model via API  (ML detection)
  - pyzxing (ZXing-Java port)     (decoding)
  - OpenCV enhancement pipeline   (contrast / denoise / sharpen / upscale / threshold)
  - 4-angle rotation retry        (0 / 90 / 180 / 270)

Web adaptation: instead of cv2.imshow / input(), this module exposes
`scan_image_bytes()` which returns JSON-serialisable detections plus an
annotated JPEG (bytes). A `process_image()` CLI wrapper with the same
console output as the original script is kept at the bottom.
"""
import base64
import os
import tempfile
import warnings

import cv2
import numpy as np

warnings.filterwarnings("ignore")

from config import (
    ROBOFLOW_API_KEY,
    ROBOFLOW_CONFIDENCE,
    ROBOFLOW_OVERLAP,
    ROBOFLOW_PROJECT,
    ROBOFLOW_VERSION,
)

# ============================
# ZXING DECODER (pyzxing-Java)
# ============================
try:
    from pyzxing import BarCodeReader
    _reader = BarCodeReader()
    ZXING_ENGINE = "ZXing-Java engine"
    ZXING_AVAILABLE = True
except Exception as exc:  # Java missing etc.
    _reader = None
    ZXING_ENGINE = f"ZXing-Java engine (unavailable: {exc})"
    ZXING_AVAILABLE = False

# Optional fallbacks (never replace pyzxing, only supplement it)
try:
    from pyzbar.pyzbar import decode as _pyzbar_decode  # needs zbar DLL
    PYZBAR_AVAILABLE = True
except Exception:
    _pyzbar_decode = None
    PYZBAR_AVAILABLE = False

_qr_detector = cv2.QRCodeDetector()

_model = None
_model_error = None


def get_model():
    """Lazy-load the Roboflow model so `import` never needs network."""
    global _model, _model_error
    if _model is not None:
        return _model
    if _model_error is not None:
        return None
    try:
        from roboflow import Roboflow
        rf = Roboflow(api_key=ROBOFLOW_API_KEY)
        project = rf.workspace().project(ROBOFLOW_PROJECT)
        _model = project.version(ROBOFLOW_VERSION).model
        return _model
    except Exception as exc:
        _model_error = str(exc)
        return None


# ============================
# DISPLAY (desktop compat)
# ============================
def show_image_resized(window_name, image, max_width=1000, max_height=700):
    h, w = image.shape[:2]
    scale = min(max_width / w, max_height / h, 1)
    resized = cv2.resize(image, (int(w * scale), int(h * scale)))
    cv2.imshow(window_name, resized)


# ============================
# RESIZE FOR API
# ============================
def resize_for_api(image, max_dim=1024):
    h, w = image.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        return cv2.resize(image, (int(w * scale), int(h * scale))), scale
    return image, 1.0


# ============================
# ENHANCEMENT PIPELINE
# ============================
def enhance_for_decoding(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    contrast = cv2.convertScaleAbs(gray, alpha=2.2, beta=0)
    denoise = cv2.fastNlMeansDenoising(contrast, None, 10, 7, 21)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharp = cv2.filter2D(denoise, -1, kernel)
    upscaled = cv2.resize(sharp, None, fx=3, fy=3,
                          interpolation=cv2.INTER_CUBIC)
    thresh = cv2.adaptiveThreshold(
        upscaled, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2)
    return [gray, contrast, denoise, sharp, upscaled, thresh]


# ============================
# ROTATION
# ============================
def rotate_image(image, angle):
    if angle == 0:
        return image
    if angle == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return image


# ============================
# ZXING TEXT CONVERSION
# ============================
def convert_to_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("utf-8", errors="ignore")
    return str(value)


# ============================
# ZXING DECODE FUNCTION
# ============================
def decode_with_zxing(image):
    """Decode a (grayscale/BGR) image with pyzxing-Java. Returns raw list."""
    if not ZXING_AVAILABLE or _reader is None:
        return []
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png",
                                         delete=False) as temp_file:
            temp_path = temp_file.name
        success = cv2.imwrite(temp_path, image)
        if not success:
            return []
        results = _reader.decode(temp_path, try_harder=True)
        return results if results else []
    except Exception as e:
        print("ZXing Error:", e)
        return []
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _fallback_decode_opencv(image):
    """OpenCV QRCodeDetector fallback (QR codes only)."""
    try:
        gray = (cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                if len(image.shape) == 3 else image)
        ok, decoded, _pts, _qr = _qr_detector.detectAndDecodeMulti(gray)
        if ok and decoded:
            return [d for d in decoded if d]
        data, _pts, _qr = _qr_detector.detectAndDecode(gray)
        return [data] if data else []
    except Exception:
        return []


def _fallback_decode_pyzbar(image):
    if not PYZBAR_AVAILABLE or _pyzbar_decode is None:
        return []
    try:
        gray = (cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                if len(image.shape) == 3 else image)
        out = []
        for obj in (_pyzbar_decode(gray) or []):
            out.append({
                "parsed": obj.data,
                "raw": obj.data,
                "format": obj.type,
                "type": obj.type,
            })
        return out
    except Exception:
        return []


# ============================
# BEST DECODE SELECTOR
# ============================
def choose_best_decode(decoded_set):
    if not decoded_set:
        return "NOT DECODED"
    return max(decoded_set, key=len)


# ============================
# VALIDATION (matches frontend copy)
# ============================
def validate_ean13(code):
    digits = "".join(c for c in str(code) if c.isdigit())
    if len(digits) != 13:
        return False, "EAN-13 must be 13 digits"
    check = int(digits[-1])
    odd = sum(int(d) for d in digits[0:12:2])
    even = sum(int(d) for d in digits[1:12:2])
    calc = (10 - ((odd + 3 * even) % 10)) % 10
    if calc == check:
        return True, f"Modulo 10 check digit valid ({check})"
    return False, (f"Modulo 10 check digit invalid "
                   f"(expected {calc}, got {check})")


def classify_format(fmt, text):
    f = (fmt or "").upper()
    if "QR" in f:
        return "QR", "QR Code"
    digits = "".join(c for c in str(text) if c.isdigit())
    if len(digits) == 13 and f in ("", "EAN_13", "EAN-13"):
        return "BARCODE", "EAN-13"
    if "EAN" in f or "UPC" in f or "CODE" in f or "BAR" in f:
        return "BARCODE", fmt or "Barcode"
    # Heuristic: long numeric -> barcode, else QR
    if text and len(str(text).strip()) > 0:
        t = str(text).strip()
        if t.isdigit() and len(t) >= 8:
            return "BARCODE", fmt or "Barcode"
        if len(t) > 40 or "http" in t.lower():
            return "QR", "QR Code"
    return ("QR" if "QR" in f else "BARCODE"), fmt or "Barcode"


# ============================
# CORE: bytes in -> detections + annotated image
# ============================
def scan_image_bytes(image_bytes, use_ml=True):
    """Run ML detection + ZXing decode. Returns (detections, annotated_jpg)."""
    arr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image file")
    h_img, w_img = image.shape[:2]

    boxes = []  # (x1,y1,x2,y2,label,confidence,source)
    ml_error = None

    # ---------- ML DETECTION (Roboflow YOLO) ----------
    if use_ml:
        model = get_model()
        if model is None:
            ml_error = _model_error or "Roboflow model unavailable"
        else:
            resized_img, scale = resize_for_api(image)
            with tempfile.NamedTemporaryFile(suffix=".jpg",
                                             delete=False) as tf:
                temp_path = tf.name
            try:
                cv2.imwrite(temp_path, resized_img)
                result = model.predict(
                    temp_path,
                    confidence=ROBOFLOW_CONFIDENCE,
                    overlap=ROBOFLOW_OVERLAP).json()
                for pred in result.get("predictions", []):
                    x = int(pred["x"] / scale)
                    y = int(pred["y"] / scale)
                    w = int(pred["width"] / scale)
                    h = int(pred["height"] / scale)
                    label = str(pred.get("class", "barcode")).lower()
                    conf = float(pred.get("confidence", 0))
                    pad = 20
                    x1 = max(0, int(x - w / 2) - pad)
                    y1 = max(0, int(y - h / 2) - pad)
                    x2 = min(w_img, int(x + w / 2) + pad)
                    y2 = min(h_img, int(y + h / 2) + pad)
                    boxes.append((x1, y1, x2, y2, label, conf, "ml"))
            except Exception as exc:
                ml_error = str(exc)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

    # ---------- Fallback: whole image if ML found nothing ----------
    if not boxes:
        boxes.append((0, 0, w_img, h_img, "fallback", 0.0, "full-image"))

    seen = set()
    detections = []
    idx = 0
    for (x1, y1, x2, y2, label, conf, src) in boxes:
        key = (x1 // 30, y1 // 30)
        if key in seen:
            continue
        seen.add(key)
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        decoded = {}   # text -> format string
        variants = enhance_for_decoding(crop)
        tried_fallback = False
        for img in variants:
            for angle in (0, 90, 180, 270):
                rotated = rotate_image(img, angle)
                for obj in decode_with_zxing(rotated):
                    parsed = obj.get("parsed")
                    raw = obj.get("raw")
                    text = convert_to_text(parsed if parsed else raw)
                    if not text:
                        continue
                    fmt = convert_to_text(
                        obj.get("format") or obj.get("type") or "")
                    decoded[text] = fmt.upper() or decoded.get(text, "")
                if not tried_fallback:
                    # cheap supplement: pyzbar dicts + opencv strings
                    for fb in _fallback_decode_pyzbar(rotated):
                        t = convert_to_text(
                            fb.get("parsed") or fb.get("raw"))
                        if t and t not in decoded:
                            decoded[t] = str(
                                fb.get("format", "")).upper()
                    for t in _fallback_decode_opencv(rotated):
                        if t and t not in decoded:
                            decoded[t] = decoded.get(t, "QR_CODE")
            if decoded:
                break
            tried_fallback = True

        idx += 1
        if decoded:
            best = choose_best_decode(set(decoded.keys()))
            fmt = decoded.get(best, "")
            det_type, fmt_label = classify_format(fmt, best)
        else:
            best = "NOT DECODED"
            det_type = label.upper() if label in (
                "qr", "barcode") else "BARCODE"
            if det_type == "QR":
                det_type = "QR"
            fmt_label = "QR Code" if det_type == "QR" else "Barcode"

        if det_type == "QR":
            valid, note = True, "Checksum not required for QR Code"
            fmt_label = fmt_label if "QR" in fmt_label else "QR Code"
        else:
            digits = "".join(c for c in best if c.isdigit())
            if best != "NOT DECODED" and len(digits) == 13:
                valid, note = validate_ean13(best)
                fmt_label = "EAN-13"
            elif best != "NOT DECODED":
                valid, note = True, "Decoded"
            else:
                valid, note = False, "No data decoded"

        detections.append({
            "id": idx,
            "type": det_type,
            "format": fmt_label,
            "data": best,
            "valid": bool(valid),
            "note": note,
            "confidence": round(conf, 2),
            "bbox": [int(x1), int(y1), int(x2), int(y2)],
            "source": src,
        })

        color = (0, 255, 0) if best != "NOT DECODED" else (0, 0, 255)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        cv2.putText(image, f"ID {idx}", (x1, max(0, y1 - 30)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 3)
        cv2.putText(image, f"{det_type} ({conf:.2f})", (x1, max(0, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    ok, buf = cv2.imencode(".jpg", image)
    annotated = buf.tobytes() if ok else image_bytes
    meta = {"ml_error": ml_error, "zxing": ZXING_ENGINE}
    return detections, annotated, meta


def annotated_base64(jpg_bytes):
    return base64.b64encode(jpg_bytes).decode("ascii")


# ============================
# CLI (original behaviour)
# ============================
def process_image(image_path):
    image = cv2.imread(image_path)
    if image is None:
        print("Image not found")
        return
    with open(image_path, "rb") as fh:
        detections, annotated, _meta = scan_image_bytes(fh.read())
    print("\n===== FINAL OUTPUT =====")
    if not detections:
        print("Neither barcode nor QR code detected")
        return
    for d in detections:
        print(f"Object {d['id']}: {d['type']} detected, "
              f"Decode: {d['data']}")
    show_image_resized("Final Result",
                       cv2.imdecode(np.frombuffer(annotated, np.uint8),
                                    cv2.IMREAD_COLOR))
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    path = input("Enter image path: ")
    process_image(path)
