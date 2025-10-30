
import os, pandas as pd
from flask import Flask,render_template,request,redirect,url_for,flash,send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager,login_user,login_required,logout_user,current_user,UserMixin
from werkzeug.security import generate_password_hash,check_password_hash
from io import BytesIO
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
app.secret_key=os.getenv("FLASK_SECRET_KEY","dev")
app.config["SQLALCHEMY_DATABASE_URI"]=os.getenv("DATABASE_URL","sqlite:///app.db")
db=SQLAlchemy(app)
login=LoginManager(app)
login.login_view="login"

class User(db.Model,UserMixin):
    id=db.Column(db.Integer,primary_key=True)
    email=db.Column(db.String,unique=True)
    password=db.Column(db.String)
    role=db.Column(db.String,default="user")

class Report(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    business=db.Column(db.String)
    data=db.Column(db.Text)
    score=db.Column(db.Integer)
    created=db.Column(db.DateTime,default=datetime.utcnow)
    user_id=db.Column(db.Integer,db.ForeignKey("user.id"))

@login.user_loader
def load_user(uid): return User.query.get(int(uid))

def ensure_admin():
    db.create_all()
    e=os.getenv("ADMIN_EMAIL"); p=os.getenv("ADMIN_PASSWORD")
    if e and p and not User.query.filter_by(email=e).first():
        db.session.add(User(email=e,password=generate_password_hash(p),role="admin"))
        db.session.commit()

@app.before_request
def init(): ensure_admin()

def load_schema():
    return pd.read_excel("data/Prime_credit_business_attributes.xlsx").fillna("")

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=User.query.filter_by(email=request.form['email']).first()
        if u and check_password_hash(u.password,request.form['password']):
            login_user(u); return redirect('/')
        flash("Invalid credentials")
    return render_template('login.html')

@app.route('/logout'); @login_required
def logout_view(): logout_user(); return redirect('/login')

@app.route('/'); @login_required
def home(): return render_template('dashboard.html')

def admin_only(f):
    from functools import wraps
    @wraps(f)
    def w(*a,**k):
        if current_user.role!='admin': return redirect('/')
        return f(*a,**k)
    return w

@app.route('/admin/users',methods=['GET','POST']); @login_required @admin_only
def admin_users():
    if request.method=='POST':
        db.session.add(User(email=request.form['email'],password=generate_password_hash(request.form['password']),role=request.form['role']))
        db.session.commit()
    return render_template('admin_users.html',users=User.query.all())

@app.route('/admin/users/<int:id>/delete'); @login_required @admin_only
def delete_user(id):
    if id!=current_user.id:
        db.session.delete(User.query.get(id)); db.session.commit()
    return redirect('/admin/users')

@app.route('/admin/schema',methods=['GET','POST']); @login_required @admin_only
def admin_schema():
    if request.method=='POST':
        request.files['file'].save('data/Prime_credit_business_attributes.xlsx')
    return render_template('admin_schema.html')

@app.route('/report/create',methods=['GET','POST']); @login_required
def create_report():
    df=load_schema(); grouped={}
    for _,r in df.iterrows(): grouped.setdefault(r["Category"],[]).append(r.to_dict())
    if request.method=='POST':
        total=earn=0; details=[]
        for _,r in df.iterrows():
            v=request.form.get(r["Variable"],""); w=float(r.get("Suggested Weight (%)") or 0)
            total+=w; 
            if v: earn+=w
            details.append((r["Variable"],v,w))
        score=int(100*earn/total) if total else 0
        r=Report(business=request.form.get("Business_Name",""),data=str(details),score=score,user_id=current_user.id)
        db.session.add(r); db.session.commit()
        return redirect(f"/report/{r.id}")
    return render_template('form.html',grouped=grouped)

@app.route('/report/<int:id>'); @login_required
def view(id):
    r=Report.query.get_or_404(id); d=eval(r.data)
    return render_template('report.html',report={"id":r.id,"business":r.business,"score":r.score,"details":[{"variable":x[0],"value":x[1],"weight":x[2]} for x in d]})

@app.route('/report/<int:id>/download.pdf'); @login_required
def download_pdf(id):
    r=Report.query.get_or_404(id); d=eval(r.data)
    buf=BytesIO(); doc=SimpleDocTemplate(buf); s=getSampleStyleSheet(); el=[Paragraph("Business Credit Report",s["Title"])]
    el.append(Paragraph(f"Business: {r.business}",s["Normal"])); el.append(Paragraph(f"Score: {r.score}",s["Normal"])); el.append(Spacer(1,12))
    data=[("Field","Value","Weight")]+[(x[0],x[1],x[2]) for x in d]
    el.append(Table(data)); doc.build(el); buf.seek(0)
    return send_file(buf,as_attachment=True,download_name=f"report_{id}.pdf")

if __name__=='__main__':
    app.run(debug=True)
