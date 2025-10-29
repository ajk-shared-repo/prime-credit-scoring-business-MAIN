# Prime Credit – Business Credit Report App


## Use PostgreSQL on Render (Managed DB)

This repo includes a `render.yaml` that provisions a **managed PostgreSQL database** and injects
`DATABASE_URL` into the web service automatically.

- For local dev, SQLite (`sqlite:///app.db`) still works if you set `DATABASE_URL=sqlite:///app.db`.
- On Render, no change needed — the app will connect to Render's managed PostgreSQL automatically.
