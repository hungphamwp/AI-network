"""
supabase_sync.py — Background sync helper: SQLite (primary) → Supabase (cloud)

All functions are fire-and-forget; errors are logged but never raised so that
the local SQLite path remains unaffected.
"""
import os
import traceback
from typing import Optional

_client = None
_init_tried = False


def get_supabase():
    """Return a Supabase client (cached), or None if credentials are missing / import fails."""
    global _client, _init_tried
    if _init_tried:
        return _client
    _init_tried = True
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        print("⚠️  Supabase credentials not set — cloud sync disabled.")
        return None
    try:
        from supabase import create_client
        _client = create_client(url, key)
        print("✅ Supabase client initialized.")
    except Exception as e:
        print(f"⚠️  Supabase init failed: {e}")
    return _client


# ── Column mapping: SQLite → Supabase ─────────────────────────────────────────
# Supabase devices schema uses different column names than SQLite.
# SQLite:   ssh_user, ssh_pass, enable_pass, last_seen
# Supabase: username,  password,  (no col),   last_checked

def _sqlite_device_to_supabase(d: dict) -> dict:
    """Map SQLite device dict to Supabase column names, dropping unknown fields."""
    supabase_cols = {"id", "name", "ip", "type", "location",
                     "status", "last_checked", "created_at", "username", "password"}
    row = {
        "name":         d.get("name"),
        "ip":           d.get("ip"),
        "type":         d.get("type"),
        "location":     d.get("location"),
        "status":       d.get("status"),
        "last_checked": d.get("last_seen"),   # SQLite: last_seen → Supabase: last_checked
        "created_at":   d.get("created_at"),
        "username":     d.get("ssh_user"),    # SQLite: ssh_user → Supabase: username
        "password":     d.get("ssh_pass"),    # SQLite: ssh_pass → Supabase: password
        # enable_pass has no Supabase column — omitted
    }
    # Remove None-value keys to avoid overwriting existing Supabase data with None
    return {k: v for k, v in row.items() if v is not None}


# ── Device sync ────────────────────────────────────────────────────────────────

def sync_device_upsert(device: dict):
    """Upsert a device row to Supabase (match on `ip`)."""
    sb = get_supabase()
    if not sb:
        return
    try:
        row = _sqlite_device_to_supabase(device)
        sb.table("devices").upsert(row, on_conflict="ip").execute()
    except Exception:
        print(f"⚠️  Supabase device upsert failed:\n{traceback.format_exc()}")


def sync_device_delete(ip: str):
    """Delete a device from Supabase by IP."""
    sb = get_supabase()
    if not sb:
        return
    try:
        sb.table("devices").delete().eq("ip", ip).execute()
    except Exception:
        print(f"⚠️  Supabase device delete failed:\n{traceback.format_exc()}")


# ── Diagnostics sync ───────────────────────────────────────────────────────────

def sync_diagnostic_insert(entry: dict):
    """Insert a diagnostics_log row to Supabase (strip local id — Supabase auto-generates)."""
    sb = get_supabase()
    if not sb:
        return
    try:
        # Supabase id is GENERATED ALWAYS — must not be sent
        row = {k: v for k, v in entry.items() if k != "id"}
        sb.table("diagnostics_log").insert(row).execute()
    except Exception:
        print(f"⚠️  Supabase diagnostic insert failed:\n{traceback.format_exc()}")


# ── Bulk startup sync ──────────────────────────────────────────────────────────

def sync_all_from_sqlite():
    """
    On startup, push every SQLite row to Supabase.
    Runs synchronously (called from the startup event before serving requests).
    """
    sb = get_supabase()
    if not sb:
        return

    try:
        from src.db import get_conn
        conn = get_conn()

        # --- devices ---
        devices = [dict(r) for r in conn.execute("SELECT * FROM devices").fetchall()]
        if devices:
            rows = [_sqlite_device_to_supabase(d) for d in devices]
            sb.table("devices").upsert(rows, on_conflict="ip").execute()
            print(f"✅ Supabase: synced {len(rows)} devices.")

        # --- diagnostics_log ---
        logs = [dict(r) for r in conn.execute("SELECT * FROM diagnostics_log").fetchall()]
        if logs:
            # Strip local SQLite id — Supabase uses GENERATED ALWAYS identity
            rows_no_id = [{k: v for k, v in r.items() if k != "id"} for r in logs]
            # Clear existing rows first to avoid duplicates on repeated startup
            sb.table("diagnostics_log").delete().neq("id", 0).execute()
            sb.table("diagnostics_log").insert(rows_no_id).execute()
            print(f"✅ Supabase: synced {len(rows_no_id)} diagnostics log rows.")

        conn.close()
    except Exception:
        print(f"⚠️  Supabase bulk sync failed:\n{traceback.format_exc()}")
