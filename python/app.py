"""The owner's page (part 2). Standard library only, no install needed.

Run from inside python/:

    python app.py

Environment variables:
    PORT      port to listen on, default 8000
    DATA_DIR  folder with invoices.json and sent.json, default ../data
    TODAY     date as YYYY-MM-DD, default the real date
"""

from datetime import date
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import urllib.parse

from plan import build_plan, parse_date, read_json

PORT = int(os.environ.get("PORT", "8000"))
DATA_DIR = os.environ.get("DATA_DIR", "../data")
TODAY = os.environ.get("TODAY") or date.today().isoformat()

# In-memory store for owner decisions: {invoice_id: "approved" | "rejected"}
DECISIONS = {}

HUMAN_REASONS = {
    "duplicate_id": "Duplicate invoice ID found in data",
    "invalid_amount": "Amount is missing, non-numeric, or non-positive",
    "missing_due_date": "Due date is missing or empty",
    "invalid_due_date": "Due date is not a valid calendar date (YYYY-MM-DD)",
    "invalid_paid_date": "Paid date is malformed or set in the future",
}


def get_plan_data():
    """Load data and build today's plan, returning (plan, invoice_lookup, error)."""
    invoices_path = os.path.join(DATA_DIR, "invoices.json")
    sent_path = os.path.join(DATA_DIR, "sent.json")

    if not os.path.exists(invoices_path):
        return None, {}, f"Invoices file not found at '{invoices_path}'."
    if not os.path.exists(sent_path):
        return None, {}, f"Sent reminders file not found at '{sent_path}'."

    try:
        invoices = read_json(invoices_path)
    except Exception as e:
        return None, {}, f"Could not parse invoices JSON from '{invoices_path}': {e}"

    try:
        sent = read_json(sent_path)
    except Exception as e:
        return None, {}, f"Could not parse sent JSON from '{sent_path}': {e}"

    try:
        plan = build_plan(invoices, sent, TODAY)
    except Exception as e:
        return None, {}, f"Error building plan: {e}"

    lookup = {}
    if isinstance(invoices, list):
        for inv in invoices:
            if isinstance(inv, dict) and "id" in inv and inv["id"] is not None:
                lookup[str(inv["id"])] = inv

    return plan, lookup, None


