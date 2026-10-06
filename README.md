# SortWise — Smart Waste Segregation

SortWise is a first-version AI waste-sorting demo. It accepts a photo from a device camera or file picker, returns a disposal route, records the result in SQLite, and shows a lightweight operations dashboard.

## Run

```powershell
python -m uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000>.

The API is available at `/docs`. The page classifies uploaded images automatically, records category/confidence/timestamp in SQLite, and returns bin and disposal suggestions. TrashNet has six model classes; organic and hazardous are not model predictions in this version. Bin colors are examples and can vary by local collection rules.

To clear all classification history and restart the event IDs, stop the server and run:

```powershell
python -m app.main --reset-db
```

This deletes all saved scan events from `data/sortwise.db`; it does not delete the database file or model.

## Endpoints

- `POST /api/classify` — classify and log a base64 image
- `GET /api/stats` — summary and category distribution
- `GET /api/events` — most recent classification events
- `GET /api/health` — service health

## Taxonomy

Plastic, paper/cardboard, metal, glass, organic, hazardous/e-waste, and general waste.
