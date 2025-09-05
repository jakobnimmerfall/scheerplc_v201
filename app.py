import os
import io
from datetime import date, timedelta
from typing import Dict

from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin
from flask_bcrypt import Bcrypt

import pandas as pd

from sqlalchemy import create_engine, Integer, String, Date, UniqueConstraint, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, foreign

# ----------------------------
# App & Config
# ----------------------------
app = Flask(__name__)

# WICHTIG: in Cloud Run per Env setzen!
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# DB:
# Lokal: sqlite:///local.db
# Cloud SQL (TCP): postgresql+psycopg2://USER:PWD@HOST:5432/DBNAME
# Cloud SQL (Unix Socket):
#   postgresql+psycopg2://USER:PWD@/DBNAME?host=/cloudsql/PROJECT:REGION:INSTANCE
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local.db")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

bcrypt = Bcrypt(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

# ----------------------------
# Models
# ----------------------------
class Base(DeclarativeBase):
    pass

class User(Base, UserMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    def get_id(self) -> str:
        return str(self.id)

class WorkSelection(Base):
    __tablename__ = "work_selections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(foreign(User.id), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    location: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_date"),)

Base.metadata.create_all(engine)

# ----------------------------
# Auth helpers
# ----------------------------
@login_manager.user_loader
def load_user(user_id: str):
    with Session(engine) as s:
        return s.get(User, int(user_id))

def create_user_if_missing(email: str, username: str, name: str, password: str):
    with Session(engine) as s:
        existing = s.scalar(select(User).where(User.email == email))
        if existing:
            return existing
        pw_hash = bcrypt.generate_password_hash(password).decode("utf-8")
        u = User(email=email, username=username, name=name, password_hash=pw_hash, is_active=1)
        s.add(u)
        s.commit()
        return u

# ----------------------------
# Bestehende Logik (erweitert)
# ----------------------------
LOCATIONS = ["Homeoffice", "Office", "Customer"]
WEEKDAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

def iso_last_week(year: int) -> int:
    return date(year, 12, 28).isocalendar()[1]

def get_week_dates(year: int, week: int):
    lw = iso_last_week(year)
    week = max(1, min(int(week), lw))
    monday = date.fromisocalendar(year, week, 1)
    return [monday + timedelta(days=i) for i in range(7)], week

def load_selections_for_user_week(user_id: int, days_list: list[date]) -> Dict[str, str]:
    with Session(engine) as s:
        rows = s.execute(
            select(WorkSelection.date, WorkSelection.location)
            .where(WorkSelection.user_id == user_id)
            .where(WorkSelection.date.in_(days_list))
        ).all()
    return {d.isoformat(): loc for (d, loc) in rows}

def upsert_user_week(user_id: int, year: int, week: int, form_payload: Dict[str, str]):
    days, week_norm = get_week_dates(year, week)
    with Session(engine) as s:
        for idx, d in enumerate(days):
            key = f"loc_{d.isoformat()}"
            sel = form_payload.get(key, "")
            if sel not in LOCATIONS:
                sel = ""
            existing = s.scalar(
                select(WorkSelection).where(WorkSelection.user_id == user_id, WorkSelection.date == d)
            )
            if existing:
                existing.location = sel
                existing.year = year
                existing.week = week_norm
            else:
                s.add(WorkSelection(user_id=user_id, date=d, year=year, week=week_norm, location=sel))
        s.commit()

# ----------------------------
# Routes: Auth
# ----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username_or_email = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        with Session(engine) as s:
            q = select(User).where((User.username == username_or_email) | (User.email == username_or_email))
            user = s.scalar(q)
            if user and bcrypt.check_password_hash(user.password_hash, password) and user.is_active:
                login_user(user)
                return redirect(request.args.get("next") or url_for("index"))
        flash("Login fehlgeschlagen. Bitte prüfen Sie Zugangsdaten.", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ----------------------------
# Routes: App
# ----------------------------
@app.route("/", methods=["GET"])
@login_required
def index():
    today = date.today()
    default_year = request.args.get("year", type=int) or today.isocalendar()[0]
    requested_week = request.args.get("week", type=int)
    default_week = requested_week if requested_week is not None else today.isocalendar()[1]

    days, normalized_week = get_week_dates(default_year, default_week)

    # Selektionen des eingeloggten Users aus DB
    selections = load_selections_for_user_week(current_user.id, days)

    # Prev/Next
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
        name=current_user.name,
        last_week=last_week_this_year,
        prev_year=prev_year,
        prev_week=prev_week,
        next_year=next_year,
        next_week=next_week,
        current_username=current_user.username,
    )

@app.route("/save", methods=["POST"])
@login_required
def save():
    try:
        year = int(request.form.get("year"))
        week = int(request.form.get("week"))
    except (TypeError, ValueError):
        return "Ungültige Kalenderangabe.", 400
    upsert_user_week(current_user.id, year, week, request.form)
    flash("Auswahl gespeichert.", "success")
    return redirect(url_for("index", year=year, week=week))

@app.route("/download", methods=["POST"])
@login_required
def download():
    # Speichern und dann Excel erzeugen (deine bestehende Logik)
    try:
        year = int(request.form.get("year"))
        week = int(request.form.get("week"))
    except (TypeError, ValueError):
        return "Ungültige Kalenderangabe.", 400

    upsert_user_week(current_user.id, year, week, request.form)
    days, week = get_week_dates(year, week)

    selections = load_selections_for_user_week(current_user.id, days)
    rows = []
    for idx, d in enumerate(days):
        rows.append({
            "Name": current_user.name,
            "Jahr": year,
            "Kalenderwoche": week,
            "Datum": d.isoformat(),
            "Wochentag": ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"][idx],
            "Standort": selections.get(d.isoformat(), ""),
        })
    df = pd.DataFrame(rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Arbeitsorte")
        worksheet = writer.sheets["Arbeitsorte"]
        for i, col in enumerate(df.columns):
            try:
                max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
            except ValueError:
                max_len = len(str(col)) + 2
            worksheet.set_column(i, i, min(max_len, 40))
    output.seek(0)

    filename = f"Arbeitsorte_{current_user.name}_J{year}_KW{week:02d}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )

# ----------------------------
# Pilot-User seeden (einmalig)
# ----------------------------
@app.before_first_request
def ensure_pilot_user():
    email = os.environ.get("INIT_USER_EMAIL", "jakob.nimmerfall@scheer-group.com")
    username = os.environ.get("INIT_USER_USERNAME", "jakob.nimmerfall")
    name = os.environ.get("INIT_USER_NAME", "Jakob Nimmerfall")
    pwd = os.environ.get("INIT_USER_PASSWORD", None)
    if not pwd:
        return
    create_user_if_missing(email=email, username=username, name=name, password=pwd)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
