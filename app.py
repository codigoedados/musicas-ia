import os, sqlite3, uuid, secrets, hmac
from datetime import datetime, timezone
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, send_from_directory, send_file, abort, flash)
from werkzeug.middleware.proxy_fix import ProxyFix

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
THUMB_DIR = os.path.join(DATA_DIR, "thumbs")
AUDIO_DIR = os.path.join(DATA_DIR, "audio")
DB_PATH = os.path.join(DATA_DIR, "musicas.db")
for d in (THUMB_DIR, AUDIO_DIR):
    os.makedirs(d, exist_ok=True)

SITE_NAME = os.environ.get("SITE_NAME", "Mundo Novo da IA")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
THUMB_EXT = {"jpg", "jpeg", "png", "webp"}

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config.update(
    MAX_CONTENT_LENGTH=int(os.environ.get("MAX_UPLOAD_MB", 200)) * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# ---------- banco ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_):
    c = g.pop("db", None)
    if c: c.close()

def init_db():
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS songs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, artist TEXT DEFAULT '', description TEXT DEFAULT '',
        thumb TEXT, audio TEXT NOT NULL, duration INTEGER DEFAULT 0,
        plays INTEGER DEFAULT 0, downloads INTEGER DEFAULT 0,
        created_at TEXT NOT NULL)""")
    c.commit(); c.close()
init_db()

# ---------- utilidades ----------
def ago(iso):
    s = (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    for lim, un, pl in ((31536000, "ano", "anos"), (2592000, "mês", "meses"),
                        (86400, "dia", "dias"), (3600, "hora", "horas"), (60, "min", "min")):
        if s >= lim:
            n = int(s // lim)
            if un == "mês" and n > 1: return f"{n} meses atrás"
            return f"{n} {un if n == 1 else pl} atrás"
    return "agora"

def fmt_dur(sec):
    sec = int(sec or 0)
    return f"{sec // 60}:{sec % 60:02d}" if sec else ""

def compact(n):
    return f"{n/1000:.1f} mil".replace(".0", "") if n >= 1000 else str(n)

app.jinja_env.filters.update(ago=ago, dur=fmt_dur, compact=compact)

def save_file(f, folder, allowed):
    if not f or not f.filename: return None
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in allowed: return False
    name = f"{uuid.uuid4().hex}.{ext}"
    f.save(os.path.join(folder, name))
    return name

def rm(folder, name):
    if name:
        try: os.remove(os.path.join(folder, name))
        except OSError: pass

def csrf_token():
    if "csrf" not in session: session["csrf"] = secrets.token_hex(16)
    return session["csrf"]
app.jinja_env.globals.update(csrf=csrf_token, site_name=SITE_NAME)

@app.before_request
def check_csrf():
    if request.method == "POST" and request.endpoint != "play":
        if not hmac.compare_digest(request.form.get("csrf", ""), session.get("csrf", "x")):
            abort(400, "Sessão expirada. Recarregue a página.")

def admin_required(fn):
    @wraps(fn)
    def w(*a, **k):
        if not session.get("admin"): return redirect(url_for("login"))
        return fn(*a, **k)
    return w

# ---------- público ----------
@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "recent")
    order = {"recent": "id DESC", "popular": "downloads + plays DESC, id DESC",
             "old": "id ASC"}.get(sort, "id DESC")
    sql, args = "SELECT * FROM songs", []
    if q:
        sql += " WHERE title LIKE ? OR artist LIKE ?"; args += [f"%{q}%"] * 2
    songs = db().execute(f"{sql} ORDER BY {order}", args).fetchall()
    return render_template("index.html", songs=songs, q=q, sort=sort)

@app.route("/media/<kind>/<name>")
def media(kind, name):
    folder = {"thumb": THUMB_DIR, "audio": AUDIO_DIR}.get(kind) or abort(404)
    return send_from_directory(folder, name, conditional=True, max_age=86400)

@app.route("/download/<int:sid>")
def download(sid):
    s = db().execute("SELECT * FROM songs WHERE id=?", (sid,)).fetchone() or abort(404)
    db().execute("UPDATE songs SET downloads=downloads+1 WHERE id=?", (sid,)); db().commit()
    return send_file(os.path.join(AUDIO_DIR, s["audio"]), as_attachment=True,
                     download_name=f"{s['title']}.mp3".replace("/", "-"),
                     mimetype="audio/mpeg")

@app.route("/play/<int:sid>", methods=["POST"])
def play(sid):
    db().execute("UPDATE songs SET plays=plays+1 WHERE id=?", (sid,)); db().commit()
    return "", 204

# ---------- admin ----------
@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Senha incorreta.", "err")
    return render_template("login.html")

@app.route("/admin/logout", methods=["POST"])
def logout():
    session.pop("admin", None)
    return redirect(url_for("index"))

@app.route("/admin")
@app.route("/admin/<int:sid>/editar")
@admin_required
def admin(sid=None):
    song = db().execute("SELECT * FROM songs WHERE id=?", (sid,)).fetchone() if sid else None
    songs = db().execute("SELECT * FROM songs ORDER BY id DESC").fetchall()
    return render_template("admin.html", songs=songs, song=song)

@app.route("/admin/salvar", methods=["POST"])
@admin_required
def salvar():
    f = request.form
    sid = f.get("id", type=int)
    title = f.get("title", "").strip()
    if not title:
        flash("Informe o título da música.", "err"); return redirect(request.referrer or url_for("admin"))
    old = db().execute("SELECT * FROM songs WHERE id=?", (sid,)).fetchone() if sid else None

    thumb = save_file(request.files.get("thumb"), THUMB_DIR, THUMB_EXT)
    audio = save_file(request.files.get("audio"), AUDIO_DIR, {"mp3"})
    if thumb is False or audio is False:
        rm(THUMB_DIR, thumb or None); rm(AUDIO_DIR, audio or None)
        flash("Formato inválido. Use JPG/PNG/WEBP na capa e MP3 no áudio.", "err")
        return redirect(request.referrer or url_for("admin"))
    if not old and not audio:
        rm(THUMB_DIR, thumb)
        flash("Envie o arquivo MP3.", "err"); return redirect(url_for("admin"))

    dur = f.get("duration", type=int) or 0
    if old:
        if thumb: rm(THUMB_DIR, old["thumb"])
        if audio: rm(AUDIO_DIR, old["audio"])
        db().execute("""UPDATE songs SET title=?, artist=?, description=?, thumb=?, audio=?, duration=?
                        WHERE id=?""",
                     (title, f.get("artist", "").strip(), f.get("description", "").strip(),
                      thumb or old["thumb"], audio or old["audio"], dur if audio else old["duration"], sid))
        flash("Música atualizada.", "ok")
    else:
        db().execute("""INSERT INTO songs(title,artist,description,thumb,audio,duration,created_at)
                        VALUES(?,?,?,?,?,?,?)""",
                     (title, f.get("artist", "").strip(), f.get("description", "").strip(),
                      thumb, audio, dur, datetime.now(timezone.utc).isoformat()))
        flash("Música publicada.", "ok")
    db().commit()
    return redirect(url_for("admin"))

@app.route("/admin/<int:sid>/excluir", methods=["POST"])
@admin_required
def excluir(sid):
    s = db().execute("SELECT * FROM songs WHERE id=?", (sid,)).fetchone() or abort(404)
    rm(THUMB_DIR, s["thumb"]); rm(AUDIO_DIR, s["audio"])
    db().execute("DELETE FROM songs WHERE id=?", (sid,)); db().commit()
    flash("Música excluída.", "ok")
    return redirect(url_for("admin"))

@app.errorhandler(413)
def too_big(_):
    flash("Arquivo maior que o limite permitido.", "err")
    return redirect(url_for("admin"))

@app.route("/healthz")
def healthz(): return "ok"
