# Prime Business Credit — Flat Flask App

## Quickstart (Render or local)

- **Start command**: `gunicorn -w 2 -k gthread -t 180 app:app`
- **Env (optional)**:
  - `FLASK_SECRET_KEY` (any string)
  - `DEFAULT_ADMIN_PASSWORD` (defaults to `admin123`)
  - `DEFAULT_USER_PASSWORD` (defaults to `user123`)

### Local
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```
