from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import sqlite3
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "safdari.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT NOT NULL,
        image TEXT,
        base_price REAL NOT NULL,
        reference_gold REAL NOT NULL,
        active INTEGER NOT NULL DEFAULT 1
    );
    """)
    if conn.execute("SELECT 1 FROM settings WHERE key='gold_price'").fetchone() is None:
        conn.execute("INSERT INTO settings(key,value) VALUES('gold_price','0')")
    conn.commit()
    conn.close()

def current_gold():
    conn = db()
    row = conn.execute("SELECT value FROM settings WHERE key='gold_price'").fetchone()
    conn.close()
    return float(row["value"] or 0)

def calc_price(base_price, reference_gold):
    gold = current_gold()
    if reference_gold <= 0:
        return base_price
    return base_price * gold / reference_gold

def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.template_filter("money")
def money(value):
    return f"{round(float(value)):,.0f}"

@app.route("/")
def index():
    conn = db()
    models = conn.execute("SELECT * FROM models WHERE active=1 ORDER BY id DESC").fetchall()
    conn.close()
    gold = current_gold()
    return render_template("index.html", models=models, gold=gold, calc_price=calc_price)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("admin"):
        if request.method == "POST":
            if request.form.get("password") == ADMIN_PASSWORD:
                session["admin"] = True
                return redirect(url_for("admin"))
            flash("رمز عبور اشتباه است.")
        return render_template("login.html")

    conn = db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "gold":
            try:
                price = float(request.form["gold_price"])
                if price <= 0:
                    raise ValueError
                conn.execute("UPDATE settings SET value=? WHERE key='gold_price'", (str(price),))
                conn.commit()
                flash("قیمت طلا با موفقیت تغییر کرد.")
            except (ValueError, KeyError):
                flash("قیمت طلا معتبر نیست.")
        elif action == "add":
            name = request.form.get("name", "").strip()
            code = request.form.get("code", "").strip()
            try:
                base_price = float(request.form["base_price"])
                reference_gold = float(request.form["reference_gold"])
                if not name or not code or base_price <= 0 or reference_gold <= 0:
                    raise ValueError
            except (ValueError, KeyError):
                flash("اطلاعات مدل کامل یا معتبر نیست.")
                conn.close()
                return redirect(url_for("admin"))

            image_name = None
            file = request.files.get("image")
            if file and file.filename and allowed(file.filename):
                safe = secure_filename(file.filename)
                image_name = f"{os.urandom(8).hex()}_{safe}"
                file.save(UPLOAD_DIR / image_name)

            conn.execute("""INSERT INTO models(name,code,image,base_price,reference_gold)
                            VALUES(?,?,?,?,?)""",
                         (name, code, image_name, base_price, reference_gold))
            conn.commit()
            flash("مدل اضافه شد.")
        elif action == "delete":
            model_id = request.form.get("id")
            row = conn.execute("SELECT image FROM models WHERE id=?", (model_id,)).fetchone()
            if row and row["image"]:
                try: (UPLOAD_DIR / row["image"]).unlink(missing_ok=True)
                except OSError: pass
            conn.execute("DELETE FROM models WHERE id=?", (model_id,))
            conn.commit()
            flash("مدل حذف شد.")
    models = conn.execute("SELECT * FROM models ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("admin.html", models=models, gold=current_gold(), calc_price=calc_price)

@app.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
