"""
server.py — NetAI Agent API Server
"""
import uvicorn
import sys
import os
import asyncio
import socket
import datetime
import secrets

import requests
from dotenv import load_dotenv
import csv
import io
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List

# ── Path setup ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# ── Internal modules ───────────────────────────────────────────────────────────
from src.db   import get_conn, init_all_tables, seed_default_user, seed_demo_devices, log_diagnostic
from src.auth import (create_access_token, authenticate_user, change_user_password,
                      get_current_user, require_admin, require_operator, hash_password)
from src.agent.graph import run_agent
from src.supabase_sync import (sync_device_upsert, sync_device_delete,
                                sync_all_from_sqlite)

PUBLIC_DIR = os.path.join(PROJECT_ROOT, "public")
ENV_FILE   = os.path.join(PROJECT_ROOT, ".env")

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="NetAI Agent API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════════════════
class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class QueryRequest(BaseModel):
    query: str
    preferred_model: Optional[str] = None
    simulation: bool = False

class ApplyFixRequest(BaseModel):
    device_ip: str
    commands: List[str]
    simulation: bool = False

class DeviceCreate(BaseModel):
    name: str
    ip: str
    type: str = "router"
    location: str = ""
    ssh_user: str = ""
    ssh_pass: str = ""
    enable_pass: str = ""

class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None
    type: Optional[str] = None
    location: Optional[str] = None
    ssh_user: Optional[str] = None
    ssh_pass: Optional[str] = None
    enable_pass: Optional[str] = None

class SettingsUpdate(BaseModel):
    telegramToken: str
    telegramChatId: str

class AISettingsUpdate(BaseModel):
    googleApiKey: str
    groqApiKey: str
    openrouterApiKey: str


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def mask_key(k: str) -> str:
    if not k: return ""
    if len(k) < 8: return "*" * len(k)
    return k[:4] + "*" * (len(k) - 8) + k[-4:]


def send_telegram_alert(message: str) -> bool:
    import dotenv
    dotenv.load_dotenv(ENV_FILE, override=True)
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("⚠️  Telegram not configured — skipping alert")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=5
        )
        return r.ok
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


def _tcp_ping(ip: str, port: int = 22, timeout: float = 3.0) -> str:
    """Blocking TCP connect to check reachability. Returns 'up'/'down'."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        sock.close()
        return "up"
    except (socket.timeout, ConnectionRefusedError):
        return "warning"
    except OSError:
        return "down"


# ══════════════════════════════════════════════════════════════════════════════
# STARTUP — init DB, seed data, start background monitor
# ══════════════════════════════════════════════════════════════════════════════
async def device_monitor_loop():
    print("🕵️  Device status monitor started (30s interval).")
    while True:
        try:
            conn = get_conn()
            devices = conn.execute("SELECT id, ip FROM devices").fetchall()
            conn.close()

            async def check_one(dev_id, ip):
                loop = asyncio.get_event_loop()
                st = await asyncio.wait_for(
                    loop.run_in_executor(None, _tcp_ping, ip), timeout=5
                )
                c = get_conn()
                c.execute(
                    "UPDATE devices SET status=?, last_seen=? WHERE id=?",
                    (st, datetime.datetime.now().isoformat(), dev_id)
                )
                c.commit()
                c.close()

            await asyncio.gather(*[check_one(d["id"], d["ip"]) for d in devices],
                                 return_exceptions=True)
        except Exception as e:
            print(f"Monitor error: {e}")
        await asyncio.sleep(30)


@app.on_event("startup")
async def startup_event():
    init_all_tables()
    seed_default_user()
    seed_demo_devices()
    asyncio.create_task(device_monitor_loop())
    # Push local SQLite data → Supabase on startup
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, sync_all_from_sqlite)
    print("🚀 NetAI API Server ready.")


# ══════════════════════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/auth/login")
def login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Sai tên đăng nhập hoặc mật khẩu")
    token = create_access_token(user["username"], user["id"], user["role"])
    return {"access_token": token, "token_type": "bearer",
            "username": user["username"], "role": user["role"]}


@app.get("/api/auth/me")
def me(current_user: dict = Depends(get_current_user)):
    return {"username": current_user["sub"],
            "role":     current_user["role"],
            "user_id":  current_user["user_id"]}


@app.post("/api/auth/change-password")
def change_password(req: ChangePasswordRequest,
                    current_user: dict = Depends(get_current_user)):
    user = authenticate_user(current_user["sub"], req.current_password)
    if not user:
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")
    change_user_password(current_user["sub"], req.new_password)
    return {"status": "success", "message": "Đã đổi mật khẩu thành công"}


# ══════════════════════════════════════════════════════════════════════════════
# DEVICE CRUD  (SQLite-based, no Supabase dependency)
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/devices")
def get_devices():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, ip, type, location, ssh_user, status, last_seen, created_at FROM devices ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/devices/status")
def get_device_status():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, ip, status, last_seen FROM devices ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/devices")
def create_device(req: DeviceCreate,
                  _: dict = Depends(require_admin)):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO devices (name, ip, type, location, ssh_user, ssh_pass, enable_pass) VALUES (?,?,?,?,?,?,?)",
            (req.name, req.ip, req.type, req.location, req.ssh_user, req.ssh_pass, req.enable_pass)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM devices WHERE ip=?", (req.ip,)).fetchone()
        conn.close()
        device = dict(row)
        sync_device_upsert(device)
        return {"status": "success", "device": device}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/devices/{device_id}")
def update_device(device_id: int, req: DeviceUpdate,
                  _: dict = Depends(require_admin)):
    conn = get_conn()
    existing = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Device not found")

    fields = {k: v for k, v in req.dict().items() if v is not None}
    if not fields:
        conn.close()
        return {"status": "no_change"}

    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [device_id]
    conn.execute(f"UPDATE devices SET {sets} WHERE id=?", vals)
    conn.commit()
    row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    conn.close()
    device = dict(row)
    sync_device_upsert(device)
    return {"status": "success", "device": device}


@app.delete("/api/devices/{device_id}")
def delete_device(device_id: int,
                  _: dict = Depends(require_admin)):
    conn = get_conn()
    row = conn.execute("SELECT ip FROM devices WHERE id=?", (device_id,)).fetchone()
    conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
    conn.commit()
    conn.close()
    if row:
        sync_device_delete(row["ip"])
    return {"status": "success"}


# ══════════════════════════════════════════════════════════════════════════════
# HISTORY & STATS
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/history")
def get_history():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM diagnostics_log ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/stats")
def get_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM diagnostics_log").fetchone()[0]
    issues = conn.execute(
        "SELECT COUNT(*) FROM diagnostics_log WHERE severity IN ('critical','error','warning')"
    ).fetchone()[0]
    conn.close()
    return {
        "queries":  total,
        "commands": total * 3,
        "issues":   issues,
        "fixes":    int(issues * 0.8),
    }


@app.get("/api/stats/trend")
def get_trend():
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            DATE(created_at) as date,
            COUNT(CASE WHEN severity IN ('critical','error','warning') THEN 1 END) as issues,
            COUNT(*) as total
        FROM diagnostics_log
        WHERE created_at >= DATE('now', '-7 days')
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    """).fetchall()
    conn.close()
    result = [{"date": r["date"], "issues": r["issues"],
               "fixes": int(r["issues"] * 0.8)} for r in rows]
    return result


