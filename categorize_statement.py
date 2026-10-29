#!/usr/bin/env python3
"""
categorize_statement.py

Reads a bank / credit-card statement PDF and groups the expenses it finds
into categories (Groceries, Subscriptions, Transactions, Other).

This file is used two ways:

  1. From the terminal:
         python3 categorize_statement.py path/to/statement.pdf

  2. By the web app (app.py), which imports extract_transactions() and
     summarize() from here. All the parsing/categorizing logic lives in
     this one file, so if you tweak a keyword or the regex, both the
     terminal version and the web page pick up the change.

CUSTOMIZING FOR YOUR OWN STATEMENTS
------------------------------------
Every bank formats its statements differently. This script was built and
tested against a German credit-card statement where each transaction line
looks like:

    DD.MM.YYYY   Description   [Location]   Amount

If your statement doesn't produce any results, run the terminal version
with --debug to see the raw lines the script is reading, then adjust the
DATE_LINE regex or the CATEGORY_RULES keyword lists below.
"""

import argparse
import re
import sys
from collections import defaultdict

try:
    import pdfplumber
except ImportError:
    sys.exit(
        "Missing dependency 'pdfplumber'.\n"
        "Install it with:\n\n    python3 -m pip install -r requirements.txt\n"
    )

# ---------------------------------------------------------------------------
# 1. CATEGORY RULES
#
#    Add, remove, or edit keywords here to fit your own statements and
#    spending habits. Matching is case-insensitive and looks for the
#    keyword ANYWHERE inside the transaction description. Categories are
#    checked top to bottom and the first match wins, so put more specific
#    rules above more general ones. Add a whole new category by adding a
#    new "Name": [keywords...] entry.
# ---------------------------------------------------------------------------
CATEGORY_RULES = {
    "Groceries": [
        "edeka", "rewe", "aldi", "lidl", "kaufland", "netto", "penny",
        "dm drogerie", "dm-drogerie", "rossmann", "whole foods",
        "trader joe", "walmart", "safeway", "kroger", "tesco",
        "sainsbury", "carrefour", "supermarket", "grocery", "sila", "eurogida", "euro gida"
    ],
    "Subscriptions": [
        "netflix", "spotify", "anthropic", "claude sub", "amazon prime",
        "*prime", "youtube premium", "apple.com/bill", "disney+",
        "hbo max", "icloud", "google *", " sub ", " abo", "subscription",
        "patreon", "audible", "onthatass"
    ],
    "Transactions": [
        "einzahlung", "uberweisung", "überweisung", "zahlung eingang",
        "transfer", "payment received", "gutschrift", "lastschrift",
        "direct debit", "standing order", "dauerauftrag",
    ],
    "Restaurants": [
        "sanku", "yangguofu", "doner", "kebap", "döner",
    ],
    "Shopping": [
        "amazon", "zalando", "ebay", "new yorker", "h&m"
    ],
    "Travel": [
        "flix", "db", "detusche bahn",
    ],
    "Scooter": [
        "lime", "voi", "bolt", "nextbike",
    ]
    # Feel free to split "Other" further, e.g.:
    # "Dining": ["burger king", "mcdonald", "restaurant", "cafe"],
    # "Shopping": ["amazon", "zalando", "ebay"],
    # "Fees": ["sollzinsen", "interest", "annual fee", "jahresgebuhr"],
}

# Lines that describe the statement itself rather than a real transaction
# (opening/closing balance, etc.) — these are skipped entirely so they
# don't get miscounted as spending.
SKIP_KEYWORDS = [
    "alter saldo", "neuer saldo", "saldo vortrag",
    "opening balance", "closing balance", "new balance", "previous balance",
]

# Matches lines like: "03.07.2026  EDEKA 5520  BERLIN  0,84"
#   date:   DD.MM.YYYY (or DD/MM/YY etc.)
#   desc:   everything in between
#   amount: European "1.234,56" or plain "12,34" / "12.34"
DATE_LINE = re.compile(
    r"^(?P<date>\d{2}[./]\d{2}[./]\d{2,4})\s+(?P<desc>.+?)\s+"
    r"(?P<amount>-?\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*$"
)


