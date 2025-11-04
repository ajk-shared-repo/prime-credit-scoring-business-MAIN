import os
from io import BytesIO
from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import pandas as pd

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

@app.route("/ping")
def ping():
    return {"status":"ok"}

@app.route("/")
def index():
    return render_template("home.html")

@app.route("/generate", methods=["GET", "POST"])
def generate():
    if request.method == "GET":
        return render_template("form.html")

    # POST
    file = request.files.get("file")
    df = None
    used_sample = False
    try:
        if file and file.filename:
            name = file.filename.lower()
            if name.endswith(".csv"):
                df = pd.read_csv(file)
            elif name.endswith(".xlsx") or name.endswith(".xls"):
                df = pd.read_excel(file)
            else:
                flash("Unsupported file type. Please upload CSV or XLSX.", "error")
                return redirect(url_for("generate"))
        else:
            # fallback to sample
            xlsx = os.path.join("data", "Liberia_Business_Credit_Report_Template.xlsx")
            csv = os.path.join("data", "sample_business_data.csv")
            if os.path.exists(xlsx):
                df = pd.read_excel(xlsx)
                used_sample = True
            elif os.path.exists(csv):
                df = pd.read_csv(csv)
                used_sample = True
            else:
                flash("No file uploaded and no sample data available.", "error")
                return redirect(url_for("generate"))
    except Exception as e:
        flash(f"Failed to read file: {e}", "error")
        return redirect(url_for("generate"))

    record = df.iloc[0].to_dict() if not df.empty else {}

    # PDF
    buf = BytesIO()
    p = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    p.setFont("Helvetica-Bold", 16)
    p.drawString(72, height-72, "Prime Business Credit Report")

    p.setFont("Helvetica", 10)
    y = height - 110
    p.drawString(72, y, f"Source: {'Sample' if used_sample else 'Upload'}")
    y -= 20

    for k, v in list(record.items())[:28]:
        if y < 72:
            p.showPage()
            p.setFont("Helvetica", 10)
            y = height - 72
        p.drawString(72, y, f"{k}: {v}"[:110])
        y -= 16

    # demo score
    try:
        name = str(record.get("BusinessName") or record.get("business_name") or "")
        score = min(850, 300 + len(name) * 10)
    except Exception:
        score = 600
    if y < 90:
        p.showPage(); y = height - 72
    p.setFont("Helvetica-Bold", 12)
    p.drawString(72, y, f"Indicative Credit Score (demo): {score}")
    y -= 20
    p.setFont("Helvetica", 9)
    p.drawString(72, y, "Demo only — replace with production scoring logic.")
    p.save()

    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="prime_business_credit_report.pdf", mimetype="application/pdf")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
