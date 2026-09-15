#!/usr/bin/env python3
"""
Remote Employee Equipment Allocation Tracker
A minimalist, zero-dependency Python application for HR, Finance, and IT Operations.
Workflow: Employees request setups -> IT reviews inventory -> IT issues tracking -> HR/IT logs return agreements.
"""

import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DB_FILE = os.path.join(os.path.dirname(__file__), "equipment_tracker.db")

# ---------------------------------------------------------------------------
# Database & Model Layer
# ---------------------------------------------------------------------------

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db(seed=False):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_tag TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                model_name TEXT NOT NULL,
                serial_number TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'Available', -- Available, Allocated, Maintenance, Retired
                cost_center TEXT NOT NULL DEFAULT 'IT-OPS',
                asset_value REAL NOT NULL DEFAULT 0.0,
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_name TEXT NOT NULL,
                employee_email TEXT NOT NULL,
                department TEXT NOT NULL,
                role_title TEXT NOT NULL,
                shipping_address TEXT NOT NULL,
                setup_tier TEXT NOT NULL, -- Engineering, Design, General, Custom
                requested_items TEXT NOT NULL,
                assigned_asset_tags TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Pending Review', -- Pending Review, Approved, Shipped, Delivered, Returned, Rejected
                carrier TEXT DEFAULT '',
                tracking_number TEXT DEFAULT '',
                dispatch_date TEXT DEFAULT '',
                return_agreement_signed INTEGER NOT NULL DEFAULT 0, -- 0 or 1
                return_agreement_date TEXT DEFAULT '',
                return_due_date TEXT DEFAULT '',
                return_notes TEXT DEFAULT '',
                admin_notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

        # Only seed demo/mock data if explicitly requested
        if seed:
            cursor.execute("SELECT COUNT(*) as count FROM inventory")
            if cursor.fetchone()["count"] == 0:
                seed_initial_data(cursor)
                conn.commit()

def seed_initial_data(cursor):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    inventory_items = [
        ("AST-0101", "Laptop", "Apple MacBook Pro 16\" (M3 Pro / 36GB / 512GB)", "SN-MBP-9011", "Allocated", "ENG-DEV", 2499.00),
        ("AST-0102", "Laptop", "Lenovo ThinkPad X1 Carbon Gen 11", "SN-LNV-4322", "Available", "OPS-GEN", 1850.00),
        ("AST-0103", "Laptop", "Apple MacBook Air 15\" (M3 / 16GB / 512GB)", "SN-MBA-6784", "Available", "MKT-REM", 1499.00),
        ("AST-0104", "Laptop", "Dell XPS 15 9530 (i9 / 32GB / 1TB)", "SN-DEL-1120", "Available", "FIN-ANL", 2150.00),
        ("AST-0201", "Monitor", "Dell UltraSharp 27\" 4K USB-C (U2723QE)", "SN-MON-3341", "Allocated", "ENG-DEV", 580.00),
        ("AST-0202", "Monitor", "LG 34\" UltraWide Curved IPS", "SN-MON-8812", "Available", "DES-PROD", 699.00),
        ("AST-0203", "Monitor", "Dell UltraSharp 27\" 4K USB-C (U2723QE)", "SN-MON-3345", "Available", "ENG-DEV", 580.00),
        ("AST-0301", "Docking Station", "CalDigit TS4 Thunderbolt 4 Dock", "SN-DCK-5541", "Allocated", "ENG-DEV", 399.00),
        ("AST-0302", "Docking Station", "Dell WD19TBS Thunderbolt Dock", "SN-DCK-2211", "Available", "OPS-GEN", 280.00),
        ("AST-0401", "Peripherals", "Logitech MX Master 3S + MX Mechanical Bundle", "SN-PER-1044", "Allocated", "ENG-DEV", 220.00),
        ("AST-0402", "Peripherals", "Apple Magic Keyboard with Touch ID + Magic Trackpad", "SN-PER-2099", "Available", "DES-PROD", 299.00)
    ]
    for item in inventory_items:
        cursor.execute("""
            INSERT INTO inventory (asset_tag, category, model_name, serial_number, status, cost_center, asset_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (*item, now))

    # Sample requests representing different workflow stages
    requests_seed = [
        (
            "Elena Rostova", "elena.r@company.io", "Engineering", "Senior Backend Architect",
            "742 Evergreen Terrace, Apt 4B, Austin, TX 78701", "Engineering",
            "MacBook Pro 16\", Dell UltraSharp 27\" 4K, CalDigit TS4 Dock, Logitech MX Bundle",
            "AST-0101, AST-0201, AST-0301, AST-0401", "Delivered",
            "FedEx", "FX-9982410291", "2026-09-02", 1, "2026-09-01", "", "",
            "Equipment verified in active deployment. Compliance agreement logged.",
            "2026-09-01 10:15"
        ),
        (
            "Marcus Vance", "marcus.v@company.io", "Design", "Staff UI/UX Designer",
            "1208 Pine Crest Drive, Seattle, WA 98101", "Design",
            "MacBook Air 15\", LG 34\" UltraWide, Magic Keyboard & Trackpad",
            "", "Pending Review",
            "", "", "", 1, "2026-09-14", "", "",
            "Pending IT inventory stock allocation.",
            "2026-09-14 14:30"
        ),
        (
            "Sarah Jenkins", "sarah.j@company.io", "Finance", "Senior Financial Analyst",
            "502 Commonwealth Ave, Boston, MA 02215", "General",
            "ThinkPad X1 Carbon Gen 11, Dell WD19TBS Dock",
            "AST-0102, AST-0302", "Shipped",
            "UPS Express", "1Z9999999999999999", "2026-09-13", 1, "2026-09-12", "", "",
            "Hardware kit in transit. Expected delivery in 48 hours.",
            "2026-09-12 09:00"
        )
    ]
    for req in requests_seed:
        cursor.execute("""
            INSERT INTO requests (
                employee_name, employee_email, department, role_title, shipping_address,
                setup_tier, requested_items, assigned_asset_tags, status, carrier,
                tracking_number, dispatch_date, return_agreement_signed, return_agreement_date,
                return_due_date, return_notes, admin_notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, req)

# ---------------------------------------------------------------------------
# Business Logic & API Handlers
# ---------------------------------------------------------------------------

def get_stats():
    with get_db() as conn:
        c = conn.cursor()
        total_inv = c.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
        avail_inv = c.execute("SELECT COUNT(*) FROM inventory WHERE status = 'Available'").fetchone()[0]
        alloc_inv = c.execute("SELECT COUNT(*) FROM inventory WHERE status = 'Allocated'").fetchone()[0]
        pending_req = c.execute("SELECT COUNT(*) FROM requests WHERE status = 'Pending Review'").fetchone()[0]
        in_transit = c.execute("SELECT COUNT(*) FROM requests WHERE status = 'Shipped'").fetchone()[0]
        active_alloc = c.execute("SELECT COUNT(*) FROM requests WHERE status = 'Delivered'").fetchone()[0]
        total_value = c.execute("SELECT COALESCE(SUM(asset_value), 0) FROM inventory WHERE status = 'Allocated'").fetchone()[0]
        return {
            "total_inventory": total_inv,
            "available_inventory": avail_inv,
            "allocated_inventory": alloc_inv,
            "pending_requests": pending_req,
            "in_transit": in_transit,
            "active_allocations": active_alloc,
            "allocated_value": round(total_value, 2)
        }

def list_inventory(status_filter=None):
    with get_db() as conn:
        c = conn.cursor()
        if status_filter:
            c.execute("SELECT * FROM inventory WHERE status = ? ORDER BY category, asset_tag", (status_filter,))
        else:
            c.execute("SELECT * FROM inventory ORDER BY category, asset_tag")
        return [dict(row) for row in c.fetchall()]

def add_inventory_item(data):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO inventory (asset_tag, category, model_name, serial_number, status, cost_center, asset_value, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["asset_tag"].strip().upper(),
            data["category"].strip(),
            data["model_name"].strip(),
            data["serial_number"].strip().upper(),
            data.get("status", "Available"),
            data.get("cost_center", "IT-OPS").strip().upper(),
            float(data.get("asset_value", 0.0)),
            now
        ))
        conn.commit()
        return c.lastrowid