def render_html():
    plan, invoice_lookup, error = get_plan_data()

    html_parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
        "  <title>Payment Reminder Assistant</title>",
        "  <style>",
        "    :root {",
        "      --bg: #f8fafc; --card: #ffffff; --text: #0f172a; --muted: #64748b; --border: #e2e8f0;",
        "      --primary: #2563eb; --primary-hover: #1d4ed8;",
        "      --success: #16a34a; --success-bg: #dcfce7; --danger: #dc2626; --danger-bg: #fee2e2;",
        "      --warning: #d97706; --warning-bg: #fef3c7; --info: #0284c7; --info-bg: #e0f2fe;",
        "    }",
        "    * { box-sizing: border-box; margin: 0; padding: 0; }",
        "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;",
        "           background: var(--bg); color: var(--text); line-height: 1.5; padding: 1.5rem 1rem; }",
        "    .container { max-width: 900px; margin: 0 auto; }",
        "    header { margin-bottom: 2rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem; }",
        "    h1 { font-size: 1.75rem; font-weight: 700; color: #0f172a; }",
        "    .meta { font-size: 0.875rem; color: var(--muted); margin-top: 0.25rem; }",
        "    .card { background: var(--card); border: 1px solid var(--border); border-radius: 0.75rem;",
        "            padding: 1.25rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }",
        "    .card-title { font-size: 1.25rem; font-weight: 600; margin-bottom: 1rem; }",
        "    .alert { padding: 1rem; border-radius: 0.5rem; margin-bottom: 1.5rem; font-weight: 500; }",
        "    .alert-error { background: var(--danger-bg); color: var(--danger); border: 1px solid #fca5a5; }",
        "    .badge { display: inline-block; padding: 0.25rem 0.625rem; border-radius: 9999px;",
        "             font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }",
        "    .badge-friendly { background: var(--info-bg); color: var(--info); }",
        "    .badge-firm { background: var(--warning-bg); color: var(--warning); }",
        "    .badge-final { background: var(--danger-bg); color: var(--danger); }",
        "    .badge-approved { background: var(--success-bg); color: var(--success); }",
        "    .badge-rejected { background: var(--danger-bg); color: var(--danger); }",
        "    .badge-pending { background: #f1f5f9; color: #475569; }",
        "    .action-item { border: 1px solid var(--border); border-radius: 0.5rem; padding: 1rem;",
        "                   margin-bottom: 1rem; background: #fafafa; }",
        "    .action-header { display: flex; flex-wrap: wrap; justify-content: space-between;",
        "                     align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }",
        "    .action-customer { font-size: 1.1rem; font-weight: 600; }",
        "    .action-details { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));",
        "                      gap: 0.5rem; font-size: 0.875rem; margin-bottom: 0.75rem; }",
        "    .detail-label { color: var(--muted); display: block; font-size: 0.75rem; }",
        "    .detail-val { font-weight: 600; }",
        "    .message-box { background: #f1f5f9; padding: 0.75rem; border-radius: 0.375rem;",
        "                   font-family: monospace; font-size: 0.8125rem; white-space: pre-wrap;",
        "                   border: 1px solid #cbd5e1; margin-bottom: 0.75rem; color: #1e293b; }",
        "    .controls { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }",
        "    .btn { padding: 0.375rem 0.75rem; border-radius: 0.375rem; font-size: 0.875rem;",
        "           font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; }",
        "    .btn:focus { outline: 2px solid var(--primary); outline-offset: 2px; }",
        "    .btn-approve { background: var(--success); color: #fff; }",
        "    .btn-approve:hover { background: #15803d; }",
        "    .btn-reject { background: #ef4444; color: #fff; }",
        "    .btn-reject:hover { background: #b91c1c; }",
        "    .empty-state { text-align: center; padding: 2rem 1rem; color: var(--muted); }",
        "    .skipped-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }",
        "    .skipped-table th, .skipped-table td { padding: 0.625rem 0.75rem; text-align: left;",
        "                                           border-bottom: 1px solid var(--border); }",
        "    .skipped-table th { background: #f8fafc; color: var(--muted); font-size: 0.75rem;",
        "                        text-transform: uppercase; font-weight: 600; }",
        "    @media (max-width: 480px) {",
        "      body { padding: 1rem 0.5rem; }",
        "      .action-header { flex-direction: column; align-items: flex-start; }",
        "    }",
        "  </style>",
        "</head>",
        "<body>",
        '  <main class="container">',
        "    <header>",
        "      <h1>Payment Reminder Assistant</h1>",
        f'      <p class="meta">Date: <strong>{escape(TODAY)}</strong> | Data folder: <code>{escape(DATA_DIR)}</code></p>',
        "    </header>",
    ]

    if error:
        html_parts.append(
            f'    <div class="alert alert-error" role="alert"><strong>Data Error:</strong> {escape(error)}</div>'
        )
    else:
        actions = plan.get("actions", [])
        skipped = plan.get("skipped", [])

        # 1. Today's Actions Section
        html_parts.append('    <section class="card" aria-labelledby="actions-heading">')
        html_parts.append(f'      <h2 id="actions-heading" class="card-title">Today\'s Reminders ({len(actions)})</h2>')

        if not actions:
            html_parts.append(
                '      <div class="empty-state">'
                "        <p>🎉 All caught up! No payment reminders need to be sent today.</p>"
                "      </div>"
            )
        else:
            for act in actions:
                inv_id = str(act.get("invoice_id", ""))
                step = str(act.get("step", "friendly"))
                needs_approval = act.get("needs_approval", False)
                days_overdue = act.get("days_overdue", 0)
                msg = act.get("message", "")

                inv_data = invoice_lookup.get(inv_id, {})
                customer = inv_data.get("customer", "Customer")
                amount = inv_data.get("amount", 0.0)
                currency = inv_data.get("currency", "")
                amount_str = f"{currency} {amount:.2f}"

                current_decision = DECISIONS.get(inv_id)

                html_parts.append('      <article class="action-item">')
                html_parts.append('        <div class="action-header">')
                html_parts.append(f'          <span class="action-customer">{escape(customer)}</span>')
                html_parts.append("          <div>")
                html_parts.append(f'            <span class="badge badge-{escape(step)}">{escape(step)}</span>')

                if needs_approval:
                    if current_decision == "approved":
                        html_parts.append('            <span class="badge badge-approved">Approved</span>')
                    elif current_decision == "rejected":
                        html_parts.append('            <span class="badge badge-rejected">Rejected</span>')
                    else:
                        html_parts.append('            <span class="badge badge-pending">Needs Approval</span>')
                else:
                    html_parts.append('            <span class="badge badge-approved">Auto-Approved</span>')

                html_parts.append("          </div>")
                html_parts.append("        </div>")

                html_parts.append('        <div class="action-details">')
                html_parts.append(f'          <div><span class="detail-label">Invoice ID</span><span class="detail-val">{escape(inv_id)}</span></div>')
                html_parts.append(f'          <div><span class="detail-label">Amount</span><span class="detail-val">{escape(amount_str)}</span></div>')
                html_parts.append(f'          <div><span class="detail-label">Overdue</span><span class="detail-val">{escape(str(days_overdue))} days</span></div>')
                html_parts.append("        </div>")

                html_parts.append(f'        <details><summary style="cursor: pointer; font-size: 0.8125rem; color: var(--primary); margin-bottom: 0.5rem;">Preview message draft</summary><pre class="message-box">{escape(msg)}</pre></details>')

                if needs_approval:
                    html_parts.append('        <form method="POST" action="/decision" class="controls">')
                    html_parts.append(f'          <input type="hidden" name="invoice_id" value="{escape(inv_id)}">')
                    html_parts.append('          <button type="submit" name="decision" value="approved" class="btn btn-approve" aria-label="Approve reminder">Approve</button>')
                    html_parts.append('          <button type="submit" name="decision" value="rejected" class="btn btn-reject" aria-label="Reject reminder">Reject</button>')
                    if current_decision:
                        html_parts.append(f'          <span style="font-size: 0.8125rem; color: var(--muted); margin-left: 0.5rem;">Current status: <strong>{escape(current_decision.capitalize())}</strong></span>')
                    html_parts.append("        </form>")

                html_parts.append("      </article>")

        html_parts.append("    </section>")

        # 2. Skipped Invoices Section
        html_parts.append('    <section class="card" aria-labelledby="skipped-heading">')
        html_parts.append(f'      <h2 id="skipped-heading" class="card-title">Skipped Invoices ({len(skipped)})</h2>')

        if not skipped:
            html_parts.append('      <p style="color: var(--muted); font-size: 0.875rem;">No invoices were skipped due to invalid data.</p>')
        else:
            html_parts.append('      <table class="skipped-table" role="table">')
            html_parts.append('        <thead><tr><th scope="col">Invoice ID</th><th scope="col">Reason</th></tr></thead>')
            html_parts.append("        <tbody>")
            for item in skipped:
                s_id = str(item.get("invoice_id", ""))
                code = item.get("reason", "")
                human_text = HUMAN_REASONS.get(code, code)
                html_parts.append(f'          <tr><td><code>{escape(s_id)}</code></td><td>{escape(human_text)}</td></tr>')
            html_parts.append("        </tbody>")
            html_parts.append("      </table>")

        html_parts.append("    </section>")

    html_parts.append("  </main>")
    html_parts.append("</body>")
    html_parts.append("</html>")
    return "\n".join(html_parts)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/" and not self.path.startswith("/?"):
            self.send_error(404, "Page not found")
            return

        body = render_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/decision":
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length).decode("utf-8")
            params = urllib.parse.parse_qs(post_body)

            invoice_id = params.get("invoice_id", [""])[0]
            decision = params.get("decision", [""])[0]

            if invoice_id and decision in ("approved", "rejected"):
                DECISIONS[invoice_id] = decision

            # Redirect back to homepage
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return

        self.send_error(404, "Not found")


def main():
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"Serving Payment Reminder Dashboard on http://localhost:{PORT}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
