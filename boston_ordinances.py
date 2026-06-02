#!/usr/bin/env python3
"""
Boston City Council Ordinance Monitor
Checks the Legistar API for new/updated ordinances and sends a Gmail summary.
"""

import json
import os
import smtplib
import urllib.request
import urllib.parse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Config ────────────────────────────────────────────────────────────────────
GMAIL_USER     = "emma@thinkjet.io"
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "")   # Set as GitHub secret
TO_ADDRESSES   = ["emma@thinkjet.io", "jefferson@thinkjet.io", "brianna@thinkjet.io", "ayah@thinkjet.io"]

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
STATE_FILE  = os.path.join(SCRIPT_DIR, "boston_ordinances_state.json")

LEGISTAR_BASE = "https://webapi.legistar.com/v1/boston"

SELECT_FIELDS = (
    "MatterId,MatterFile,MatterTitle,MatterStatusName,"
    "MatterIntroDate,MatterAgendaDate,MatterPassedDate,MatterBodyName"
)
# ─────────────────────────────────────────────────────────────────────────────


def fetch_ordinances():
    params = urllib.parse.urlencode({
        "$filter": "MatterTypeName eq 'Council Ordinance'",
        "$orderby": "MatterLastModifiedUtc desc",
        "$top": "100",
        "$select": SELECT_FIELDS,
    })
    url = f"{LEGISTAR_BASE}/matters?{params}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_sponsors(matter_id):
    url = f"{LEGISTAR_BASE}/matters/{matter_id}/sponsors"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            sponsors = json.loads(resp.read().decode())
            return [s.get("MatterSponsorName", "") for s in sponsors]
    except Exception:
        return []


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"seen_ids": [], "seen_agenda_dates": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def fmt_date(iso):
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso.split("T")[0]).strftime("%B %d, %Y")
    except Exception:
        return iso


def build_email(new_items, updated_items):
    today = datetime.now().strftime("%B %d, %Y")
    lines = [f"<h2>Boston City Council — Ordinance Update ({today})</h2>"]

    if new_items:
        lines.append("<h3>🆕 Newly Filed Ordinances</h3><ul>")
        for item in new_items:
            sponsors_str = ", ".join(item["sponsors"]) if item["sponsors"] else "Unknown"
            hearing = fmt_date(item.get("MatterAgendaDate"))
            lines.append(
                f"<li><b>{item['MatterFile']}</b> — {item['MatterTitle']}<br>"
                f"Sponsored by: {sponsors_str}<br>"
                f"Hearing date: {hearing} | Status: {item['MatterStatusName']}<br>"
                f"To look up: go to <a href='https://boston.legistar.com'>boston.legistar.com</a>, click Search Agenda Items, and search for <b>{item['MatterFile']}</b></li>"
            )
        lines.append("</ul>")

    if updated_items:
        lines.append("<h3>📅 Hearing Date Announced / Status Changed</h3><ul>")
        for item in updated_items:
            sponsors_str = ", ".join(item["sponsors"]) if item["sponsors"] else "Unknown"
            hearing = fmt_date(item.get("MatterAgendaDate"))
            lines.append(
                f"<li><b>{item['MatterFile']}</b> — {item['MatterTitle']}<br>"
                f"Sponsored by: {sponsors_str}<br>"
                f"Hearing date: {hearing} | Status: {item['MatterStatusName']}<br>"
                f"To look up: go to <a href='https://boston.legistar.com'>boston.legistar.com</a>, click Search Agenda Items, and search for <b>{item['MatterFile']}</b></li>"
            )
        lines.append("</ul>")

    lines.append("<p><small>Source: <a href='https://boston.legistar.com'>boston.legistar.com</a></small></p>")
    return "\n".join(lines)


def send_email(subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(TO_ADDRESSES)
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, TO_ADDRESSES, msg.as_string())

    print(f"Email sent to {TO_ADDRESSES}")


def main():
    if not GMAIL_APP_PASS:
        raise ValueError("GMAIL_APP_PASS environment variable is not set.")

    state = load_state()
    seen_ids = set(state.get("seen_ids", []))
    seen_agenda = state.get("seen_agenda_dates", {})

    ordinances = fetch_ordinances()

    new_items     = []
    updated_items = []

    for item in ordinances:
        mid = str(item["MatterId"])

        if mid not in seen_ids:
            item["sponsors"] = fetch_sponsors(item["MatterId"])
            new_items.append(item)
            seen_ids.add(mid)
            seen_agenda[mid] = item.get("MatterAgendaDate")
        else:
            prev_agenda = seen_agenda.get(mid)
            curr_agenda = item.get("MatterAgendaDate")
            if curr_agenda and curr_agenda != prev_agenda:
                item["sponsors"] = fetch_sponsors(item["MatterId"])
                updated_items.append(item)
                seen_agenda[mid] = curr_agenda

    print(f"New: {len(new_items)}, Updated: {len(updated_items)}")

    if new_items or updated_items:
        total = len(new_items) + len(updated_items)
        subject = f"Boston City Council: {total} ordinance update{'s' if total != 1 else ''}"
        html = build_email(new_items, updated_items)
        send_email(subject, html)
    else:
        print("No new ordinances or updates — no email sent.")

    save_state({"seen_ids": list(seen_ids), "seen_agenda_dates": seen_agenda})


if __name__ == "__main__":
    main()
