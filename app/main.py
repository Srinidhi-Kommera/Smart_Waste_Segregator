from __future__ import annotations

import base64
import hashlib
import io
import sqlite3
import argparse
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torchvision import models, transforms
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "sortwise.db"
STATIC_DIR = ROOT / "static"
MODEL_PATH = ROOT / "app" / "waste_model.pth"

app = FastAPI(title="SortWise API", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

CATEGORIES = {
    "plastic": {"label": "Recyclable · Plastic", "route": "Blue recycling bin", "tip": "Empty and rinse containers before recycling.", "tone": "blue"},
    "paper": {"label": "Recyclable · Paper & Cardboard", "route": "Paper recycling bin", "tip": "Keep paper dry and flatten cardboard.", "tone": "amber"},
    "metal": {"label": "Recyclable · Metal", "route": "Metal recycling bin", "tip": "Rinse cans and keep sharp metal safely contained.", "tone": "slate"},
    "glass": {"label": "Recyclable · Glass", "route": "Glass recycling bin", "tip": "Remove food residue; handle broken glass carefully.", "tone": "green"},
    "organic": {"label": "Organic / Biodegradable", "route": "Green compost bin", "tip": "Food scraps and garden waste belong in compost.", "tone": "green"},
    "hazardous": {"label": "Hazardous / E-waste", "route": "Hazardous-waste collection point", "tip": "Never place batteries or electronics in household bins.", "tone": "red"},
    "general": {"label": "General / Non-recyclable", "route": "General waste bin", "tip": "Use only when the item cannot be safely separated.", "tone": "charcoal"},
}
for _category, _route, _color, _recyclable in [
    ("plastic", "Blue bin", "blue", True), ("paper", "Blue bin", "blue", True),
    ("metal", "Blue bin", "blue", True), ("glass", "Green bin", "green", True),
    ("organic", "Green bin", "green", True), ("hazardous", "Red bin / approved collection point", "red", False),
    ("general", "Red bin", "red", False),
]:
    CATEGORIES[_category].update(route=_route, bin_color=_color, recyclable=_recyclable)

class ClassifyRequest(BaseModel):
    image: str = Field(..., description="Base64 data URL from camera or file upload")
    hint: Literal["auto", "plastic", "paper", "metal", "glass", "organic", "hazardous", "general"] = "auto"

# The trained model only knows TrashNet's 6 classes (v2 scope decision: no organic/
# hazardous data yet). Map each TrashNet label onto the closest existing app category.
TRASHNET_TO_CATEGORY = {
    "cardboard": "paper",
    "glass": "glass",
    "metal": "metal",
    "paper": "paper",
    "plastic": "plastic",
    "trash": "general",
}

IMG_SIZE = 224
INFERENCE_TRANSFORM = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                          std=[0.229, 0.224, 0.225]),
])

_model: nn.Module | None = None
_trashnet_classes: list[str] = []
_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def load_model() -> None:
    """Load the fine-tuned MobileNetV2 checkpoint once, at startup."""
    global _model, _trashnet_classes
    if not MODEL_PATH.exists():
        # Model file missing — fall back gracefully instead of crashing the whole app.
        print(f"WARNING: {MODEL_PATH} not found. Falling back to placeholder classifier.")
        return
    checkpoint = torch.load(MODEL_PATH, map_location=_device)
    _trashnet_classes = checkpoint["class_names"]

    model = models.mobilenet_v2(weights=None)
    model.classifier[1] = nn.Linear(model.last_channel, len(_trashnet_classes))
    model.load_state_dict(checkpoint["state_dict"])
    model.to(_device)
    model.eval()
    _model = model
    print(f"Loaded waste_model.pth with classes: {_trashnet_classes}")

def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def initialise_database() -> None:
    with closing(connect()) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            category TEXT NOT NULL,
            confidence REAL NOT NULL,
            review_required INTEGER NOT NULL,
            image_hash TEXT NOT NULL
        )""")
        db.commit()

@app.on_event("startup")
def startup() -> None:
    initialise_database()
    load_model()

def classify(image_data: str, hint: str) -> tuple[str, float]:
    """Runs the fine-tuned MobileNetV2 model on the uploaded image.

    Falls back to the old hash placeholder only if the model file failed to load,
    so the app never hard-crashes if waste_model.pth is missing.
    """
    try:
        raw = image_data.split(",", 1)[1] if "," in image_data else image_data
        payload = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise HTTPException(400, "Please provide a valid base64 image.") from exc
    if len(payload) < 100:
        raise HTTPException(400, "The image file is too small to classify.")
    if hint != "auto":
        return hint, 0.93

    if _model is None:
        # Model didn't load — old placeholder behaviour as a safety net.
        digest = hashlib.sha256(payload).digest()
        category = list(CATEGORIES)[digest[0] % len(CATEGORIES)]
        confidence = round(0.55 + (digest[1] / 255) * 0.34, 2)
        return category, confidence

    try:
        image = Image.open(io.BytesIO(payload)).convert("RGB")
    except Exception as exc:
        raise HTTPException(400, "Could not read this file as an image.") from exc

    tensor = INFERENCE_TRANSFORM(image).unsqueeze(0).to(_device)
    with torch.no_grad():
        logits = _model(tensor)
        probs = F.softmax(logits, dim=1).squeeze(0)
        top_idx = int(torch.argmax(probs).item())
        confidence = round(float(probs[top_idx].item()), 2)

    trashnet_label = _trashnet_classes[top_idx]
    category = TRASHNET_TO_CATEGORY.get(trashnet_label, "general")
    return category, confidence

@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "sortwise"}

@app.post("/api/classify")
def classify_event(request: ClassifyRequest) -> dict:
    category, confidence = classify(request.image, request.hint)
    review_required = confidence < 0.7
    now = datetime.now(timezone.utc).isoformat()
    image_hash = hashlib.sha256(request.image.encode()).hexdigest()[:16]
    with closing(connect()) as db:
        cursor = db.execute(
            "INSERT INTO events (created_at, category, confidence, review_required, image_hash) VALUES (?, ?, ?, ?, ?)",
            (now, category, confidence, int(review_required), image_hash),
        )
        db.commit()
    details = CATEGORIES[category]
    return {"id": cursor.lastrowid, "created_at": now, "category": category, "confidence": confidence, "review_required": review_required, "suggestions": details["tip"], **details}

@app.get("/api/events")
def events(limit: int = 8) -> list[dict]:
    limit = max(1, min(limit, 50))
    with closing(connect()) as db:
        rows = db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]

@app.get("/api/stats")
def stats() -> dict:
    with closing(connect()) as db:
        total = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        review = db.execute("SELECT COUNT(*) FROM events WHERE review_required = 1").fetchone()[0]
        rows = db.execute("SELECT category, COUNT(*) AS count FROM events GROUP BY category").fetchall()
    distribution = {key: 0 for key in CATEGORIES}
    distribution.update({row["category"]: row["count"] for row in rows})
    return {"total": total, "review_required": review, "distribution": distribution}

def reset_database() -> None:
    """Create the schema if needed and remove all saved classification history."""
    initialise_database()
    with closing(connect()) as db:
        db.execute("DELETE FROM events")
        db.execute("DELETE FROM sqlite_sequence WHERE name = 'events'")
        db.commit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SortWise database maintenance")
    parser.add_argument("--reset-db", action="store_true", help="delete all saved classification events and start the log over")
    args = parser.parse_args()
    if args.reset_db:
        reset_database()
        print(f"Classification history cleared from {DB_PATH}")
    else:
        parser.print_help()
