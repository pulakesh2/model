import os
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
DB_PATH = BASE_DIR / "photo_ratings.db"
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-this-secret"),
    # Leave room for multipart headers while keeping the uploaded file itself at 100 MB.
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES + 64 * 1024,
)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            caption TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 10),
            UNIQUE(post_id, user_id)
        );
        """
    )
    db.commit()


@app.before_request
def prepare_request():
    init_db()
    g.user = None
    user_id = session.get("user_id")
    if user_id:
        g.user = get_db().execute(
            "SELECT id, username, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if g.user is None:
            session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Log in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token
app.jinja_env.globals["is_video"] = lambda filename: filename.rsplit(".", 1)[-1].lower() in VIDEO_EXTENSIONS


@app.before_request
def verify_csrf():
    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            abort(400, description="Your form session expired. Refresh the page and try again.")


def valid_media_name(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
@login_required
def feed():
    db = get_db()
    posts = db.execute(
        """
        SELECT p.id, p.filename, p.caption, p.created_at, p.user_id,
               u.username,
               ROUND(AVG(r.score), 1) AS average_rating,
               COUNT(r.id) AS rating_count,
               mine.score AS my_rating
        FROM posts p
        JOIN users u ON u.id = p.user_id
        LEFT JOIN ratings r ON r.post_id = p.id
        LEFT JOIN ratings mine ON mine.post_id = p.id AND mine.user_id = ?
        GROUP BY p.id
        ORDER BY p.id DESC
        """,
        (g.user["id"],),
    ).fetchall()
    return render_template("feed.html", posts=posts)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if g.user:
        return redirect(url_for("feed"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not username or len(username) > 32 or any(ch.isspace() for ch in username):
            flash("Choose a username with 1–32 characters and no spaces.", "error")
        elif "@" not in email or len(email) > 254:
            flash("Enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Your password must be at least 8 characters.", "error")
        else:
            db = get_db()
            try:
                cur = db.execute(
                    "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (username, email, generate_password_hash(password), datetime.now().astimezone().isoformat(timespec="seconds")),
                )
                db.commit()
                session.clear()
                session["user_id"] = cur.lastrowid
                flash("Your account is ready. Share your first photo!", "success")
                return redirect(url_for("feed"))
            except sqlite3.IntegrityError:
                flash("That username or email is already registered.", "error")
    return render_template("auth.html", mode="signup")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("feed"))
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ? OR email = ?", (identity, identity.lower())
        ).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            flash("Welcome back!", "success")
            target = request.args.get("next", "")
            if target.startswith("/") and not target.startswith("//"):
                return redirect(target)
            return redirect(url_for("feed"))
        flash("The username/email or password is incorrect.", "error")
    return render_template("auth.html", mode="login")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "GET":
        return render_template("upload.html")

    photo = request.files.get("media")
    caption = request.form.get("caption", "").strip()
    if not photo or not photo.filename:
        flash("Choose an image or video to upload.", "error")
        return redirect(url_for("upload"))
    if not valid_media_name(photo.filename):
        flash("Use a PNG, JPG, GIF, WebP, MP4, WebM, or MOV file.", "error")
        return redirect(url_for("upload"))
    if len(caption) > 300:
        flash("Captions can be up to 300 characters.", "error")
        return redirect(url_for("upload"))
    safe_name = secure_filename(photo.filename)
    if "." not in safe_name:
        flash("That file name is not valid.", "error")
        return redirect(url_for("upload"))
    extension = safe_name.rsplit(".", 1)[1].lower()
    filename = f"{secrets.token_hex(16)}.{extension}"
    destination = UPLOAD_DIR / filename
    photo.save(destination)
    if destination.stat().st_size > MAX_UPLOAD_BYTES:
        destination.unlink(missing_ok=True)
        flash("That file is too large. The limit is 100 MB.", "error")
        return redirect(url_for("upload"))
    try:
        get_db().execute(
            "INSERT INTO posts (user_id, filename, caption, created_at) VALUES (?, ?, ?, ?)",
            (g.user["id"], filename, caption, datetime.now().astimezone().isoformat(timespec="seconds")),
        )
        get_db().commit()
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    flash("Your media is live.", "success")
    return redirect(url_for("feed"))


@app.route("/rate/<int:post_id>", methods=["POST"])
@login_required
def rate(post_id):
    score = request.form.get("score", type=int)
    db = get_db()
    post = db.execute("SELECT id, user_id FROM posts WHERE id = ?", (post_id,)).fetchone()
    if post is None:
        abort(404)
    if post["user_id"] == g.user["id"]:
        flash("You can’t rate your own photo.", "info")
    elif score is None or not 1 <= score <= 10:
        flash("Choose a rating from 1 to 10.", "error")
    else:
        db.execute(
            "INSERT INTO ratings (post_id, user_id, score) VALUES (?, ?, ?) "
            "ON CONFLICT(post_id, user_id) DO UPDATE SET score = excluded.score",
            (post_id, g.user["id"], score),
        )
        db.commit()
        flash("Your rating has been saved.", "success")
    return redirect(url_for("feed"))


@app.route("/account")
@login_required
def account():
    posts = get_db().execute(
        """
        SELECT p.id, p.filename, p.caption, p.created_at,
               ROUND(AVG(r.score), 1) AS average_rating,
               COUNT(r.id) AS rating_count
        FROM posts p LEFT JOIN ratings r ON r.post_id = p.id
        WHERE p.user_id = ? GROUP BY p.id ORDER BY p.id DESC
        """,
        (g.user["id"],),
    ).fetchall()
    return render_template("account.html", posts=posts)


@app.route("/posts/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    db = get_db()
    post = db.execute(
        "SELECT id, filename FROM posts WHERE id = ? AND user_id = ?",
        (post_id, g.user["id"]),
    ).fetchone()
    if post is None:
        abort(404)
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db.commit()
    (UPLOAD_DIR / post["filename"]).unlink(missing_ok=True)
    flash("Photo removed.", "success")
    return redirect(url_for("account"))


@app.errorhandler(413)
def too_large(_error):
    flash("That file is too large. The limit is 100 MB.", "error")
    return redirect(url_for("upload"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
