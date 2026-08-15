import os
import sqlite3
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_from_directory
)

from werkzeug.utils import secure_filename


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

# IMPORTANT:
# Change this before putting the website into production.
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-secret-key"
)


# =========================================================
# MAXIMUM UPLOAD SIZE
# =========================================================

# 5 GB maximum upload
app.config["MAX_CONTENT_LENGTH"] = (
    5 * 1024 * 1024 * 1024
)


# =========================================================
# PROJECT DIRECTORIES
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


# =========================================================
# DATABASE
# =========================================================

DATABASE = os.path.join(
    BASE_DIR,
    "movies.db"
)


# =========================================================
# UPLOAD DIRECTORIES
# =========================================================

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "static",
    "uploads"
)

POSTER_FOLDER = os.path.join(
    UPLOAD_FOLDER,
    "posters"
)

VIDEO_FOLDER = os.path.join(
    UPLOAD_FOLDER,
    "videos"
)


# Create folders automatically
os.makedirs(
    POSTER_FOLDER,
    exist_ok=True
)

os.makedirs(
    VIDEO_FOLDER,
    exist_ok=True
)


# =========================================================
# ALLOWED FILE TYPES
# =========================================================

ALLOWED_POSTERS = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}


ALLOWED_VIDEOS = {
    "mp4",
    "webm",
    "ogg",
    "mov"
}


# =========================================================
# ADMIN LOGIN
# =========================================================

ADMIN_USERNAME = os.environ.get(
    "ADMIN_USERNAME",
    "admin"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "admin123"
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():

    connection = sqlite3.connect(
        DATABASE
    )

    connection.row_factory = sqlite3.Row

    return connection


# =========================================================
# CREATE DATABASE
# =========================================================

def create_database():

    connection = get_db()

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS movies (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            title TEXT NOT NULL,

            year TEXT DEFAULT '',

            genre TEXT DEFAULT '',

            description TEXT DEFAULT '',

            poster TEXT DEFAULT '',

            movie_file TEXT DEFAULT ''

        )
        """
    )

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

    column_names = {
        column["name"]
        for column in columns
    }

    # Add missing columns to old databases

    if "year" not in column_names:

        connection.execute(
            """
            ALTER TABLE movies
            ADD COLUMN year TEXT DEFAULT ''
            """
        )


    if "genre" not in column_names:

        connection.execute(
            """
            ALTER TABLE movies
            ADD COLUMN genre TEXT DEFAULT ''
            """
        )


    if "description" not in column_names:

        connection.execute(
            """
            ALTER TABLE movies
            ADD COLUMN description TEXT DEFAULT ''
            """
        )


    if "poster" not in column_names:

        connection.execute(
            """
            ALTER TABLE movies
            ADD COLUMN poster TEXT DEFAULT ''
            """
        )


    if "movie_file" not in column_names:

        connection.execute(
            """
            ALTER TABLE movies
            ADD COLUMN movie_file TEXT DEFAULT ''
            """
        )


    connection.commit()

    connection.close()


# =========================================================
# INITIALIZE DATABASE
# =========================================================

# IMPORTANT:
# This is OUTSIDE the __main__ block.
#
# Gunicorn imports app.py, so this makes sure the
# movies table exists when Render starts the website.

create_database()

migrate_database()


# =========================================================
# FILE EXTENSION CHECK
# =========================================================

def allowed_file(
    filename,
    allowed_extensions
):

    if not filename:

        return False


    if "." not in filename:

        return False


    extension = filename.rsplit(
        ".",
        1
    )[1].lower()


    return extension in allowed_extensions


# =========================================================
# ADMIN REQUIRED
# =========================================================

def admin_required(function):

    @wraps(function)
    def wrapper(
        *args,
        **kwargs
    ):

        if not session.get(
            "admin_logged_in"
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

        return render_template(
            "404.html"
        ), 404


    return render_template(
        "movie.html",
        movie=movie
    )


# =========================================================
# VIDEO STREAM
# =========================================================

@app.route(
    "/video/<filename>"
)
def video(filename):

    filename = secure_filename(
        filename
    )


    return send_from_directory(
        VIDEO_FOLDER,
        filename
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=[
        "GET",
        "POST"
    ]
)
def login():

    error = None


    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

