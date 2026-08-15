import os
import sqlite3
import secrets
from pathlib import Path
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    abort,
    send_from_directory
)

from werkzeug.utils import secure_filename


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)

# Maximum upload request = 5 GB
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024 * 1024


# =========================================================
# DIRECTORIES
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

UPLOAD_DIR = BASE_DIR / "static" / "uploads"

POSTER_DIR = UPLOAD_DIR / "posters"

MOVIE_DIR = UPLOAD_DIR / "movies"


DATA_DIR.mkdir(
    parents=True,
    exist_ok=True
)

POSTER_DIR.mkdir(
    parents=True,
    exist_ok=True
)

MOVIE_DIR.mkdir(
    parents=True,
    exist_ok=True
)


DATABASE = DATA_DIR / "movies.db"


# =========================================================
# ALLOWED FILE TYPES
# =========================================================

ALLOWED_POSTERS = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}

ALLOWED_MOVIES = {
    "mp4",
    "webm",
    "m4v",
    "ogg"
}


# =========================================================
# DATABASE
# =========================================================

def get_db():

    connection = sqlite3.connect(
        str(DATABASE)
    )

    connection.row_factory = sqlite3.Row

    return connection


def create_database():

    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS movies (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            title TEXT NOT NULL,

            year TEXT,

            genre TEXT,

            description TEXT,

            poster TEXT,

            movie_file TEXT,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP

        )
    """)

    connection.commit()

    connection.close()


def migrate_database():

    connection = get_db()

    columns = connection.execute(
        "PRAGMA table_info(movies)"
    ).fetchall()

    existing_columns = {
        column["name"]
        for column in columns
    }

    required_columns = {

        "year": "TEXT",

        "genre": "TEXT",

        "description": "TEXT",

        "poster": "TEXT",

        "movie_file": "TEXT"

    }

    for column_name, column_type in required_columns.items():

        if column_name not in existing_columns:

            connection.execute(
                f"""
                ALTER TABLE movies
                ADD COLUMN {column_name} {column_type}
                """
            )

    connection.commit()

    connection.close()


create_database()
migrate_database()


# =========================================================
# ADMIN LOGIN
# =========================================================

def get_admin_username():

    return os.environ.get(
        "ADMIN_USERNAME",
        "admin"
    )


def get_admin_password():

    return os.environ.get(
        "ADMIN_PASSWORD",
        "admin123"
    )


def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get(
            "admin_logged_in",
            False
        ):

            return redirect(
                url_for("login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


# =========================================================
# FILE FUNCTIONS
# =========================================================

def allowed_file(
    filename,
    extensions
):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = (
        filename
        .rsplit(".", 1)[1]
        .lower()
    )

    return extension in extensions


def make_unique_filename(filename):

    safe_name = secure_filename(
        filename
    )

    if not safe_name:
        return None

    if "." in safe_name:

        extension = (
            "."
            + safe_name.rsplit(
                ".",
                1
            )[1].lower()
        )

    else:

        extension = ""

    return (
        secrets.token_hex(16)
        + extension
    )


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    search = request.args.get(
        "search",
        ""
    ).strip()

    connection = get_db()

    if search:

        movies = connection.execute(
            """
            SELECT *
            FROM movies

            WHERE title LIKE ?
               OR genre LIKE ?
               OR year LIKE ?

            ORDER BY id DESC
            """,
            (
                f"%{search}%",
                f"%{search}%",
                f"%{search}%"
            )
        ).fetchall()

    else:

        movies = connection.execute(
            """
            SELECT *
            FROM movies
            ORDER BY id DESC
            """
        ).fetchall()

    connection.close()

    return render_template(
        "index.html",
        movies=movies,
        search=search
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if session.get(
        "admin_logged_in",
        False
    ):

        return redirect(
            url_for("admin")
        )

    error = None

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if (
            username == get_admin_username()
            and
            password == get_admin_password()
        ):

            session.clear()

            session["admin_logged_in"] = True

            session["admin_username"] = username

            return redirect(
                url_for("admin")
            )

        error = "Incorrect username or password."

    return render_template(
        "login.html",
        error=error
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
@admin_required
def admin():

    connection = get_db()

    movies = connection.execute(
        """
        SELECT *
        FROM movies
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    return render_template(
        "admin.html",
        movies=movies
    )


# =========================================================
# ADD MOVIE
# =========================================================

