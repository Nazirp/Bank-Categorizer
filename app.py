#!/usr/bin/env python3
"""
app.py — a small local web page for the bank statement categorizer.

Run it with:
    python3 app.py

then open http://127.0.0.1:8000 in your browser, pick a statement PDF,
and click "Analyze".

How it fits together:
  - Flask is a tiny web framework: it listens for browser requests and
    decides what to send back.
  - The page itself lives in templates/index.html.
  - The actual PDF reading and categorizing is done by the functions in
    categorize_statement.py — this file just connects them to the page.

Privacy: the uploaded PDF is read straight from memory and never saved to
disk, and the server only listens on 127.0.0.1, so nothing outside your
own laptop can reach it.
"""

import io

from flask import Flask, render_template, request

from categorize_statement import extract_transactions, summarize

app = Flask(__name__)

# Refuse uploads bigger than 20 MB (a bank statement is usually < 1 MB).
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


@app.route("/", methods=["GET", "POST"])
def index():
    # GET = someone just opened the page: show the empty upload form.
    if request.method == "GET":
        return render_template("index.html")

    # POST = the form was submitted with a file.
    uploaded = request.files.get("statement")

    if uploaded is None or uploaded.filename == "":
        return render_template("index.html", error="Please choose a PDF file first.")

    if not uploaded.filename.lower().endswith(".pdf"):
        return render_template(
            "index.html", error=f"“{uploaded.filename}” isn't a PDF. Please pick a .pdf file."
        )

    # Read the upload into memory and hand it to the existing parser.
    pdf_bytes = io.BytesIO(uploaded.read())
    try:
        transactions = extract_transactions(pdf_bytes)
    except Exception:
        return render_template(
            "index.html",
            error="Couldn't read that file as a PDF. It may be damaged or password-protected.",
        )

    if not transactions:
        return render_template(
            "index.html",
            error=(
                "No transactions were found in this PDF. Its layout may differ from "
                "what the parser expects — try the terminal version with --debug to "
                "see the raw lines, then adjust DATE_LINE in categorize_statement.py."
            ),
        )

    return render_template(
        "index.html",
        summary=summarize(transactions),
        filename=uploaded.filename,
    )


@app.errorhandler(413)
def too_large(_error):
    return render_template("index.html", error="That file is too large (limit is 20 MB)."), 413


@app.template_filter("money")
def money(value):
    """Format numbers like 1234.5 -> '1,234.50' inside the HTML template."""
    return f"{value:,.2f}"


if __name__ == "__main__":
    # Port 8000 rather than Flask's default 5000, because on macOS port
    # 5000 is taken by the AirPlay Receiver and you'd get a 403 error.
    app.run(host="127.0.0.1", port=8000, debug=True)
