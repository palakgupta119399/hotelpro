import os
import sqlite3
from datetime import datetime, date
from functools import wraps
from flask import Flask, g, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.environ.get("HOTELPRO_DB", os.path.join(BASE_DIR, "hotelpro.db"))
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    # Development convenience only. Set SECRET_KEY in production.
    SECRET_KEY = "dev-only-change-this-secret-key"
app = Flask(__name__)
app.config.update(SECRET_KEY=SECRET_KEY, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS rooms (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      room_type TEXT NOT NULL,
      description TEXT NOT NULL,
      price INTEGER NOT NULL CHECK(price > 0),
      capacity INTEGER NOT NULL CHECK(capacity BETWEEN 1 AND 10),
      emoji TEXT NOT NULL DEFAULT '🛏️',
      active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS bookings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id),
      room_id INTEGER NOT NULL REFERENCES rooms(id),
      check_in TEXT NOT NULL,
      check_out TEXT NOT NULL,
      guests INTEGER NOT NULL,
      total INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active','Cancelled')),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CHECK(check_out > check_in)
    );
    """)
    count = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    if count == 0:
        rooms = [
          ("Deluxe Room","Deluxe","A comfortable room with a queen bed, Wi-Fi and a peaceful view.",2499,2,"🛏️"),
          ("Executive Suite","Suite","A spacious suite with a separate sitting area and premium amenities.",4599,3,"🛋️"),
          ("Family Room","Family","A roomy stay for families, with flexible sleeping arrangements.",3599,4,"🏡"),
          ("Premium King","Premium","A stylish king room designed for a relaxing getaway.",3199,2,"🌅"),
          ("Garden View Room","Deluxe","Bright interiors with a refreshing garden-facing view.",2799,2,"🌿"),
          ("Luxury Suite","Suite","Extra space, elegant decor and an elevated hotel experience.",5999,4,"✨"),
        ]
        conn.executemany("INSERT INTO rooms(name,room_type,description,price,capacity,emoji) VALUES(?,?,?,?,?,?)", rooms)
    # Optional first-admin bootstrap: set ADMIN_EMAIL and ADMIN_PASSWORD before first run.
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if admin_email and admin_password:
        existing = conn.execute("SELECT id FROM users WHERE email=?", (admin_email.lower().strip(),)).fetchone()
        if not existing:
            conn.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'admin')",
                         ("Hotel Admin", admin_email.lower().strip(), generate_password_hash(admin_password)))
    conn.commit()
    conn.close()

@app.before_request
def load_user():
    g.user = None
    if session.get("user_id"):
        g.user = db().execute("SELECT id,name,email,role FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if g.user is None:
            session.clear()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.user:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.user:
            flash("Please log in as an administrator.", "info")
            return redirect(url_for("login"))
        if g.user["role"] != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_globals():
    return {"current_user": getattr(g, "user", None), "today": date.today().isoformat(), "now_year": date.today().year}

@app.route("/")
def index():
    rooms = db().execute("SELECT * FROM rooms WHERE active=1 ORDER BY id DESC LIMIT 3").fetchall()
    return render_template("index.html", rooms=rooms)

@app.route("/rooms")
def rooms():
    room_type = request.args.get("type", "all")
    types = db().execute("SELECT DISTINCT room_type FROM rooms WHERE active=1 ORDER BY room_type").fetchall()
    if room_type == "all":
        items = db().execute("SELECT * FROM rooms WHERE active=1 ORDER BY price").fetchall()
    else:
        items = db().execute("SELECT * FROM rooms WHERE active=1 AND room_type=? ORDER BY price", (room_type,)).fetchall()
    return render_template("rooms.html", rooms=items, types=types, selected_type=room_type)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/signup", methods=["GET","POST"])
def signup():
    if g.user:
        return redirect(url_for("index"))
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        if len(name) < 2 or "@" not in email or len(password) < 8:
            flash("Enter a valid name/email and a password of at least 8 characters.", "error")
        else:
            try:
                cur = db().execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'user')",
                                   (name,email,generate_password_hash(password)))
                db().commit()
                session.clear()
                session["user_id"] = cur.lastrowid
                flash("Account created successfully.", "success")
                return redirect(url_for("index"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "error")
    return render_template("auth.html", mode="signup")

@app.route("/login", methods=["GET","POST"])
def login():
    if g.user:
        return redirect(url_for("admin") if g.user["role"]=="admin" else url_for("index"))
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        user = db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash("Welcome back!", "success")
            target = request.args.get("next", "")
            if target.startswith("/") and not target.startswith("//"):
                return redirect(target)
            return redirect(url_for("admin") if user["role"]=="admin" else url_for("index"))
        flash("Email or password is incorrect.", "error")
    return render_template("auth.html", mode="login")

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/book/<int:room_id>", methods=["GET","POST"])
@login_required
def book(room_id):
    room = db().execute("SELECT * FROM rooms WHERE id=? AND active=1", (room_id,)).fetchone()
    if not room:
        abort(404)
    if request.method == "POST":
        check_in = request.form.get("check_in","")
        check_out = request.form.get("check_out","")
        try:
            ci = date.fromisoformat(check_in)
            co = date.fromisoformat(check_out)
            guests = int(request.form.get("guests","1"))
            if ci < date.today():
                raise ValueError
            if co <= ci or guests < 1 or guests > room["capacity"]:
                raise ValueError
        except (ValueError, TypeError):
            flash("Choose valid dates and a guest count within room capacity.", "error")
            return render_template("book.html", room=room)
        # A room cannot be booked if another active booking overlaps the requested dates.
        overlap = db().execute("""
          SELECT id FROM bookings WHERE room_id=? AND status='Active'
          AND check_in < ? AND check_out > ?
        """, (room_id, check_out, check_in)).fetchone()
        if overlap:
            flash("This room is already booked for some of those dates. Please choose other dates or a different room.", "error")
            return render_template("book.html", room=room)
        nights = (co-ci).days
        total = nights * room["price"]
        db().execute("INSERT INTO bookings(user_id,room_id,check_in,check_out,guests,total) VALUES(?,?,?,?,?,?)",
                     (g.user["id"], room_id, check_in, check_out, guests, total))
        db().commit()
        flash("Your reservation has been created.", "success")
        return redirect(url_for("my_bookings"))
    return render_template("book.html", room=room)

@app.route("/my-bookings")
@login_required
def my_bookings():
    rows = db().execute("""
      SELECT b.*, r.name AS room_name, r.room_type
      FROM bookings b JOIN rooms r ON r.id=b.room_id
      WHERE b.user_id=? ORDER BY b.created_at DESC
    """, (g.user["id"],)).fetchall()
    return render_template("my_bookings.html", bookings=rows)

@app.route("/booking/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    booking = db().execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    if not booking:
        abort(404)
    if booking["user_id"] != g.user["id"] and g.user["role"] != "admin":
        abort(403)
    if booking["status"] == "Active":
        db().execute("UPDATE bookings SET status='Cancelled' WHERE id=?", (booking_id,))
        db().commit()
        flash("Booking cancelled.", "success")
    return redirect(url_for("admin") if g.user["role"]=="admin" else url_for("my_bookings"))

@app.route("/admin")
@admin_required
def admin():
    conn = db()
    bookings = conn.execute("""
      SELECT b.*, u.name AS customer_name, u.email, r.name AS room_name
      FROM bookings b JOIN users u ON u.id=b.user_id JOIN rooms r ON r.id=b.room_id
      ORDER BY b.created_at DESC
    """).fetchall()
    rooms = conn.execute("SELECT * FROM rooms ORDER BY id DESC").fetchall()
    users = conn.execute("SELECT id,name,email,role,created_at FROM users ORDER BY created_at DESC").fetchall()
    stats = {
      "rooms": conn.execute("SELECT COUNT(*) FROM rooms WHERE active=1").fetchone()[0],
      "bookings": conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0],
      "users": conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0],
    }
    return render_template("admin.html", bookings=bookings, rooms=rooms, users=users, stats=stats)

@app.route("/admin/rooms/add", methods=["POST"])
@admin_required
def add_room():
    name=request.form.get("name","").strip()
    room_type=request.form.get("room_type","Deluxe").strip()
    description=request.form.get("description","").strip()
    try:
        price=int(request.form.get("price","0")); capacity=int(request.form.get("capacity","2"))
        if not name or not description or price < 1 or not 1 <= capacity <= 10: raise ValueError
    except ValueError:
        flash("Please provide valid room details.", "error")
        return redirect(url_for("admin")+"#rooms")
    db().execute("INSERT INTO rooms(name,room_type,description,price,capacity,emoji) VALUES(?,?,?,?,?,?)",
                 (name,room_type,description,price,capacity,request.form.get("emoji","🛏️")[:8]))
    db().commit()
    flash("Room added.", "success")
    return redirect(url_for("admin")+"#rooms")

@app.route("/admin/rooms/<int:room_id>/toggle", methods=["POST"])
@admin_required
def toggle_room(room_id):
    room=db().execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
    if not room: abort(404)
    db().execute("UPDATE rooms SET active=? WHERE id=?", (0 if room["active"] else 1, room_id))
    db().commit()
    flash("Room availability updated.", "success")
    return redirect(url_for("admin")+"#rooms")

@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="We couldn't find that page."), 404

init_db()
if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
