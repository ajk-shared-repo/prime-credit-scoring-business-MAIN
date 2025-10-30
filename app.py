import os, logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")

# Normalize DATABASE_URL for SQLAlchemy (postgres:// -> postgresql+psycopg2://)
db_url = os.getenv("DATABASE_URL", "sqlite:///app.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev")
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login = LoginManager(app)
login.login_view = "login"

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="user")

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business = db.Column(db.String(255))
    score = db.Column(db.Integer, default=0)
    created = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))

@login.user_loader
def load_user(uid):
    try:
        return User.query.get(int(uid))
    except Exception:
        return None

def ensure_admin():
    db.create_all()
    email = os.getenv("ADMIN_EMAIL", "admin@example.com")
    password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
    if not User.query.filter_by(email=email).first():
        u = User(email=email, role="admin")
        u.set_password(password)
        db.session.add(u); db.session.commit()
        log.info("Seeded admin user: %s", email)

@app.before_request
def before_any():
    try:
        ensure_admin()
    except Exception as e:
        log.exception("DB init failed: %s", e)

@app.get("/ping")
def ping():
    return "ok", 200

@app.get("/health")
def health():
    return jsonify(status="ok", db=app.config["SQLALCHEMY_DATABASE_URI"]), 200

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"].strip().lower()).first()
        if user and user.check_password(request.form["password"]):
            login_user(user); return redirect(url_for("home"))
        flash("Invalid credentials")
    return render_template("login.html")

@app.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.get("/")
@login_required
def home():
    return render_template("dashboard.html")

@app.route("/report/create", methods=["GET","POST"])
@login_required
def create_report():
    if request.method == "POST":
        business = request.form.get("Business_Name","").strip() or "Unknown Business"
        r = Report(business=business, score=100, user_id=current_user.id)  # placeholder score
        db.session.add(r); db.session.commit()
        return redirect(url_for("view_report", rid=r.id))
    return render_template("form.html")

@app.get("/report/<int:rid>")
@login_required
def view_report(rid):
    r = Report.query.get_or_404(rid)
    report = {"business": r.business, "score": r.score, "id": r.id}
    return render_template("report.html", report=report)
