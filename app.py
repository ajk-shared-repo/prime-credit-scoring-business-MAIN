import os, json
from datetime import datetime
from io import BytesIO
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet

def normalize_db_url(url):
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY", "dev")
app.config['SQLALCHEMY_DATABASE_URI'] = normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///app.db"))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login = LoginManager(app); login.login_view = "login"

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="user")
    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_name = db.Column(db.String(255))
    payload_json = db.Column(db.Text)
    score = db.Column(db.Integer, default=0)
    created = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

@login.user_loader
def load_user(uid): return User.query.get(int(uid))

def ensure_admin():
    db.create_all()
    e=os.getenv("ADMIN_EMAIL","admin@example.com"); p=os.getenv("ADMIN_PASSWORD","ChangeMe123!")
    if not User.query.filter_by(email=e).first():
        u=User(email=e, role="admin"); u.set_password(p); db.session.add(u); db.session.commit()

@app.before_request
def br(): ensure_admin()

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "data", "Liberia_Business_Credit_Report_Template.xlsx")

def read_schema():
    if not os.path.exists(SCHEMA_PATH):
        return pd.DataFrame(columns=["Variable","Description","Field_Type","Suggested_Weight"])
    df = pd.read_excel(SCHEMA_PATH).copy()
    cols = {c.lower().strip(): c for c in df.columns}
    def pick(names, default=None):
        for n in names:
            if n.lower() in cols: return cols[n.lower()]
        return default
    var_col = pick(["Variable","Field","Name"], df.columns[0] if len(df.columns) else None)
    desc_col = pick(["Description / Purpose","Description","Desc"], var_col)
    type_col = pick(["Field Type","Field_Type","Type"], None)
    weight_col = pick(["Suggested Weight (%)","Suggested_Weight","Weight"], None)
    if type_col is None:
        df["Field_Type"]="Text"; type_col="Field_Type"
    if weight_col is None:
        df["Suggested_Weight"]=1; weight_col="Suggested_Weight"
    out = df[[var_col, desc_col, type_col, weight_col]].copy()
    out.columns = ["Variable","Description","Field_Type","Suggested_Weight"]
    out = out.fillna("")
    return out

@app.get("/")
def index():
    from flask_login import current_user
    if current_user.is_authenticated:
        return render_template("home.html")
    return render_template("home.html")

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u = User.query.filter_by(email=request.form['email'].strip().lower()).first()
        if u and u.check_password(request.form['password']):
            login_user(u); return redirect(url_for('index'))
        flash("Invalid credentials")
    return render_template('login.html')

@app.get('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('login'))

def admin_only(f):
    from functools import wraps
    @wraps(f)
    def w(*a,**k):
        if current_user.role!='admin':
            flash('Admin access required'); return redirect(url_for('index'))
        return f(*a,**k)
    return w

@app.route('/admin/users', methods=['GET','POST'])
@login_required
@admin_only
def admin_users():
    if request.method=='POST':
        u=User(email=request.form['email'].strip().lower(), role=request.form.get('role','user'))
        u.set_password(request.form['password'])
        db.session.add(u); db.session.commit(); flash('User added')
    return render_template('admin_users.html', users=User.query.order_by(User.email).all())

@app.get('/admin/users/<int:user_id>/delete')
@login_required
@admin_only
def delete_user(user_id):
    if current_user.id == user_id:
        flash('Cannot delete yourself'); return redirect(url_for('admin_users'))
    u=User.query.get_or_404(user_id); db.session.delete(u); db.session.commit(); flash('Deleted')
    return redirect(url_for('admin_users'))

@app.route('/admin/schema', methods=['GET','POST'])
@login_required
@admin_only
def admin_schema():
    if request.method=='POST':
        f = request.files['file']
        if f and f.filename.lower().endswith('.xlsx'):
            f.save(SCHEMA_PATH); flash('Template updated')
        else:
            flash('Upload a .xlsx file')
    return render_template('admin_schema.html')

@app.route('/report/create', methods=['GET','POST'])
@login_required
def create_report():
    schema = read_schema()
    rows = schema.to_dict(orient='records')
    if request.method=='POST':
        total = float(schema['Suggested_Weight'].astype(float).sum() or 0.0)
        earned = 0.0
        details = []
        business_name = None
        for r in rows:
            var = r['Variable']
            weight = float(r.get('Suggested_Weight') or 0)
            val = request.form.get(var, '').strip()
            if var.lower() in ['business_name','business name','legal_name','legal name']:
                business_name = val or business_name
            if val:
                earned += weight
            details.append({"variable": var, "value": val, "weight": weight})
        score = int(round(100 * earned / total)) if total else 0
        payload = {"details": details}
        rep = Report(business_name=business_name or "Unknown Business",
                     payload_json=json.dumps(payload),
                     score=score,
                     user_id=current_user.id)
        db.session.add(rep); db.session.commit()
        return redirect(url_for('view_report', report_id=rep.id))
    return render_template('form.html', rows=rows)

@app.get('/report/<int:report_id>')
@login_required
def view_report(report_id):
    r = Report.query.get_or_404(report_id)
    payload = json.loads(r.payload_json or '{"details": []}')
    return render_template('report.html', report={
        "id": r.id,
        "business_name": r.business_name,
        "score": r.score,
        "details": payload.get("details", [])
    })

@app.get('/ping')
def ping(): return "ok", 200

@app.get('/report/<int:report_id>/download.pdf')
@login_required
def download_pdf(report_id):
    r = Report.query.get_or_404(report_id)
    payload = json.loads(r.payload_json or '{"details": []}')
    buf = BytesIO()
    doc = SimpleDocTemplate(buf)
    styles = getSampleStyleSheet()
    elems = [
        Paragraph("Liberia Business Credit Report", styles['Title']),
        Spacer(1,10),
        Paragraph(f"Business: {r.business_name}", styles['Normal']),
        Paragraph(f"Score: {r.score} / 100", styles['Normal']),
        Spacer(1,10)
    ]
    data = [("Field","Value","Weight")]
    for d in payload.get("details", []):
        data.append((d["variable"], d["value"], str(d["weight"])))
    elems.append(Table(data))
    doc.build(elems)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"Business_Credit_Report_{r.id}.pdf")

if __name__ == "__main__":
    with app.app_context(): db.create_all()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
