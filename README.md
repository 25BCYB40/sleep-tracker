# Sleep Tracker

A simple Flask sleep tracker with:

- daily sleep entry logging
- automatic duration calculation from bedtime and wake time
- duplicate protection for the same name and date
- dashboard search by name
- sleep result suggestions
- wellness tips for yoga, meditation, and stress reduction

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
python app.py
```

4. Open `http://127.0.0.1:5000`

## Optional environment variable

For a custom Flask secret key:

```bash
set FLASK_SECRET_KEY=your-secret-key
```

## Project structure

- `app.py` - Flask routes and logic
- `templates/` - Jinja HTML templates
- `static/` - CSS and SVG reference images
- `data/` - local JSON data storage
