import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "sleep_entries.json"
DATABASE_URL = os.environ.get("DATABASE_URL")
POSTGRES_READY = False

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

QUALITY_SCORES = {
    "Poor": 1,
    "Fair": 2,
    "Good": 3,
    "Great": 4,
}


def uses_postgres():
    return bool(DATABASE_URL)


def get_db_connection():
    if psycopg2 is None:
        raise RuntimeError("psycopg2-binary is required when DATABASE_URL is configured.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_postgres():
    global POSTGRES_READY
    if not uses_postgres():
        return

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sleep_entries (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entry_date DATE NOT NULL,
                    duration NUMERIC(4, 1) NOT NULL,
                    quality TEXT NOT NULL,
                    bedtime TEXT,
                    wake_time TEXT,
                    result_headline TEXT NOT NULL,
                    result_message TEXT NOT NULL,
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS sleep_entries_name_date_idx
                ON sleep_entries (LOWER(name), entry_date)
                """
            )
    POSTGRES_READY = True


def ensure_postgres_ready():
    if uses_postgres() and not POSTGRES_READY:
        init_postgres()


def read_entries_from_json():
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        DATA_PATH.write_text("[]", encoding="utf-8")
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        DATA_PATH.write_text("[]", encoding="utf-8")
        return []
    return entries if isinstance(entries, list) else []


def write_entries_to_json(entries):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


def read_entries_from_postgres():
    ensure_postgres_ready()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    name,
                    TO_CHAR(entry_date, 'YYYY-MM-DD') AS date,
                    duration,
                    quality,
                    bedtime,
                    wake_time,
                    result_headline,
                    result_message,
                    COALESCE(notes, '') AS notes
                FROM sleep_entries
                ORDER BY entry_date DESC, created_at DESC
                """
            )
            return [dict(row) for row in cursor.fetchall()]


def read_entries():
    if uses_postgres():
        try:
            return read_entries_from_postgres()
        except Exception:
            app.logger.exception("Failed to read sleep entries from PostgreSQL.")
            return []
    return read_entries_from_json()


def write_entries(entries):
    if uses_postgres():
        raise RuntimeError("Bulk write is not used when PostgreSQL storage is enabled.")
    write_entries_to_json(entries)


def normalize_entry(entry):
    normalized = dict(entry)
    normalized["id"] = entry.get("id", str(uuid.uuid4()))
    normalized["duration"] = float(entry.get("duration", 0) or 0)
    normalized["duration_percent"] = min(round((normalized["duration"] / 10) * 100, 1), 100)
    normalized["name"] = entry.get("name", "Guest")
    normalized["date"] = entry.get("date", "")
    normalized["quality"] = entry.get("quality") or "Unrated"
    normalized["bedtime"] = entry.get("bedtime", "")
    normalized["wake_time"] = entry.get("wake_time", "")
    normalized["notes"] = entry.get("notes", "")
    suggestion = build_sleep_suggestion(normalized["duration"])
    normalized["result_headline"] = entry.get("result_headline", suggestion["headline"])
    normalized["result_message"] = entry.get("result_message", suggestion["message"])
    return normalized


def get_sorted_entries():
    entries = [normalize_entry(entry) for entry in read_entries()]
    return sorted(entries, key=lambda item: item.get("date", ""), reverse=True)


def find_duplicate_entry(name, date):
    if uses_postgres():
        ensure_postgres_ready()
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id
                    FROM sleep_entries
                    WHERE LOWER(name) = LOWER(%s) AND entry_date = %s
                    LIMIT 1
                    """,
                    (name, date),
                )
                return cursor.fetchone()

    entries = read_entries()
    return next(
        (
            entry
            for entry in entries
            if entry.get("name", "").strip().lower() == name.lower()
            and entry.get("date") == date
        ),
        None,
    )


def add_entry_record(entry):
    if uses_postgres():
        ensure_postgres_ready()
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sleep_entries (
                        id,
                        name,
                        entry_date,
                        duration,
                        quality,
                        bedtime,
                        wake_time,
                        result_headline,
                        result_message,
                        notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        entry["id"],
                        entry["name"],
                        entry["date"],
                        entry["duration"],
                        entry["quality"],
                        entry["bedtime"],
                        entry["wake_time"],
                        entry["result_headline"],
                        entry["result_message"],
                        entry.get("notes", ""),
                    ),
                )
        return

    entries = read_entries_from_json()
    entries.append(entry)
    write_entries_to_json(entries)


def delete_entry_record(entry_id):
    if uses_postgres():
        ensure_postgres_ready()
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM sleep_entries WHERE id = %s", (entry_id,))
        return

    entries = read_entries_from_json()
    new_entries = [entry for entry in entries if entry.get("id") != entry_id]
    write_entries_to_json(new_entries)


def get_storage_status():
    if uses_postgres():
        ensure_postgres_ready()
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                cursor.fetchone()
        return {"backend": "postgresql", "status": "ok"}

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        DATA_PATH.write_text("[]", encoding="utf-8")
    return {"backend": "json", "status": "ok"}


def infer_quality(duration):
    if duration >= 8:
        return "Great"
    if duration >= 7:
        return "Good"
    if duration >= 6:
        return "Fair"
    return "Poor"


def calculate_duration(bedtime, wake_time):
    start = datetime.strptime(bedtime, "%H:%M")
    end = datetime.strptime(wake_time, "%H:%M")
    if end <= start:
        end += timedelta(days=1)
    return round((end - start).total_seconds() / 3600, 1)


def build_sleep_suggestion(duration):
    if duration >= 8:
        return {
            "headline": "Excellent recovery window",
            "message": "You gave your body enough time to recover well. Keep protecting this routine with a steady bedtime and a calm wind-down.",
        }
    if duration >= 7:
        return {
            "headline": "Solid sleep result",
            "message": "This is a healthy range for many people. Try to keep the same sleep and wake time so your routine stays consistent.",
        }
    if duration >= 6:
        return {
            "headline": "A fair night, but you could use more rest",
            "message": "You slept some, but an extra hour could improve focus and energy. Try reducing late-night screen time or caffeine.",
        }
    return {
        "headline": "Low sleep duration",
        "message": "This was a short night. If possible, aim for an earlier bedtime tonight and keep the next evening calm and screen-light.",
    }


def build_quality_breakdown(entries):
    counts = {"Great": 0, "Good": 0, "Fair": 0, "Poor": 0, "Unrated": 0}
    for entry in entries:
        counts[entry["quality"]] = counts.get(entry["quality"], 0) + 1
    total = len(entries)
    breakdown = []
    for label in ["Great", "Good", "Fair", "Poor", "Unrated"]:
        value = counts[label]
        percent = round((value / total) * 100, 1) if total else 0
        breakdown.append({"label": label, "value": value, "percent": percent})
    return breakdown


def calculate_streak(entries):
    dates = []
    for entry in entries:
        try:
            dates.append(datetime.fromisoformat(entry["date"]).date())
        except (KeyError, TypeError, ValueError):
            continue
    if not dates:
        return 0

    dates = sorted(set(dates), reverse=True)
    streak = 1
    for previous, current in zip(dates, dates[1:]):
        if previous - current == timedelta(days=1):
            streak += 1
        else:
            break
    return streak


def build_dashboard_metrics(entries):
    total_hours = round(sum(item["duration"] for item in entries), 1)
    count = len(entries)
    avg_hours = round(total_hours / count, 1) if count else 0
    ideal_nights = sum(1 for item in entries if 7 <= item["duration"] <= 9)
    recovery_nights = sum(1 for item in entries if item["duration"] >= 8)
    latest = entries[0] if entries else None
    recent_entries = entries[:7]
    weekly_average = (
        round(sum(item["duration"] for item in recent_entries) / len(recent_entries), 1)
        if recent_entries
        else 0
    )

    scored_entries = [QUALITY_SCORES[item["quality"]] for item in entries if item["quality"] in QUALITY_SCORES]
    average_quality = round(sum(scored_entries) / len(scored_entries), 1) if scored_entries else 0
    consistency = round((ideal_nights / count) * 100) if count else 0

    return {
        "total_hours": total_hours,
        "avg_hours": avg_hours,
        "count": count,
        "ideal_nights": ideal_nights,
        "recovery_nights": recovery_nights,
        "latest": latest,
        "weekly_average": weekly_average,
        "average_quality": average_quality,
        "consistency": consistency,
        "streak": calculate_streak(entries),
        "quality_breakdown": build_quality_breakdown(entries),
    }


@app.route("/health")
def health():
    try:
        storage = get_storage_status()
        return jsonify(
            {
                "status": "ok",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "storage": storage,
            }
        ), 200
    except Exception as exc:
        backend = "postgresql" if uses_postgres() else "json"
        return jsonify(
            {
                "status": "error",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "storage": {"backend": backend, "status": "error"},
                "error": str(exc),
            }
        ), 500


@app.route("/")
def home():
    entries = get_sorted_entries()
    search_name = request.args.get("name", "").strip()
    filtered_entries = entries
    if search_name:
        search_text = search_name.lower()
        filtered_entries = [
            entry for entry in entries if search_text in entry["name"].lower()
        ]

    metrics = build_dashboard_metrics(filtered_entries)
    return render_template(
        "index.html",
        entries=filtered_entries,
        metrics=metrics,
        search_name=search_name,
    )


@app.route("/add", methods=["GET", "POST"])
def add_entry():
    if request.method == "POST":
        date = request.form.get("date")
        name = request.form.get("name", "").strip()
        bedtime = request.form.get("bedtime", "")
        wake_time = request.form.get("wake_time", "")

        if not date or not name or not bedtime or not wake_time:
            flash("Name, date, bedtime, and wake time are required.", "error")
            return redirect(url_for("add_entry"))

        try:
            datetime.fromisoformat(date)
        except ValueError:
            flash("Invalid date format.", "error")
            return redirect(url_for("add_entry"))

        try:
            duration = calculate_duration(bedtime, wake_time)
        except ValueError:
            flash("Invalid bedtime or wake time.", "error")
            return redirect(url_for("add_entry"))

        quality = infer_quality(duration)
        suggestion = build_sleep_suggestion(duration)

        try:
            if find_duplicate_entry(name, date):
                flash("An entry for this name and date already exists.", "error")
                return redirect(url_for("add_entry"))

            add_entry_record(
                {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "date": date,
                    "duration": duration,
                    "quality": quality,
                    "bedtime": bedtime,
                    "wake_time": wake_time,
                    "result_headline": suggestion["headline"],
                    "result_message": suggestion["message"],
                    "notes": "",
                }
            )
        except Exception:
            app.logger.exception("Failed to save sleep entry.")
            flash("Storage is unavailable right now. Please try again later.", "error")
            return redirect(url_for("add_entry"))
        flash(
            "Sleep entry added for {}. Duration: {} hours. Result: {}.".format(
                name, duration, suggestion["headline"]
            ),
            "success",
        )
        return redirect(url_for("home"))

    return render_template("add.html")


@app.route("/delete/<entry_id>", methods=["POST"])
def delete_entry(entry_id):
    try:
        delete_entry_record(entry_id)
    except Exception:
        app.logger.exception("Failed to delete sleep entry.")
        flash("Storage is unavailable right now. Please try again later.", "error")
        return redirect(url_for("home"))
    flash("Entry deleted.", "success")
    return redirect(url_for("home"))


@app.route("/entry/<entry_id>")
def entry_result(entry_id):
    entries = get_sorted_entries()
    entry = next((item for item in entries if item.get("id") == entry_id), None)
    if not entry:
        flash("Entry not found.", "error")
        return redirect(url_for("home"))

    suggestion = {
        "headline": entry["result_headline"],
        "message": entry["result_message"],
    }
    return render_template("entry_result.html", entry=entry, suggestion=suggestion)


@app.route("/stats")
def stats():
    entries = get_sorted_entries()
    metrics = build_dashboard_metrics(entries)
    if entries:
        longest = max(entries, key=lambda x: x["duration"])
        shortest = min(entries, key=lambda x: x["duration"])
        best_quality = max(
            entries,
            key=lambda x: QUALITY_SCORES.get(x["quality"], 0),
        )
    else:
        longest = shortest = best_quality = None

    return render_template(
        "stats.html",
        entries=entries,
        longest=longest,
        shortest=shortest,
        best_quality=best_quality,
        metrics=metrics,
    )


@app.route("/wellness")
def wellness():
    yoga_tips = [
        {
            "title": "Child's Pose for calm breathing",
            "description": "Stay here for 1 to 2 minutes and take slow breaths to relax the back, shoulders, and nervous system.",
        },
        {
            "title": "Cat-Cow to release tension",
            "description": "Move gently for 8 to 10 rounds to ease stiffness in the spine and reduce body stress after a long day.",
        },
        {
            "title": "Legs-Up-the-Wall for recovery",
            "description": "Spend 5 minutes here in the evening to settle the body, reduce heaviness in the legs, and support relaxation.",
        },
    ]

    meditation_tips = [
        {
            "title": "Box breathing for 2 minutes",
            "description": "Inhale for 4, hold for 4, exhale for 4, hold for 4. This can quickly settle racing thoughts.",
        },
        {
            "title": "Body scan before bed",
            "description": "Move your attention slowly from head to toe and notice tension without judging it. Let each area soften.",
        },
        {
            "title": "Single-point focus",
            "description": "Choose one anchor like your breath, a sound, or a word, and gently return to it whenever your mind wanders.",
        },
    ]

    stress_tips = [
        "Keep a fixed wind-down routine for the last 30 minutes before sleep.",
        "Reduce caffeine late in the day if you notice a restless mind at night.",
        "Step away from your phone for a short period before bed to lower overstimulation.",
        "Take a short walk, stretch, or do light yoga when stress starts building up.",
        "Write down tomorrow's tasks so your mind does not keep rehearsing them at night.",
    ]

    return render_template(
        "wellness.html",
        yoga_tips=yoga_tips,
        meditation_tips=meditation_tips,
        stress_tips=stress_tips,
    )

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