def parse_amount(raw):
    """Convert '1.234,56' or '12,34' or '12.34' into a float."""
    raw = raw.strip()
    if "," in raw and "." in raw:
        # '.' is a thousands separator, ',' is the decimal point
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    return float(raw)


def date_sort_key(date_str):
    """Turn '03.07.2026' into (2026, 7, 3) so dates sort chronologically
    instead of alphabetically (where '01.08' would wrongly come before '03.07')."""
    day, month, year = re.split(r"[./]", date_str)
    return (int(year), int(month), int(day))


def extract_transactions(pdf_source, debug=False):
    """Read transactions out of a PDF.

    pdf_source can be a file path (terminal version) or an open file-like
    object such as an uploaded file (web version) — pdfplumber accepts both.
    """
    transactions = []
    with pdfplumber.open(pdf_source) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if debug:
                    print(f"[page {page_num}] {line}")
                match = DATE_LINE.match(line)
                if not match:
                    continue
                desc = match.group("desc").strip()
                if any(skip in desc.lower() for skip in SKIP_KEYWORDS):
                    continue
                transactions.append({
                    "date": match.group("date"),
                    "description": desc,
                    "amount": parse_amount(match.group("amount")),
                })
    return transactions


def categorize(description):
    desc_lower = description.lower()
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in desc_lower for keyword in keywords):
            return category
    return "Other"


def summarize(transactions):
    """Group transactions by category and compute totals.

    Returns a plain dict that both the terminal printer and the web page
    template use:
        {
          "categories": [
              {"name": "Groceries", "count": 30, "subtotal": 403.45,
               "share": 51.5, "transactions": [...]},
              ...
          ],
          "total_spent": 783.96,     # positive amounts (money going out)
          "total_credits": -1200.0,  # negative amounts (payments/refunds)
          "count": 52,
        }
    """
    grouped = defaultdict(list)
    for tx in transactions:
        grouped[categorize(tx["description"])].append(tx)

    total_spent = sum(tx["amount"] for tx in transactions if tx["amount"] > 0)
    total_credits = sum(tx["amount"] for tx in transactions if tx["amount"] < 0)

    categories = []
    for name in list(CATEGORY_RULES.keys()) + ["Other"]:
        items = grouped.get(name, [])
        if not items:
            continue
        subtotal = sum(tx["amount"] for tx in items)
        spent_here = sum(tx["amount"] for tx in items if tx["amount"] > 0)
        categories.append({
            "name": name,
            "count": len(items),
            "subtotal": subtotal,
            # What % of total spending this category is (credits don't count)
            "share": (spent_here / total_spent * 100) if total_spent else 0,
            "transactions": sorted(items, key=lambda t: date_sort_key(t["date"])),
        })

    return {
        "categories": categories,
        "total_spent": total_spent,
        "total_credits": total_credits,
        "count": len(transactions),
    }


def print_summary(summary, source_name):
    print(f"\nFound {summary['count']} transaction(s) in {source_name}")
    print("=" * 64)
    for cat in summary["categories"]:
        print(f"\n{cat['name']}  ({cat['count']} transaction(s), subtotal: {cat['subtotal']:,.2f})")
        print("-" * 64)
        for tx in cat["transactions"]:
            print(f"  {tx['date']}  {tx['description']:<40} {tx['amount']:>10,.2f}")
    print("\n" + "=" * 64)
    print(f"Total spending (excludes payments/credits): {summary['total_spent']:,.2f}")
    if summary["total_credits"]:
        print(f"Payments / credits received:                {summary['total_credits']:,.2f}")
    print("=" * 64 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Group a bank/credit-card statement PDF's expenses by category."
    )
    parser.add_argument("pdf", help="Path to the statement PDF")
    parser.add_argument(
        "--debug", action="store_true",
        help="Print every line read from the PDF (useful for tuning the regex to your bank's layout)",
    )
    args = parser.parse_args()

    transactions = extract_transactions(args.pdf, debug=args.debug)
    if not transactions:
        print(
            "\nNo transactions found.\n"
            "Your statement's layout may differ from what this script expects.\n"
            "Re-run with --debug to see the raw lines, then adjust DATE_LINE\n"
            "near the top of this file to match your bank's format.\n"
        )
        return

    print_summary(summarize(transactions), args.pdf)


if __name__ == "__main__":
    main()
