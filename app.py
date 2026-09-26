import os
import sqlite3
from contextlib import contextmanager
from flask import Flask, flash, redirect, render_template, request, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "beginner-library-app")

DATABASE = os.path.join(os.path.dirname(__file__), "library.db")


@contextmanager
def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    with get_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                author TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Available'
                    CHECK (status IN ('Available', 'Issued'))
            );

            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS issued (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL UNIQUE,
                member_id INTEGER NOT NULL,
                FOREIGN KEY (book_id) REFERENCES books (id),
                FOREIGN KEY (member_id) REFERENCES members (id)
            );
            """
        )


init_db()

@app.route("/")
def home():
    with get_db() as connection:
        total = connection.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        available = connection.execute(
            "SELECT COUNT(*) FROM books WHERE status = 'Available'"
        ).fetchone()[0]
        issued = connection.execute(
            "SELECT COUNT(*) FROM books WHERE status = 'Issued'"
        ).fetchone()[0]
    return render_template(
        "index.html", total=total, available=available, issued=issued
    )


@app.route("/books", methods=["GET", "POST"])
def books():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        author = request.form.get("author", "").strip()
        if not name or not author:
            flash("Enter both a book name and author.", "error")
        else:
            with get_db() as connection:
                connection.execute(
                    "INSERT INTO books (name, author) VALUES (?, ?)",
                    (name, author),
                )
            flash("Book added.", "success")
            return redirect(url_for("books"))

    search = request.args.get("search", "").strip()
    with get_db() as connection:
        if search:
            search_id = search.upper()
            if search_id.startswith("BK-"):
                search_id = search_id[3:]
            search_id = search_id.lstrip("0") or "0"
            book_rows = connection.execute(
                """SELECT * FROM books
                   WHERE name LIKE ? OR CAST(id AS TEXT) = ?
                   ORDER BY id DESC""",
                (f"%{search}%", search_id),
            ).fetchall()
        else:
            book_rows = connection.execute(
                "SELECT * FROM books ORDER BY id DESC"
            ).fetchall()
    return render_template("books.html", books=book_rows, search=search)


@app.route("/members", methods=["GET", "POST"])
def members():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Enter a member name.", "error")
        else:
            with get_db() as connection:
                connection.execute("INSERT INTO members (name) VALUES (?)", (name,))
            flash("Member added.", "success")
            return redirect(url_for("members"))

    with get_db() as connection:
        member_rows = connection.execute(
            "SELECT * FROM members ORDER BY id DESC"
        ).fetchall()
    return render_template("members.html", members=member_rows)


@app.route("/issue", methods=["GET", "POST"])
def issue():
    if request.method == "POST":
        book_id = request.form.get("book_id", type=int)
        member_id = request.form.get("member_id", type=int)
        if not book_id or not member_id:
            flash("Choose both a member and an available book.", "error")
        else:
            with get_db() as connection:
                book = connection.execute(
                    "SELECT id, status FROM books WHERE id = ?", (book_id,)
                ).fetchone()
                member = connection.execute(
                    "SELECT id FROM members WHERE id = ?", (member_id,)
                ).fetchone()
                if not book or not member:
                    flash("That book or member could not be found.", "error")
                elif book["status"] != "Available":
                    flash("That book is already issued.", "error")
                else:
                    connection.execute(
                        "INSERT INTO issued (book_id, member_id) VALUES (?, ?)",
                        (book_id, member_id),
                    )
                    connection.execute(
                        "UPDATE books SET status = 'Issued' WHERE id = ?", (book_id,)
                    )
                    flash("Book issued.", "success")
                    return redirect(url_for("issue"))

    with get_db() as connection:
        available_books = connection.execute(
            "SELECT id, name, author FROM books WHERE status = 'Available' ORDER BY name"
        ).fetchall()
        member_rows = connection.execute(
            "SELECT id, name FROM members ORDER BY name"
        ).fetchall()
        issued_books = connection.execute(
            """SELECT books.id, books.name, books.author, members.name AS member_name
               FROM issued
               JOIN books ON books.id = issued.book_id
               JOIN members ON members.id = issued.member_id
               ORDER BY books.name"""
        ).fetchall()
    return render_template(
        "issue.html",
        available_books=available_books,
        members=member_rows,
        issued_books=issued_books,
    )


@app.route("/return/<int:book_id>", methods=["POST"])
def return_book(book_id):
    with get_db() as connection:
        issue_row = connection.execute(
            "SELECT id FROM issued WHERE book_id = ?", (book_id,)
        ).fetchone()
        book = connection.execute(
            "SELECT status FROM books WHERE id = ?", (book_id,)
        ).fetchone()
        if not book or book["status"] == "Available" or not issue_row:
            flash("That book is already available or does not exist.", "error")
        else:
            connection.execute("DELETE FROM issued WHERE id = ?", (issue_row["id"],))
            connection.execute(
                "UPDATE books SET status = 'Available' WHERE id = ?", (book_id,)
            )
            flash("Book returned.", "success")
    return redirect(url_for("issue"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
