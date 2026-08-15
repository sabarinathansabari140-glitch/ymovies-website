import os
import sqlite3
import secrets
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_from_directory,
    abort,
)
from werkzeug.utils import secure_filename


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)

# IMPORTANT:
# On Render, create SECRET_KEY as an environment variable.
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)

# Maximum upload size = 5 GB
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024 * 1024


# =========================================================
# DIRECTORIES
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

UPLOAD_DIR = BASE_DIR / "static" / "uploads"

POSTER_DIR = UPLOAD_DIR / "posters"

MOVIE_DIR = UPLOAD_DIR / "movies"


# Create directories automatically
DATA_DIR.mkdir(parents=True, exist_ok=True)
POSTER_DIR.mkdir(parents=True, exist_ok=True)
MOVIE_DIR.mkdir(parents=True, exist_ok=True)


DATABASE = DATA_DIR / "movies.db"


# =========================================================
# ALLOWED FILE TYPES
# =========================================================

ALLOWED_POSTER_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
}

ALLOWED_MOVIE_EXTENSIONS = {
    "mp4",
    "webm",
    "ogg",
    "m4v",
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

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )
    """)

    connection.commit()

    connection.close()


# =========================================================
# DATABASE MIGRATION
# =========================================================

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
        "movie_file": "TEXT",
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


# Create/migrate database when app starts
create_database()
migrate_database()


# =========================================================
# ADMIN SETTINGS
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


# =========================================================
# ADMIN LOGIN CHECK
# =========================================================

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
# FILE HELPERS
# =========================================================

def allowed_file(filename, allowed_extensions):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    return extension in allowed_extensions


def create_safe_filename(filename):

    original_name = secure_filename(
        filename
    )

    if not original_name:

        return None

    random_name = secrets.token_hex(12)

    extension = ""

    if "." in original_name:

        extension = (
            "."
            + original_name.rsplit(
                ".",
                1
            )[1].lower()
        )

    return random_name + extension


# =========================================================
# HOME PAGE
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
                f"%{search}%",
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

    # Already logged in
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

        correct_username = (
            get_admin_username()
        )

        correct_password = (
            get_admin_password()
        )

        if (
            secrets.compare_digest(
                username,
                correct_username
            )
            and
            secrets.compare_digest(
                password,
                correct_password
            )
        ):

            session.clear()

            session["admin_logged_in"] = True

            session["admin_username"] = username

            return redirect(
                url_for("admin")
            )

        error = (
            "Incorrect username or password."
        )

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

    poster_file = request.files.get(
        "poster"
    )

    movie_file = request.files.get(
        "movie_file"
    )

    # -----------------------------------------
    # TITLE CHECK
    # -----------------------------------------

    if not title:

        return redirect(
            url_for(
                "admin",
                error="Movie title is required."
            )
        )


    # -----------------------------------------
    # POSTER
    # -----------------------------------------

    poster_filename = None

    if poster_file:

        if poster_file.filename:

            if not allowed_file(
                poster_file.filename,
                ALLOWED_POSTER_EXTENSIONS
            ):

                return redirect(
                    url_for(
                        "admin",
                        error=(
                            "Invalid poster format."
                        )
                    )
                )

            poster_filename = (
                create_safe_filename(
                    poster_file.filename
                )
            )

            if not poster_filename:

                return redirect(
                    url_for(
                        "admin",
                        error=(
                            "Invalid poster filename."
                        )
                    )
                )

            poster_file.save(
                str(
                    POSTER_DIR
                    / poster_filename
                )
            )


    # -----------------------------------------
    # MOVIE FILE
    # -----------------------------------------

    movie_filename = None

    if movie_file:

        if movie_file.filename:

            if not allowed_file(
                movie_file.filename,
                ALLOWED_MOVIE_EXTENSIONS
            ):

                return redirect(
                    url_for(
                        "admin",
                        error=(
                            "Invalid movie format. "
                            "Use MP4, WebM, OGG or M4V."
                        )
                    )
                )

            movie_filename = (
                create_safe_filename(
                    movie_file.filename
                )
            )

            if not movie_filename:

                return redirect(
                    url_for(
                        "admin",
                        error=(
                            "Invalid movie filename."
                        )
                    )
                )

            movie_file.save(
                str(
                    MOVIE_DIR
                    / movie_filename
                )
            )


    # -----------------------------------------
    # DATABASE
    # -----------------------------------------

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
# MOVIE DETAILS
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


    # -----------------------------------------
    # DELETE POSTER FILE
    # -----------------------------------------

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


    # -----------------------------------------
    # DELETE MOVIE FILE
    # -----------------------------------------

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


    # -----------------------------------------
    # DELETE DATABASE RECORD
    # -----------------------------------------

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
# SERVE MOVIE FILES
# =========================================================

@app.route(
    "/videos/<path:filename>"
)
def serve_video(filename):

    return send_from_directory(
        MOVIE_DIR,
        filename
    )


# =========================================================
# SERVE POSTER FILES
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
# 404
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return render_template(
        "404.html"
    ), 404


# =========================================================
# 413 - FILE TOO LARGE
# =========================================================

@app.errorhandler(413)
def file_too_large(error):

    return (
        """
        <h1>File too large</h1>
        <p>
        The maximum upload size is 5 GB.
        </p>
        """,
        413
    )


# =========================================================
# 500
# =========================================================

@app.errorhandler(500)
def server_error(error):

    return (
        """
        <h1>Server error</h1>
        <p>
        Something went wrong on the server.
        </p>
        """,
        500
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/test")
def test():

    return "MyMovies Flask website is working!"


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