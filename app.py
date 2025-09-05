import os
import io
from datetime import date, timedelta
from flask import Flask, render_template, request, send_file
import pandas as pd

app = Flask(__name__)

LOCATIONS = ["Homeoffice", "Office", "Customer"]
WEEKDAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

def iso_last_week(year: int) -> int:
    """Return the number of the last ISO week of the given year."""
    return date(year, 12, 28).isocalendar()[1]

def get_week_dates(year: int, week: int):
    """Return (dates_list, normalized_week). Normalizes week into [1, last_week]."""
    lw = iso_last_week(year)
    week = max(1, min(int(week), lw))
    monday = date.fromisocalendar(year, week, 1)
    return [monday + timedelta(days=i) for i in range(7)], week

@app.route("/", methods=["GET"])
def index():
    today = date.today()
    # Defaults to current ISO year/week
    default_year = request.args.get("year", type=int) or today.isocalendar()[0]
    requested_week = request.args.get("week", type=int)
    default_week = requested_week if requested_week is not None else today.isocalendar()[1]

    days, normalized_week = get_week_dates(default_year, default_week)
    name = request.args.get("name", "")

    # Build default selections from query params if present (so selections persist on refresh via query string)
    selections = {}
    for d in days:
        key = f"loc_{d.isoformat()}"
        selections[key] = request.args.get(key, "")

    # Prev / next week helpers
    if normalized_week == 1:
        prev_year = default_year - 1
        prev_week = iso_last_week(prev_year)
    else:
        prev_year = default_year
        prev_week = normalized_week - 1

    last_week_this_year = iso_last_week(default_year)
    if normalized_week == last_week_this_year:
        next_year = default_year + 1
        next_week = 1
    else:
        next_year = default_year
        next_week = normalized_week + 1

    return render_template(
        "index.html",
        year=default_year,
        week=normalized_week,
        days=list(zip(days, WEEKDAY_NAMES)),
        locations=LOCATIONS,
        selections=selections,
        name=name,
        last_week=last_week_this_year,
        prev_year=prev_year,
        prev_week=prev_week,
        next_year=next_year,
        next_week=next_week,
    )

@app.route("/download", methods=["POST"])
def download():
    name = (request.form.get("name") or "").strip()
    try:
        year = int(request.form.get("year"))
        week = int(request.form.get("week"))
    except (TypeError, ValueError):
        return "Ungültige Kalenderangabe.", 400

    days, week = get_week_dates(year, week)

    rows = []
    for idx, d in enumerate(days):
        sel = request.form.get(f"loc_{d.isoformat()}", "")
        if sel not in LOCATIONS:
            sel = ""
        rows.append({
            "Name": name,
            "Jahr": year,
            "Kalenderwoche": week,
            "Datum": d.isoformat(),
            "Wochentag": WEEKDAY_NAMES[idx],
            "Standort": sel,
        })

    df = pd.DataFrame(rows)

    # Create Excel in-memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Arbeitsorte")
        worksheet = writer.sheets["Arbeitsorte"]
        for i, col in enumerate(df.columns):
            # Autosize columns (cap at 40)
            try:
                max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
            except ValueError:
                max_len = len(str(col)) + 2
            worksheet.set_column(i, i, min(max_len, 40))
    output.seek(0)

    safe_name = name or "Unbekannt"
    filename = f"Arbeitsorte_{safe_name}_J{year}_KW{week:02d}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
