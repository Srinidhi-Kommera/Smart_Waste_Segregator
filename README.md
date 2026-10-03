# SortWise — Smart Waste Segregation

SortWise is a first-version AI waste-sorting demo. It accepts a photo from a device camera or file picker, returns a disposal route, records the result in SQLite, and shows a lightweight operations dashboard.

## Run

```powershell
python -m uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000>.

The API is available at `/docs`. Classification in this starter is a deterministic demo scorer based on the uploaded file and optional material hint; replace `classify()` in `app/main.py` with a trained CV model when one is available. This keeps the UI, routing, review logic, analytics, and API stable while the model is developed.

## Endpoints

- `POST /api/classify` — classify and log a base64 image
- `GET /api/stats` — summary and category distribution
- `GET /api/events` — most recent classification events
- `GET /api/health` — service health

## Taxonomy

Plastic, paper/cardboard, metal, glass, organic, hazardous/e-waste, and general waste.