@app.route(
    "/admin/add",
    methods=["POST"]
)
@admin_required
def add_movie():

    title = request.form.get(
        "title",
        ""
    ).strip()

    year = request.form.get(
        "year",
        ""
    ).strip()

    genre = request.form.get(
        "genre",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()


    if not title:

        return (
            "Movie title is required.",
            400
        )


    # -----------------------------------------------------
    # POSTER
    # -----------------------------------------------------

    poster_filename = None

    poster = request.files.get(
        "poster"
    )

    if poster and poster.filename:

        if not allowed_file(
            poster.filename,
            ALLOWED_POSTERS
        ):

            return (
                "Invalid poster. "
                "Use JPG, JPEG, PNG or WEBP.",
                400
            )

        poster_filename = make_unique_filename(
            poster.filename
        )

        if not poster_filename:

            return (
                "Invalid poster filename.",
                400
            )

        poster_path = (
            POSTER_DIR
            / poster_filename
        )

        poster.save(
            str(poster_path)
        )


    # -----------------------------------------------------
    # MOVIE
    # -----------------------------------------------------

    movie_filename = None

    movie = request.files.get(
        "movie_file"
    )

    if movie and movie.filename:

        if not allowed_file(
            movie.filename,
            ALLOWED_MOVIES
        ):

            return (
                "Invalid movie format. "
                "Use MP4, WebM, M4V or OGG.",
                400
            )

        movie_filename = make_unique_filename(
            movie.filename
        )

        if not movie_filename:

            return (
                "Invalid movie filename.",
                400
            )

        movie_path = (
            MOVIE_DIR
            / movie_filename
        )

        try:

            # Werkzeug saves the uploaded
            # file without loading the
            # entire movie into memory.

            movie.save(
                str(movie_path)
            )

        except Exception as error:

            print(
                "MOVIE UPLOAD ERROR:",
                error
            )

            if movie_path.exists():

                try:
                    movie_path.unlink()
                except OSError:
                    pass

            return (
                "Movie upload failed.",
                500
            )

    else:

        return (
            "Please select a movie file.",
            400
        )


    # -----------------------------------------------------
    # DATABASE
    # -----------------------------------------------------

    connection = get_db()

    connection.execute(
        """
        INSERT INTO movies
        (
            title,
            year,
            genre,
            description,
            poster,
            movie_file
        )

        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            year,
            genre,
            description,
            poster_filename,
            movie_filename
        )
    )

    connection.commit()

    connection.close()


    return redirect(
        url_for("admin")
    )


# =========================================================
# MOVIE PAGE
# =========================================================

@app.route(
    "/movie/<int:movie_id>"
)
def movie_details(movie_id):

    connection = get_db()

    movie = connection.execute(
        """
        SELECT *
        FROM movies
        WHERE id = ?
        """,
        (movie_id,)
    ).fetchone()

    connection.close()

    if movie is None:

        abort(404)

    return render_template(
        "movie.html",
        movie=movie
    )


# =========================================================
# DELETE MOVIE
# =========================================================

@app.route(
    "/admin/delete/<int:movie_id>",
    methods=["POST"]
)
@admin_required
def delete_movie(movie_id):

    connection = get_db()

    movie = connection.execute(
        """
        SELECT *
        FROM movies
        WHERE id = ?
        """,
        (movie_id,)
    ).fetchone()

    if movie is None:

        connection.close()

        abort(404)


    # Delete poster

    if movie["poster"]:

        poster_path = (
            POSTER_DIR
            / movie["poster"]
        )

        if poster_path.exists():

            try:
                poster_path.unlink()
            except OSError:
                pass


    # Delete movie

    if movie["movie_file"]:

        movie_path = (
            MOVIE_DIR
            / movie["movie_file"]
        )

        if movie_path.exists():

            try:
                movie_path.unlink()
            except OSError:
                pass


    connection.execute(
        """
        DELETE FROM movies
        WHERE id = ?
        """,
        (movie_id,)
    )

    connection.commit()

    connection.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# POSTER
# =========================================================

@app.route(
    "/posters/<path:filename>"
)
def serve_poster(filename):

    return send_from_directory(
        POSTER_DIR,
        filename
    )


# =========================================================
# VIDEO
# =========================================================

@app.route(
    "/videos/<path:filename>"
)
def serve_video(filename):

    return send_from_directory(
        MOVIE_DIR,
        filename,
        conditional=True
    )


# =========================================================
# TEST
# =========================================================

@app.route("/test")
def test():

    return "MyMovies server is working!"


# =========================================================
# FILE TOO LARGE
# =========================================================

@app.errorhandler(413)
def file_too_large(error):

    return """
    <html>

    <head>
        <title>File Too Large</title>
    </head>

    <body style="
        font-family:Arial;
        text-align:center;
        padding:60px;
    ">

        <h1>File Too Large</h1>

        <p>
            The maximum Flask upload size is 5 GB.
        </p>

        <a href="/admin">
            ← Back to Admin
        </a>

    </body>

    </html>
    """, 413


# =========================================================
# NOT FOUND
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return """
    <html>

    <head>
        <title>Not Found</title>
    </head>

    <body style="
        font-family:Arial;
        text-align:center;
        padding:60px;
    ">

        <h1>404</h1>

        <p>
            Page not found.
        </p>

        <a href="/">
            ← Back Home
        </a>

    </body>

    </html>
    """, 404


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )