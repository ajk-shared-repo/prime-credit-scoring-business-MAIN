
import os
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pandas as pd
from io import BytesIO
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "app.db"

print(f"[BOOT] BASE_DIR={BASE_DIR}", flush=True)
print(f"[BOOT] templates exists? {TEMPLATES_DIR.exists()} contents={list(TEMPLATES_DIR.glob('*')) if TEMPLATES_DIR.exists() else 'N/A'}", flush=True)

if not (TEMPLATES_DIR / "home.html").exists():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    (TEMPLATES_DIR / "home.html").write_text(
        "<!doctype html><html><body><h1>Prime Business Credit — Home</h1>"
        "<p>Default home page created at boot because templates/home.html was missing.</p>"
        "<p><a href='{{ url_for(\"login\") }}'>Login</a> | "
        "<a href='{{ url_for(\"generate_report\") }}'>Generate Report</a></p>"
        "</body></html>",
        encoding="utf-8"
    )
    print("[BOOT] Created fallback templates/home.html", flush=True)

app = Flask(__name__, template_folder=str(TEMPLATES_DIR), static_folder=str(STATIC_DIR))
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "change-me-please")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgres://"):
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["SQLALCHEMY_DATABASE_URI"].replace("postgres://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def ensure_seed_user():
    if not User.query.first():
        admin = User(email="admin@example.com", name="Admin", is_admin=True)
        admin.set_password(os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin123"))
        user = User(email="user@example.com", name="Demo User", is_admin=False)
        user.set_password(os.environ.get("DEFAULT_USER_PASSWORD", "user123"))
        db.session.add_all([admin, user])
        db.session.commit()
        print("[BOOT] Seeded default users", flush=True)

@app.get("/ping")
def ping():
    return "ok", 200

@app.route("/")
def index():
    return render_template("home.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials.", "danger")
    return render_template("login.html")

@app.get("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("index"))

@app.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)

@app.route("/generate", methods=["GET", "POST"])
@login_required
def generate_report():
    source = "default"
    df = None

    if request.method == "POST":
        if "file" in request.files and request.files["file"].filename:
            f = request.files["file"]
            filename = f.filename.lower()
            try:
                if filename.endswith(".xlsx") or filename.endswith(".xls"):
                    df = pd.read_excel(f)
                elif filename.endswith(".csv"):
                    df = pd.read_csv(f)
                else:
                    flash("Unsupported file type. Please upload CSV or XLSX.", "warning")
                    return render_template("form.html")
                source = "uploaded"
            except Exception as e:
                flash(f"Could not read file: {e}", "danger")
                return render_template("form.html")
        else:
            default_xlsx = DATA_DIR / "Liberia_Business_Credit_Report_Template.xlsx"
            default_csv = DATA_DIR / "Prime_credit_business_attributes.csv"
            try:
                if default_xlsx.exists():
                    df = pd.read_excel(default_xlsx)
                elif default_csv.exists():
                    df = pd.read_csv(default_csv)
                else:
                    flash("No default template found in /data.", "danger")
                    return render_template("form.html")
            except Exception as e:
                flash(f"Could not read default template: {e}", "danger")
                return render_template("form.html")

        name_col_candidates = ["Business Name", "Business_Name", "Company", "Legal Name", "Name"]
        score_col_candidates = ["Credit Score", "Score", "Risk Score"]
        id_col_candidates = ["Registration No", "Business ID", "Tax ID"]

        def pick_column(cands):
            for c in cands:
                for col in df.columns:
                    if col.strip().lower() == c.strip().lower():
                        return col
            return None

        name_col = pick_column(name_col_candidates)
        score_col = pick_column(score_col_candidates)
        id_col = pick_column(id_col_candidates)

        row = df.iloc[0].to_dict()
        business_name = row.get(name_col, "Unknown Business") if name_col else "Unknown Business"
        business_id = str(row.get(id_col, "N/A")) if id_col else "N/A"
        score_val = str(row.get(score_col, "N/A")) if score_col else "N/A"

        from io import BytesIO
        from reportlab.lib.pagesizes import LETTER
        from reportlab.pdfgen import canvas
        from datetime import datetime

        pdf_bytes = BytesIO()
        c = canvas.Canvas(pdf_bytes, pagesize=LETTER)
        width, height = LETTER
        y = height - 72

        c.setFont("Helvetica-Bold", 16)
        c.drawString(72, y, "Prime Credit — Business Credit Report")
        y -= 24
        c.setFont("Helvetica", 10)
        c.drawString(72, y, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  |  Source: {source}")
        y -= 36

        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Business Summary")
        y -= 18
        c.setFont("Helvetica", 11)
        c.drawString(72, y, f"Name: {business_name}")
        y -= 16
        c.drawString(72, y, f"Business ID: {business_id}")
        y -= 16
        c.drawString(72, y, f"Credit Score: {score_val}")
        y -= 24

        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y, "Selected Attributes")
        y -= 18
        c.setFont("Helvetica", 9)

        shown = 0
        for k, v in row.items():
            if shown >= 20:
                break
            text = f"{k}: {v}"
            c.drawString(72, y, text[:95])
            y -= 12
            if y < 96:
                c.showPage()
                y = height - 72
                c.setFont("Helvetica", 9)
            shown += 1

        c.showPage()
        c.save()
        pdf_bytes.seek(0)

        return send_file(
            pdf_bytes,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"business_credit_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf",
        )

    return render_template("form.html")

with app.app_context():
    db.create_all()
    ensure_seed_user()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