# ══════════════════════════════════════════════════════════════════════════════
# AI ANALYZE & APPLY FIX
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/analyze")
def analyze_network(req: QueryRequest, _: dict = Depends(require_operator)):
    try:
        print(f"📡 Analyze: {req.query[:80]} | model={req.preferred_model} sim={req.simulation}")
        state = run_agent(req.query, preferred_model=req.preferred_model, simulation=req.simulation)

        severity   = state.get("status_severity", "unknown").lower()
        device_ips = state.get("device_ips", [])
        root_cause = state.get("root_cause_analysis", "Không rõ nguyên nhân")

        # Telegram alert on issues
        if severity in ["critical", "error", "warning"]:
            send_telegram_alert(
                f"🚨 *NetAI Alert: {severity.upper()}*\n\n"
                f"📍 *Devices:* {', '.join(device_ips)}\n"
                f"🔍 *Issue:* {root_cause}\n"
                f"💬 *Query:* {req.query}"
            )

        # Persist log
        log_diagnostic(req.query, str(device_ips), severity, root_cause,
                       state.get("intent_summary", ""))

        return {
            "intent_summary":  state.get("intent_summary", ""),
            "device_ips":      device_ips,
            "commands":        state.get("required_commands", []),
            "ssh_output":      state.get("ssh_raw_output", {}),
            "status_severity": severity,
            "root_cause":      root_cause,
            "fixes":           state.get("suggested_fix_commands", []),
            "agent_logs":      state.get("agent_logs", []),
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        return {"error": str(e), "status": "failed"}


@app.post("/api/apply-fix")
def apply_fix(req: ApplyFixRequest):
    from src.tools.ssh_netmiko import SSHTool
    result = SSHTool.apply_config(req.device_ip, req.commands, simulation=req.simulation)
    return {
        "status":     "success" if "Error" not in result else "error",
        "output":     result,
        "agent_logs": [f"🛠️ Applied {len(req.commands)} commands to {req.device_ip}."],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS — AI Keys & Telegram
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/settings/ai")
def get_ai_settings():
    import dotenv; dotenv.load_dotenv(ENV_FILE, override=True)
    return {
        "googleApiKey":     mask_key(os.getenv("GOOGLE_API_KEY", "")),
        "groqApiKey":       mask_key(os.getenv("GROQ_API_KEY", "")),
        "openrouterApiKey": mask_key(os.getenv("OPENROUTER_API_KEY", "")),
    }


@app.post("/api/settings/ai")
def update_ai_settings(req: AISettingsUpdate,
                        _: dict = Depends(require_admin)):
    import dotenv
    if req.googleApiKey     and "*" not in req.googleApiKey:
        dotenv.set_key(ENV_FILE, "GOOGLE_API_KEY",      req.googleApiKey)
    if req.groqApiKey       and "*" not in req.groqApiKey:
        dotenv.set_key(ENV_FILE, "GROQ_API_KEY",        req.groqApiKey)
    if req.openrouterApiKey and "*" not in req.openrouterApiKey:
        dotenv.set_key(ENV_FILE, "OPENROUTER_API_KEY",  req.openrouterApiKey)
    dotenv.load_dotenv(ENV_FILE, override=True)
    return {"status": "success"}


@app.get("/api/settings/channels")
def get_channels():
    import dotenv; dotenv.load_dotenv(ENV_FILE, override=True)
    return {"telegram": {"token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
                         "chatId": os.getenv("TELEGRAM_CHAT_ID", "")}}


@app.post("/api/settings/channels")
def update_channels(req: SettingsUpdate,
                    _: dict = Depends(require_admin)):
    import dotenv
    dotenv.set_key(ENV_FILE, "TELEGRAM_BOT_TOKEN", req.telegramToken)
    dotenv.set_key(ENV_FILE, "TELEGRAM_CHAT_ID",   req.telegramChatId)
    dotenv.load_dotenv(ENV_FILE, override=True)
    return {"status": "success"}


@app.post("/api/settings/channels/test")
def test_telegram(_: dict = Depends(require_admin)):
    result = send_telegram_alert("✅ NetAI test message — kết nối Telegram thành công!")
    return {"status": "success" if result else "error"}


# ══════════════════════════════════════════════════════════════════════════════
# USER MANAGEMENT (admin only)
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/users")
def list_users(_: dict = Depends(require_admin)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, username, role, created_at FROM users ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/users")
def create_user(req: CreateUserRequest, _: dict = Depends(require_admin)):
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu tối thiểu 6 ký tự")
    if req.role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="Role không hợp lệ")
    conn = get_conn()
    existing = conn.execute("SELECT id FROM users WHERE username=?", (req.username,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=409, detail="Tên đăng nhập đã tồn tại")
    pwd_hash = hash_password(req.password)
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
        (req.username, pwd_hash, req.role)
    )
    conn.commit()
    row = conn.execute("SELECT id, username, role, created_at FROM users WHERE username=?",
                       (req.username,)).fetchone()
    conn.close()
    return {"status": "success", "user": dict(row)}


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, current: dict = Depends(require_admin)):
    if current["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="Không thể xóa tài khoản đang đăng nhập")
    conn = get_conn()
    row = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}


@app.put("/api/users/{user_id}/role")
def update_user_role(user_id: int, body: dict, current: dict = Depends(require_admin)):
    role = body.get("role", "")
    if role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="Role không hợp lệ")
    conn = get_conn()
    conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    conn.commit()
    conn.close()
    return {"status": "success"}


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT CSV
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/export/history.csv")
def export_history_csv(_: dict = Depends(get_current_user)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, query, device_ip, severity, root_cause, intent, created_at "
        "FROM diagnostics_log ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Câu hỏi", "IP thiết bị", "Mức độ", "Nguyên nhân", "Intent", "Thời gian"])
    for r in rows:
        writer.writerow([r["id"], r["query"], r["device_ip"], r["severity"],
                         r["root_cause"], r["intent"], r["created_at"]])
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lich_su_chan_doan.csv"}
    )


@app.get("/api/export/devices.csv")
def export_devices_csv(_: dict = Depends(get_current_user)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, ip, type, location, status, last_seen, created_at FROM devices ORDER BY id ASC"
    ).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Tên thiết bị", "IP", "Loại", "Vị trí", "Trạng thái", "Lần cuối online", "Ngày thêm"])
    for r in rows:
        writer.writerow([r["id"], r["name"], r["ip"], r["type"],
                         r["location"], r["status"], r["last_seen"], r["created_at"]])
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=danh_sach_thiet_bi.csv"}
    )


# ══════════════════════════════════════════════════════════════════════════════
# STATIC FILES
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/")
def read_root():
    index_path = os.path.join(PUBLIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "index.html not found"}

if os.path.exists(PUBLIC_DIR):
    app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="static")


if __name__ == "__main__":
    uvicorn.run("src.server:app", host="0.0.0.0", port=8000, reload=False)