def list_requests(status_filter=None):
    with get_db() as conn:
        c = conn.cursor()
        if status_filter:
            c.execute("SELECT * FROM requests WHERE status = ? ORDER BY id DESC", (status_filter,))
        else:
            c.execute("SELECT * FROM requests ORDER BY id DESC")
        return [dict(row) for row in c.fetchall()]

def create_request(data):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    signed_date = now if data.get("return_agreement_signed") else ""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO requests (
                employee_name, employee_email, department, role_title, shipping_address,
                setup_tier, requested_items, status, return_agreement_signed, return_agreement_date, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending Review', ?, ?, ?)
        """, (
            data["employee_name"].strip(),
            data["employee_email"].strip(),
            data["department"].strip(),
            data.get("role_title", "Remote Specialist").strip(),
            data["shipping_address"].strip(),
            data.get("setup_tier", "Standard").strip(),
            data["requested_items"].strip(),
            1 if data.get("return_agreement_signed") else 0,
            signed_date,
            now
        ))
        conn.commit()
        return c.lastrowid

def review_request(req_id, action, assigned_tags=None, notes=""):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM requests WHERE id = ?", (req_id,))
        req = c.fetchone()
        if not req:
            return False, "Request not found"

        if action == "approve":
            tags_str = ", ".join(assigned_tags) if assigned_tags else ""
            c.execute("""
                UPDATE requests
                SET status = 'Approved', assigned_asset_tags = ?, admin_notes = ?
                WHERE id = ?
            """, (tags_str, notes, req_id))
            if assigned_tags:
                for tag in assigned_tags:
                    c.execute("UPDATE inventory SET status = 'Allocated' WHERE asset_tag = ?", (tag.strip(),))
            conn.commit()
            return True, "Request approved and inventory allocated"

        elif action == "reject":
            c.execute("""
                UPDATE requests
                SET status = 'Rejected', admin_notes = ?
                WHERE id = ?
            """, (notes, req_id))
            conn.commit()
            return True, "Request rejected"

        return False, "Invalid review action"

def update_tracking(req_id, carrier, tracking_number, status="Shipped"):
    now_date = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM requests WHERE id = ?", (req_id,))
        req = c.fetchone()
        if not req:
            return False, "Request not found"

        c.execute("""
            UPDATE requests
            SET carrier = ?, tracking_number = ?, dispatch_date = ?, status = ?
            WHERE id = ?
        """, (carrier.strip(), tracking_number.strip(), now_date, status, req_id))
        conn.commit()
        return True, f"Logistics tracking updated ({status})"

def log_return(req_id, agreement_signed=True, return_status="Returned", notes=""):
    now_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM requests WHERE id = ?", (req_id,))
        req = c.fetchone()
        if not req:
            return False, "Request not found"

        # Update agreement signature and/or return completion
        assigned_tags = [t.strip() for t in req["assigned_asset_tags"].split(",") if t.strip()]

        if return_status == "Returned":
            # De-allocate hardware back to Available inventory
            for tag in assigned_tags:
                c.execute("UPDATE inventory SET status = 'Available' WHERE asset_tag = ?", (tag,))

        c.execute("""
            UPDATE requests
            SET return_agreement_signed = ?, return_agreement_date = COALESCE(NULLIF(return_agreement_date, ''), ?),
                status = ?, return_notes = ?
            WHERE id = ?
        """, (1 if agreement_signed else 0, now_date, return_status, notes, req_id))
        conn.commit()
        return True, f"Return agreement & lifecycle updated to {return_status}"

# ---------------------------------------------------------------------------
# Embedded Minimalist Web Interface
# ---------------------------------------------------------------------------

HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Equipment Allocation Tracker | HR & IT Ops</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #090a0f;
    --surface: #11131a;
    --surface-hover: #171a24;
    --border: #232738;
    --border-light: #2e344a;
    --text: #f1f3f9;
    --text-muted: #8b92ab;
    --primary: #4f78ff;
    --primary-glow: rgba(79, 120, 255, 0.15);
    --success: #10b981;
    --success-bg: rgba(16, 185, 129, 0.12);
    --warning: #f59e0b;
    --warning-bg: rgba(245, 158, 11, 0.12);
    --danger: #ef4444;
    --danger-bg: rgba(239, 68, 68, 0.12);
    --badge-gray: rgba(139, 146, 171, 0.15);
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
    padding-bottom: 60px;
  }

  header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 16px 32px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 100;
  }

  .brand {
    display: flex;
    align-items: flex-start;
    gap: 14px;
  }
  .brand-icon {
    width: 36px;
    height: 36px;
    border-radius: 9px;
    background: linear-gradient(135deg, #3b82f6, #6366f1);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 16px;
    color: #fff;
    box-shadow: 0 0 15px var(--primary-glow);
    flex-shrink: 0;
    margin-top: 2px;
  }
  .brand-title {
    font-size: 17px;
    font-weight: 700;
    letter-spacing: -0.01em;
    line-height: 1.2;
  }
  .brand-subtitle {
    font-size: 12px;
    color: var(--text-muted);
    font-weight: 500;
    margin-top: 2px;
  }

  /* Toggle button under header title */
  .sidebar-toggle-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-top: 8px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
    font-family: inherit;
  }
  .sidebar-toggle-btn:hover {
    color: var(--text);
    border-color: var(--border-light);
    background: var(--surface-hover);
  }

  /* App Layout with Left Sidebar */
  .app-layout {
    display: flex;
    min-height: calc(100vh - 85px);
    position: relative;
    overflow-x: hidden;
  }

  .sidebar {
    width: 250px;
    min-width: 250px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    padding: 24px 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    transition: margin-left 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.2s ease;
    flex-shrink: 0;
  }

  .sidebar.collapsed {
    margin-left: -250px;
    opacity: 0;
    pointer-events: none;
  }

  .sidebar-header {
    padding: 0 10px 4px 10px;
  }
  .sidebar-section-title {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
  }

  .sidebar-nav {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .sidebar-nav .tab-btn {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    text-align: left;
    background: transparent;
    border: 1px solid transparent;
    color: var(--text-muted);
    font-size: 13px;
    font-weight: 600;
    padding: 10px 14px;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .sidebar-nav .tab-btn:hover {
    color: var(--text);
    background: var(--surface-hover);
  }

  .sidebar-nav .tab-btn.active {
    background: rgba(79, 120, 255, 0.12);
    color: #fff;
    border-color: rgba(79, 120, 255, 0.35);
    box-shadow: 0 2px 8px var(--primary-glow);
  }

  .sidebar-nav .tab-btn.active svg {
    stroke: var(--primary);
  }

  .main-content {
    flex: 1;
    min-width: 0;
    padding: 28px 32px 60px 32px;
    max-width: 1400px;
  }

  /* Stats Bar */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
  }
  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 20px;
    transition: border-color 0.15s ease;
  }
  .stat-card:hover {
    border-color: var(--border-light);
  }
  .stat-label {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 6px;
  }
  .stat-val {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #fff;
  }

  /* Toolbar */
  .section-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 18px;
    flex-wrap: wrap;
    gap: 12px;
  }
  .section-title {
    font-size: 19px;
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    border: 1px solid transparent;
    transition: all 0.15s ease;
  }
  .btn-primary {
    background: var(--primary);
    color: #fff;
    box-shadow: 0 2px 10px var(--primary-glow);
  }
  .btn-primary:hover {
    background: #3d67f5;
  }
  .btn-outline {
    background: transparent;
    border-color: var(--border-light);
    color: var(--text);
  }
  .btn-outline:hover {
    background: var(--surface-hover);
    border-color: #3e4663;
  }
  .btn-sm {
    padding: 5px 10px;
    font-size: 12px;
    border-radius: 6px;
  }

  /* Table styling */
  .table-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  th {
    background: rgba(255,255,255,0.02);
    text-align: left;
    padding: 12px 18px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    border-bottom: 1px solid var(--border);
  }
  td {
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
    vertical-align: middle;
  }
  tr:last-child td {
    border-bottom: none;
  }
  tr:hover td {
    background: rgba(255, 255, 255, 0.015);
  }

  /* Badges */
  .badge {
    display: inline-flex;
    align-items: center;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
  }
  .badge-pending { background: var(--warning-bg); color: var(--warning); }
  .badge-approved { background: rgba(59, 130, 246, 0.12); color: #60a5fa; }
  .badge-shipped { background: rgba(168, 85, 247, 0.12); color: #c084fc; }
  .badge-delivered { background: var(--success-bg); color: var(--success); }
  .badge-returned { background: var(--badge-gray); color: var(--text-muted); }
  .badge-rejected { background: var(--danger-bg); color: var(--danger); }
  .badge-available { background: var(--success-bg); color: var(--success); }
  .badge-allocated { background: rgba(79, 120, 255, 0.15); color: #818cf8; }

  .mono {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
  }

  /* Modal */
  .modal-overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(4, 5, 8, 0.75);
    backdrop-filter: blur(4px);
    z-index: 200;
    align-items: center;
    justify-content: center;
  }
  .modal-overlay.active {
    display: flex;
  }
  .modal-box {
    background: var(--surface);
    border: 1px solid var(--border-light);
    border-radius: 14px;
    width: 90%;
    max-width: 580px;
    max-height: 90vh;
    overflow-y: auto;
    padding: 24px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.6);
  }
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }
  .modal-title {
    font-size: 17px;
    font-weight: 700;
  }
  .modal-close {
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 20px;
    cursor: pointer;
  }

  /* Form Elements */
  .form-group {
    margin-bottom: 16px;
  }
  label {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 6px;
  }
  input[type="text"], input[type="email"], input[type="number"], select, textarea {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
    color: var(--text);
    font-size: 13px;
    font-family: inherit;
    outline: none;
    transition: border-color 0.15s ease;
  }
  input:focus, select:focus, textarea:focus {
    border-color: var(--primary);
  }
  .checkbox-label {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    cursor: pointer;
    font-size: 13px;
    color: var(--text);
  }
  .checkbox-label input {
    margin-top: 3px;
  }
  .agreement-box {
    background: rgba(255,255,255,0.02);
    border: 1px solid var(--border);
    padding: 12px;
    border-radius: 8px;
    font-size: 12px;
    color: var(--text-muted);
    margin-bottom: 12px;
    line-height: 1.5;
  }

  /* Toast notification */
  #toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--surface);
    border: 1px solid var(--border-light);
    color: var(--text);
    padding: 12px 20px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    display: none;
    z-index: 999;
  }
</style>
</head>
<body>

<header>
  <div class="brand">
    <div class="brand-icon">&#9650;</div>
    <div>
      <div class="brand-title">Allocation & Compliance Tracker</div>
      <div class="brand-subtitle">Remote Employee Hardware Lifecycle & Return Agreements</div>
      <button id="sidebar-toggle" class="sidebar-toggle-btn" onclick="toggleSidebar()" title="Toggle Navigation Sidebar">
        <span id="toggle-icon">&#9776;</span>
        <span id="toggle-text">Hide Sidebar</span>
      </button>
    </div>
  </div>
  <div style="display:flex; align-items:center; gap:8px;">
    <span class="badge badge-delivered" style="font-size:11px; padding: 4px 10px;">Depot Active</span>
  </div>
</header>

<div class="app-layout">
  <aside id="sidebar" class="sidebar">
    <div class="sidebar-header">
      <span class="sidebar-section-title">Navigation</span>
    </div>
    <nav class="sidebar-nav">
      <button id="tab-btn-requests" class="tab-btn active" onclick="switchTab('requests')">
        <svg class="nav-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path><rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect></svg>
        <span>Allocation Requests</span>
      </button>
      <button id="tab-btn-inventory" class="tab-btn" onclick="switchTab('inventory')">
        <svg class="nav-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
        <span>IT Inventory</span>
      </button>
      <button id="tab-btn-request-form" class="tab-btn" onclick="switchTab('request-form')">
        <svg class="nav-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
        <span>+ Request Equipment</span>
      </button>
    </nav>
  </aside>

  <main class="main-content">
  <!-- Summary Metrics -->
  <div class="stats-grid" id="stats-container">
    <div class="stat-card">
      <div class="stat-label">Pending Requests</div>
      <div class="stat-val" id="stat-pending">-</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Active Deployments</div>
      <div class="stat-val" id="stat-active">-</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Hardware In Transit</div>
      <div class="stat-val" id="stat-transit">-</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Available Inventory</div>
      <div class="stat-val" id="stat-avail">-</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Allocated Capital</div>
      <div class="stat-val" id="stat-value">$0</div>
    </div>
  </div>

  <!-- TAB: ALLOCATION REQUESTS -->
  <div id="tab-requests" class="tab-content">
    <div class="section-toolbar">
      <div>
        <h2 class="section-title">Hardware Allocation Requests</h2>
        <p style="font-size:12px; color:var(--text-muted);">Manage requests, assign asset tags, update shipping tracking, and verify return agreements.</p>
      </div>
      <div style="display:flex; gap:8px;">
        <select id="filter-request-status" onchange="loadRequests()" style="width:auto; padding:6px 12px; font-size:12px;">
          <option value="">All Statuses</option>
          <option value="Pending Review">Pending Review</option>
          <option value="Approved">Approved</option>
          <option value="Shipped">Shipped</option>
          <option value="Delivered">Delivered</option>
          <option value="Returned">Returned</option>
          <option value="Rejected">Rejected</option>
        </select>
        <button class="btn btn-outline btn-sm" onclick="loadRequests()">&#8635; Refresh</button>
      </div>
    </div>

    <div class="table-card">
      <table>
        <thead>
          <tr>
            <th>Employee & Dept</th>
            <th>Tier & Setup</th>
            <th>Assigned Asset Tags</th>
            <th>Tracking & Logistics</th>
            <th>Compliance / Return</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="requests-tbody">
          <tr><td colspan="7" style="text-align:center; padding:30px; color:var(--text-muted);">Loading requests...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- TAB: INVENTORY -->
  <div id="tab-inventory" class="tab-content" style="display:none;">
    <div class="section-toolbar">
      <div>
        <h2 class="section-title">Hardware Inventory Depot</h2>
        <p style="font-size:12px; color:var(--text-muted);">Asset repository tagged for remote employee allocation.</p>
      </div>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-primary btn-sm" onclick="openAddInventoryModal()">+ Add Asset Item</button>
        <button class="btn btn-outline btn-sm" onclick="loadInventory()">&#8635; Refresh</button>
      </div>
    </div>

    <div class="table-card">
      <table>
        <thead>
          <tr>
            <th>Asset Tag</th>
            <th>Category</th>
            <th>Model & Hardware Specs</th>
            <th>Serial Number</th>
            <th>Cost Center</th>
            <th>Value (USD)</th>
            <th>Stock Status</th>
          </tr>
        </thead>
        <tbody id="inventory-tbody">
          <tr><td colspan="7" style="text-align:center; padding:30px; color:var(--text-muted);">Loading inventory...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- TAB: NEW REQUEST FORM -->
  <div id="tab-request-form" class="tab-content" style="display:none;">
    <div style="max-width: 680px; margin: 0 auto; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 32px;">
      <h2 class="section-title" style="margin-bottom:4px;">Remote Hardware Setup Request</h2>
      <p style="font-size:13px; color:var(--text-muted); margin-bottom: 24px;">Submit hardware allocation requirements for new hires or hardware upgrades.</p>

      <form id="new-request-form" onsubmit="submitHardwareRequest(event)">
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px;">
          <div class="form-group">
            <label>Full Employee Name *</label>
            <input type="text" id="req-name" required placeholder="e.g. Alex Morgan">
          </div>
          <div class="form-group">
            <label>Corporate Email *</label>
            <input type="email" id="req-email" required placeholder="alex.m@company.io">
          </div>
        </div>

        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px;">
          <div class="form-group">
            <label>Department *</label>
            <select id="req-dept" required>
              <option value="Engineering">Engineering</option>
              <option value="Product & Design">Product & Design</option>
              <option value="Finance & Accounting">Finance & Accounting</option>
              <option value="People & HR">People & HR</option>
              <option value="Marketing & Sales">Marketing & Sales</option>
              <option value="Operations & IT">Operations & IT</option>
            </select>
          </div>
          <div class="form-group">
            <label>Role / Position Title *</label>
            <input type="text" id="req-role" required placeholder="e.g. Staff Platform Engineer">
          </div>
        </div>

        <div class="form-group">
          <label>Hardware Package Tier *</label>
          <select id="req-tier" onchange="autoFillSetup(this.value)">
            <option value="Engineering">Engineering Setup (MacBook Pro 16\" / ThinkPad, 4K Display, TB4 Dock, Mech Keyboard)</option>
            <option value="Design">Product Design Setup (MacBook Air/Pro, UltraWide Display, Trackpad Bundle)</option>
            <option value="General">Standard Knowledge Worker (X1 Carbon / MBA, USB-C Dock, Dual Peripheral)</option>
            <option value="Custom">Custom / Specialized Equipment</option>
          </select>
        </div>

        <div class="form-group">
          <label>Requested Items & Specifications *</label>
          <textarea id="req-items" rows="3" required placeholder="Describe requested laptop, monitors, docks, and accessories..."></textarea>
        </div>

        <div class="form-group">
          <label>Direct Shipping Address (Remote Home Delivery) *</label>
          <textarea id="req-address" rows="2" required placeholder="Full street address, apartment/suite, city, state, postal code, country..."></textarea>
        </div>

        <div class="agreement-box">
          <strong>Corporate Equipment Return Agreement</strong><br>
          By submitting this request, the employee acknowledges that all allocated equipment remains company property. In the event of role change, upgrade, or employment cessation, the employee agrees to return all items within 14 business days via company-provided pre-paid courier packaging.
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input type="checkbox" id="req-agree" required>
            <span>I acknowledge and digitally sign the Remote Equipment Custody & Return Agreement.</span>
          </label>
        </div>

        <div style="margin-top:24px;">
          <button type="submit" class="btn btn-primary" style="width:100%; justify-content:center; padding:12px;">Submit Hardware Allocation Request</button>
        </div>
      </form>
    </div>
  </div>
</main>
</div>

<!-- MODAL: IT REVIEW & ASSET ALLOCATION -->
<div class="modal-overlay" id="review-modal">
  <div class="modal-box">
    <div class="modal-header">
      <div class="modal-title">Review & Allocate Hardware</div>
      <button class="modal-close" onclick="closeModal('review-modal')">&times;</button>
    </div>
    <form id="review-form" onsubmit="submitReview(event)">
      <input type="hidden" id="rev-id">
      <div style="margin-bottom:14px; font-size:13px;" id="rev-info"></div>

      <div class="form-group">
        <label>Select Available Inventory to Allocate (Hold Ctrl / Cmd to select multiple)</label>
        <select id="rev-assets" multiple style="height:140px; font-family:'JetBrains Mono', monospace; font-size:12px;">
        </select>
        <p style="font-size:11px; color:var(--text-muted); margin-top:4px;">Selected tags will be automatically marked as 'Allocated' upon approval.</p>
      </div>

      <div class="form-group">
        <label>Review Decision</label>
        <select id="rev-action" required>
          <option value="approve">Approve & Reserve Equipment</option>
          <option value="reject">Reject Request</option>
        </select>
      </div>

      <div class="form-group">
        <label>IT Operations / Inventory Notes</label>
        <textarea id="rev-notes" rows="2" placeholder="e.g. Verified stock, assigned tagged units from Austin Depot..."></textarea>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:20px;">
        <button type="button" class="btn btn-outline" onclick="closeModal('review-modal')">Cancel</button>
        <button type="submit" class="btn btn-primary">Confirm Allocation</button>
      </div>
    </form>
  </div>
</div>

<!-- MODAL: LOGISTICS & TRACKING UPDATE -->
<div class="modal-overlay" id="tracking-modal">
  <div class="modal-box">
    <div class="modal-header">
      <div class="modal-title">Logistics & Tracking Details</div>
      <button class="modal-close" onclick="closeModal('tracking-modal')">&times;</button>
    </div>
    <form id="tracking-form" onsubmit="submitTracking(event)">
      <input type="hidden" id="track-id">
      <div style="margin-bottom:14px; font-size:13px;" id="track-info"></div>

      <div class="form-group">
        <label>Shipping Carrier *</label>
        <select id="track-carrier" required>
          <option value="FedEx">FedEx Express</option>
          <option value="UPS">UPS Worldwide</option>
          <option value="DHL Express">DHL Express</option>
          <option value="USPS Priority">USPS Priority Mail</option>
          <option value="Local Courier">Direct / Local IT Courier</option>
        </select>
      </div>

      <div class="form-group">
        <label>Tracking Number / Consignment ID *</label>
        <input type="text" id="track-number" required placeholder="e.g. FX-9827361928">
      </div>

      <div class="form-group">
        <label>Shipment Status Update</label>
        <select id="track-status" required>
          <option value="Shipped">In Transit (Shipped to Remote Employee)</option>
          <option value="Delivered">Delivered & Received by Employee</option>
        </select>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:20px;">
        <button type="button" class="btn btn-outline" onclick="closeModal('tracking-modal')">Cancel</button>
        <button type="submit" class="btn btn-primary">Save Tracking</button>
      </div>
    </form>
  </div>
</div>

<!-- MODAL: RETURN AGREEMENT & OFFBOARDING -->
<div class="modal-overlay" id="return-modal">
  <div class="modal-box">
    <div class="modal-header">
      <div class="modal-title">Compliance & Return Agreement Log</div>
      <button class="modal-close" onclick="closeModal('return-modal')">&times;</button>
    </div>
    <form id="return-form" onsubmit="submitReturn(event)">
      <input type="hidden" id="ret-id">
      <div style="margin-bottom:14px; font-size:13px;" id="ret-info"></div>

      <div class="form-group">
        <label class="checkbox-label">
          <input type="checkbox" id="ret-agreement-signed">
          <span>Signed Employee Return Policy On File (HR Compliance)</span>
        </label>
      </div>

      <div class="form-group">
        <label>Allocation Lifecycle Status</label>
        <select id="ret-status" required>
          <option value="Delivered">Active Deployment (Equipment in use)</option>
          <option value="Returned">Returned to IT Stock (Employee Offboarded / Replaced)</option>
        </select>
        <p style="font-size:11px; color:var(--text-muted); margin-top:4px;">Setting status to 'Returned' will automatically restore assigned asset tags back to 'Available' stock.</p>
      </div>

      <div class="form-group">
        <label>Return Condition & Inspection Notes</label>
        <textarea id="ret-notes" rows="3" placeholder="Condition of returned gear, inspection results, restocking notes..."></textarea>
      </div>

      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:20px;">
        <button type="button" class="btn btn-outline" onclick="closeModal('return-modal')">Cancel</button>
        <button type="submit" class="btn btn-primary">Update Compliance Log</button>
      </div>
    </form>
  </div>
</div>

<!-- MODAL: ADD INVENTORY ASSET -->
<div class="modal-overlay" id="add-inv-modal">
  <div class="modal-box">
    <div class="modal-header">
      <div class="modal-title">Register New Hardware Asset</div>
      <button class="modal-close" onclick="closeModal('add-inv-modal')">&times;</button>
    </div>
    <form id="add-inv-form" onsubmit="submitAddInventory(event)">
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
        <div class="form-group">
          <label>Asset Tag ID *</label>
          <input type="text" id="inv-tag" required placeholder="e.g. AST-0501" class="mono">
        </div>
        <div class="form-group">
          <label>Category *</label>
          <select id="inv-cat" required>
            <option value="Laptop">Laptop / Workstation</option>
            <option value="Monitor">Monitor / Display</option>
            <option value="Docking Station">Docking Station</option>
            <option value="Peripherals">Peripherals / Accessories</option>
          </select>
        </div>
      </div>

      <div class="form-group">
        <label>Hardware Make & Model *</label>
        <input type="text" id="inv-model" required placeholder="e.g. Apple MacBook Pro 14\" M3 Max (36GB/1TB)">
      </div>

      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
        <div class="form-group">
          <label>Serial Number *</label>
          <input type="text" id="inv-sn" required placeholder="e.g. SN-MBP-90412" class="mono">
        </div>
        <div class="form-group">
          <label>Asset Capital Value ($ USD) *</label>
          <input type="number" id="inv-val" step="0.01" required placeholder="e.g. 2199.00">
        </div>
      </div>

      <div class="form-group">
        <label>Cost Center</label>
        <input type="text" id="inv-cc" value="IT-OPS" placeholder="e.g. ENG-DEV, FIN-OPS">
      </div>

      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:20px;">
        <button type="button" class="btn btn-outline" onclick="closeModal('add-inv-modal')">Cancel</button>
        <button type="submit" class="btn btn-primary">Add to Inventory</button>
      </div>
    </form>
  </div>
</div>

<div id="toast"></div>

<script>
  // State
  let cachedInventory = [];
  let cachedRequests = [];

  // Sidebar Toggle
  function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const toggleText = document.getElementById('toggle-text');
    const isCollapsed = sidebar.classList.toggle('collapsed');
    if (toggleText) {
      toggleText.textContent = isCollapsed ? 'Open Sidebar' : 'Hide Sidebar';
    }
  }

  // Tab Switching
  function switchTab(tabId) {
    document.querySelectorAll('.sidebar-nav .tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
    
    const btn = document.getElementById(`tab-btn-${tabId}`);
    if (btn) btn.classList.add('active');

    const content = document.getElementById(`tab-${tabId}`);
    if (content) content.style.display = 'block';

    if (tabId === 'requests') {
      loadRequests();
    } else if (tabId === 'inventory') {
      loadInventory();
    }
  }

  // Toast Notification
  function showToast(msg) {
    const t = document.getElementById('toast');
    t.innerText = msg;
    t.style.display = 'block';
    setTimeout(() => { t.style.display = 'none'; }, 3000);
  }

  // Load Dashboard Stats
  async function loadStats() {
    try {
      const res = await fetch('/api/stats');
      const data = await res.json();
      document.getElementById('stat-pending').innerText = data.pending_requests;
      document.getElementById('stat-active').innerText = data.active_allocations;
      document.getElementById('stat-transit').innerText = data.in_transit;
      document.getElementById('stat-avail').innerText = `${data.available_inventory} / ${data.total_inventory}`;
      document.getElementById('stat-value').innerText = `$${Number(data.allocated_value).toLocaleString()}`;
    } catch (e) {
      console.error('Failed to load stats', e);
    }
  }

  // Load Requests
  async function loadRequests() {
    const status = document.getElementById('filter-request-status').value;
    const url = status ? `/api/requests?status=${encodeURIComponent(status)}` : '/api/requests';
    try {
      const res = await fetch(url);
      cachedRequests = await res.json();
      renderRequestsTable(cachedRequests);
      loadStats();
    } catch (e) {
      console.error('Failed to load requests', e);
    }
  }

  function renderRequestsTable(list) {
    const tbody = document.getElementById('requests-tbody');
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:30px; color:var(--text-muted);">No hardware requests found.</td></tr>';
      return;
    }

    tbody.innerHTML = list.map(r => {
      const statusBadge = `<span class="badge badge-${r.status.toLowerCase().replace(' ', '')}">${r.status}</span>`;
      const tags = r.assigned_asset_tags 
        ? r.assigned_asset_tags.split(',').map(t => `<span class="badge badge-allocated" style="margin:2px;">${t.trim()}</span>`).join('') 
        : '<span style="color:var(--text-muted); font-size:12px;">Unassigned</span>';
      
      const tracking = r.tracking_number 
        ? `<div style="font-weight:600; font-size:12px;">${r.carrier}</div><div class="mono" style="font-size:11px; color:var(--text-muted);">${r.tracking_number}</div>`
        : '<span style="color:var(--text-muted); font-size:12px;">No tracking yet</span>';

      const agreement = r.return_agreement_signed 
        ? `<span class="badge badge-delivered">&#10003; Signed</span><div style="font-size:11px; color:var(--text-muted); margin-top:2px;">${r.return_agreement_date || 'On file'}</div>`
        : '<span class="badge badge-pending">Unsigned</span>';

      return `
        <tr>
          <td>
            <div style="font-weight:600;">${escapeHtml(r.employee_name)}</div>
            <div style="font-size:11px; color:var(--text-muted);">${escapeHtml(r.department)} &bull; ${escapeHtml(r.role_title)}</div>
            <div style="font-size:11px; color:var(--text-muted); margin-top:2px;">${escapeHtml(r.employee_email)}</div>
          </td>
          <td>
            <div style="font-weight:600; font-size:12px;">${escapeHtml(r.setup_tier)} Tier</div>
            <div style="font-size:11px; color:var(--text-muted); max-width:240px;">${escapeHtml(r.requested_items)}</div>
          </td>
          <td>${tags}</td>
          <td>${tracking}</td>
          <td>${agreement}</td>
          <td>${statusBadge}</td>
          <td>
            <div style="display:flex; flex-direction:column; gap:4px;">
              ${r.status === 'Pending Review' ? `<button class="btn btn-primary btn-sm" onclick="openReviewModal(${r.id})">Review & Allocate</button>` : ''}
              ${r.status === 'Approved' || r.status === 'Shipped' ? `<button class="btn btn-outline btn-sm" onclick="openTrackingModal(${r.id})">Update Tracking</button>` : ''}
              <button class="btn btn-outline btn-sm" onclick="openReturnModal(${r.id})">Compliance & Return</button>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  }

  // Load Inventory
  async function loadInventory() {
    try {
      const res = await fetch('/api/inventory');
      cachedInventory = await res.json();
      renderInventoryTable(cachedInventory);
      loadStats();
    } catch (e) {
      console.error('Failed to load inventory', e);
    }
  }

  function renderInventoryTable(list) {
    const tbody = document.getElementById('inventory-tbody');
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:30px; color:var(--text-muted);">No inventory found.</td></tr>';
      return;
    }

    tbody.innerHTML = list.map(item => `
      <tr>
        <td class="mono" style="font-weight:600;">${item.asset_tag}</td>
        <td><span class="badge badge-gray">${item.category}</span></td>
        <td><div style="font-weight:500;">${escapeHtml(item.model_name)}</div></td>
        <td class="mono" style="color:var(--text-muted);">${item.serial_number}</td>
        <td><span class="mono" style="font-size:11px;">${item.cost_center}</span></td>
        <td style="font-weight:600;">$${Number(item.asset_value).toFixed(2)}</td>
        <td><span class="badge badge-${item.status.toLowerCase()}">${item.status}</span></td>
      </tr>
    `).join('');
  }

  // Setup Tier Auto-Fill Helper
  function autoFillSetup(tier) {
    const itemsEl = document.getElementById('req-items');
    if (tier === 'Engineering') {
      itemsEl.value = 'Apple MacBook Pro 16" (M3 Pro / 36GB), Dell UltraSharp 27" 4K Monitor, CalDigit TS4 Thunderbolt Dock, Logitech MX Master 3S + Mechanical Keyboard';
    } else if (tier === 'Design') {
      itemsEl.value = 'Apple MacBook Pro 16", LG 34" UltraWide 5K Display, Apple Magic Trackpad & Keyboard, CalDigit Dock';
    } else if (tier === 'General') {
      itemsEl.value = 'Lenovo ThinkPad X1 Carbon Gen 11 (32GB RAM), Dell 27" USB-C Display, Ergonomic Peripherals';
    } else {
      itemsEl.value = '';
    }
  }

  // Submit Employee Request
  async function submitHardwareRequest(e) {
    e.preventDefault();
    const payload = {
      employee_name: document.getElementById('req-name').value,
      employee_email: document.getElementById('req-email').value,
      department: document.getElementById('req-dept').value,
      role_title: document.getElementById('req-role').value,
      setup_tier: document.getElementById('req-tier').value,
      requested_items: document.getElementById('req-items').value,
      shipping_address: document.getElementById('req-address').value,
      return_agreement_signed: document.getElementById('req-agree').checked ? 1 : 0
    };

    try {
      const res = await fetch('/api/requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        showToast('Request submitted successfully! IT has been notified.');
        document.getElementById('new-request-form').reset();
        switchTab('requests');
      } else {
        const err = await res.json();
        alert('Error: ' + (err.error || 'Failed to submit'));
      }
    } catch (err) {
      alert('Network error submitting request');
    }
  }

  // Review Modal Logic
  async function openReviewModal(reqId) {
    const req = cachedRequests.find(r => r.id === reqId);
    if (!req) return;

    document.getElementById('rev-id').value = req.id;
    document.getElementById('rev-info').innerHTML = `
      <strong>Request from:</strong> ${escapeHtml(req.employee_name)} (${escapeHtml(req.department)})<br>
      <strong>Requested Gear:</strong> ${escapeHtml(req.requested_items)}<br>
      <strong>Shipping Destination:</strong> ${escapeHtml(req.shipping_address)}
    `;

    // Fetch fresh available inventory
    const res = await fetch('/api/inventory?status=Available');
    const available = await res.json();
    const select = document.getElementById('rev-assets');
    select.innerHTML = available.length
      ? available.map(a => `<option value="${a.asset_tag}">[${a.asset_tag}] ${a.category}: ${a.model_name}</option>`).join('')
      : '<option disabled value="">No available inventory found. Register hardware first.</option>';

    document.getElementById('review-modal').classList.add('active');
  }

  async function submitReview(e) {
    e.preventDefault();
    const reqId = document.getElementById('rev-id').value;
    const action = document.getElementById('rev-action').value;
    const select = document.getElementById('rev-assets');
    const selectedTags = Array.from(select.selectedOptions).map(o => o.value);
    const notes = document.getElementById('rev-notes').value;

    const res = await fetch(`/api/requests/${reqId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, assigned_tags: selectedTags, notes })
    });
    if (res.ok) {
      closeModal('review-modal');
      showToast('Hardware allocation reviewed successfully');
      loadRequests();
    } else {
      const err = await res.json();
      alert('Review failed: ' + (err.error || 'Error'));
    }
  }

  // Tracking Modal Logic
  function openTrackingModal(reqId) {
    const req = cachedRequests.find(r => r.id === reqId);
    if (!req) return;

    document.getElementById('track-id').value = req.id;
    document.getElementById('track-info').innerHTML = `
      <strong>Employee:</strong> ${escapeHtml(req.employee_name)}<br>
      <strong>Assigned Assets:</strong> ${req.assigned_asset_tags || 'None'}<br>
      <strong>Destination:</strong> ${escapeHtml(req.shipping_address)}
    `;
    if (req.carrier) document.getElementById('track-carrier').value = req.carrier;
    document.getElementById('track-number').value = req.tracking_number || '';
    document.getElementById('track-status').value = req.status === 'Delivered' ? 'Delivered' : 'Shipped';

    document.getElementById('tracking-modal').classList.add('active');
  }

  async function submitTracking(e) {
    e.preventDefault();
    const reqId = document.getElementById('track-id').value;
    const carrier = document.getElementById('track-carrier').value;
    const tracking_number = document.getElementById('track-number').value;
    const status = document.getElementById('track-status').value;

    const res = await fetch(`/api/requests/${reqId}/tracking`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ carrier, tracking_number, status })
    });
    if (res.ok) {
      closeModal('tracking-modal');
      showToast('Courier tracking updated');
      loadRequests();
    }
  }

  // Return & Compliance Modal Logic
  function openReturnModal(reqId) {
    const req = cachedRequests.find(r => r.id === reqId);
    if (!req) return;

    document.getElementById('ret-id').value = req.id;
    document.getElementById('ret-info').innerHTML = `
      <strong>Employee:</strong> ${escapeHtml(req.employee_name)} &bull; ${escapeHtml(req.department)}<br>
      <strong>Allocated Tags:</strong> ${req.assigned_asset_tags || 'None'}<br>
      <strong>Agreement Date:</strong> ${req.return_agreement_date || 'Not signed'}
    `;
    document.getElementById('ret-agreement-signed').checked = !!req.return_agreement_signed;
    document.getElementById('ret-status').value = req.status === 'Returned' ? 'Returned' : req.status;
    document.getElementById('ret-notes').value = req.return_notes || '';

    document.getElementById('return-modal').classList.add('active');
  }

  async function submitReturn(e) {
    e.preventDefault();
    const reqId = document.getElementById('ret-id').value;
    const agreement_signed = document.getElementById('ret-agreement-signed').checked;
    const return_status = document.getElementById('ret-status').value;
    const notes = document.getElementById('ret-notes').value;

    const res = await fetch(`/api/requests/${reqId}/return`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agreement_signed, return_status, notes })
    });
    if (res.ok) {
      closeModal('return-modal');
      showToast('Return & compliance record updated');
      loadRequests();
    }
  }

  // Add Inventory Modal Logic
  function openAddInventoryModal() {
    document.getElementById('add-inv-form').reset();
    document.getElementById('add-inv-modal').classList.add('active');
  }

  async function submitAddInventory(e) {
    e.preventDefault();
    const payload = {
      asset_tag: document.getElementById('inv-tag').value,
      category: document.getElementById('inv-cat').value,
      model_name: document.getElementById('inv-model').value,
      serial_number: document.getElementById('inv-sn').value,
      asset_value: parseFloat(document.getElementById('inv-val').value) || 0,
      cost_center: document.getElementById('inv-cc').value
    };

    const res = await fetch('/api/inventory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      closeModal('add-inv-modal');
      showToast('New asset successfully added to inventory depot');
      loadInventory();
    } else {
      const err = await res.json();
      alert('Error adding asset: ' + (err.error || 'Duplicate tag or serial number'));
    }
  }

  function closeModal(id) {
    document.getElementById(id).classList.remove('active');
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Initial load
  autoFillSetup('Engineering');
  loadStats();
  loadRequests();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# HTTP Server Handler
# ---------------------------------------------------------------------------

class RequestHandler(BaseHTTPRequestHandler):
    def send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            html = HTML_UI.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if path == "/api/stats":
            self.send_json(get_stats())
            return

        if path == "/api/inventory":
            status_filter = params.get("status", [None])[0]
            self.send_json(list_inventory(status_filter))
            return

        if path == "/api/requests":
            status_filter = params.get("status", [None])[0]
            self.send_json(list_requests(status_filter))
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            body = self.read_json_body()

            if path == "/api/inventory":
                item_id = add_inventory_item(body)
                self.send_json({"success": True, "id": item_id}, status=HTTPStatus.CREATED)
                return

            if path == "/api/requests":
                req_id = create_request(body)
                self.send_json({"success": True, "id": req_id}, status=HTTPStatus.CREATED)
                return

            # Dynamic routes: /api/requests/<id>/<action>
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "requests":
                req_id = int(parts[2])
                action = parts[3]

                if action == "review":
                    success, msg = review_request(
                        req_id,
                        body.get("action"),
                        body.get("assigned_tags", []),
                        body.get("notes", "")
                    )
                    status = HTTPStatus.OK if success else HTTPStatus.BAD_REQUEST
                    self.send_json({"success": success, "message": msg}, status=status)
                    return

                if action == "tracking":
                    success, msg = update_tracking(
                        req_id,
                        body.get("carrier", "FedEx"),
                        body.get("tracking_number", ""),
                        body.get("status", "Shipped")
                    )
                    status = HTTPStatus.OK if success else HTTPStatus.BAD_REQUEST
                    self.send_json({"success": success, "message": msg}, status=status)
                    return

                if action == "return":
                    success, msg = log_return(
                        req_id,
                        body.get("agreement_signed", True),
                        body.get("return_status", "Returned"),
                        body.get("notes", "")
                    )
                    status = HTTPStatus.OK if success else HTTPStatus.BAD_REQUEST
                    self.send_json({"success": success, "message": msg}, status=status)
                    return

            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

        except sqlite3.IntegrityError as e:
            self.send_json({"success": False, "error": f"Database integrity error: {str(e)}"}, status=HTTPStatus.BAD_REQUEST)
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format, *args):
        # Clean minimalist logger
        sys.stdout.write(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]} {args[1]} -> {args[2]}\n")

def run(port=8080, seed=None):
    if seed is None:
        seed = "--seed" in sys.argv or os.environ.get("SEED_MOCK_DATA", "").lower() in ("1", "true", "yes")
    init_db(seed=seed)
    server = HTTPServer(("0.0.0.0", port), RequestHandler)
    print(f"[*] Equipment Allocation & Return Tracker active on http://localhost:{port}")
    if seed:
        print("[*] Demo mock data enabled.")
    print("[*] Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server shutdown gracefully.")
    finally:
        server.server_close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    run(port=port)
