# Sleep Tracker

Sleep Tracker is a small Flask web app for logging nightly sleep, reviewing entries, and getting simple wellness guidance in one place.

## Features

- Add daily sleep entries with bedtime and wake time
- Automatically calculate sleep duration
- Prevent duplicate entries for the same person and date
- Search the dashboard by name
- View sleep result feedback after each entry
- Browse wellness tips for yoga, meditation, and stress management

## Tech Stack

- Python
- Flask
- Jinja2 templates
- Local JSON file storage
- HTML and CSS

## Run Locally

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
python app.py
```

4. Open the app in your browser:

```text
http://127.0.0.1:5000
```

## Optional Environment Variable

Set a custom Flask secret key if needed:

```bash
set FLASK_SECRET_KEY=your-secret-key
```

## Project Structure

- `app.py` - Flask routes, validation, and app logic
- `templates/` - Jinja templates for pages and results
- `static/` - CSS and SVG assets
- `data/` - JSON storage for sleep entries

## Notes

- Data is stored locally in `data/sleep_entries.json`
- The app is intended for local development and learning use
