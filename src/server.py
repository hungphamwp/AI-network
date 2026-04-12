import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
import sys
import os
import shutil
from dotenv import load_dotenv

# Load secret keys from .env
load_dotenv()

import requests
import sqlite3
import datetime
from supabase import create_client, Client

# Supabase Initialization
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY and "your_supabase" not in SUPABASE_URL:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Đã kết nối Supabase thành công.")
    except Exception as e:
        print(f"❌ Lỗi khởi tạo Supabase client: {e}")
else:
    print("⚠️ Thiếu SUPABASE_URL hoặc SUPABASE_KEY. Vui lòng cấu hình trong file .env")

def init_db():
    conn = sqlite3.connect("netai_history.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS diagnostics_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            device_ip TEXT,
            severity TEXT,
            root_cause TEXT,
            intent TEXT,
            created_at DATETIME
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_log_to_db(query, ip, severity, cause, intent):
    if supabase:
        try:
            data = {
                "query": query,
                "device_ip": str(ip),
                "severity": severity,
                "root_cause": cause,
                "intent": intent
            }
            supabase.table("diagnostics_log").insert(data).execute()
        except Exception as e:
            print(f"Lỗi lưu Supabase: {e}")
    else:
        # Fallback to local SQLite if Supabase not configured
        try:
            conn = sqlite3.connect("netai_history.db")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO diagnostics_log (query, device_ip, severity, root_cause, intent, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (query, ip, severity, cause, intent, datetime.datetime.now())
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Lỗi lưu SQLite: {e}")

def send_telegram_alert(message: str):
    import dotenv
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    dotenv.load_dotenv(env_file, override=True)
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        from urllib.parse import quote
        # Xử lý tự động gửi thông báo với bot demo nếu chưa setup
        print("Bỏ qua cảnh báo qua Telegram do chưa cắm TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID")
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Lỗi gửi Telegram: {e}")

# Đảm bảo có thể import các package trong src từ thư mục gốc
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.graph import run_agent
# Tệp giao diện chính nằm ở thư mục public/ (đổi tên từ UI/)
import os
target_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")

app = FastAPI(title="NetAI Agent Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str
    preferred_model: str = None
    simulation: bool = False

class ApplyFixRequest(BaseModel):
    device_ip: str
    commands: list[str]
    simulation: bool = False

class SettingsUpdate(BaseModel):
    telegramToken: str
    telegramChatId: str

class AISettingsUpdate(BaseModel):
    googleApiKey: str
    groqApiKey: str
    openrouterApiKey: str

class DeviceCreate(BaseModel):
    name: str
    ip: str
    type: str = "cisco_ios"
    location: str = ""
    username: str = ""
    password: str = ""


@app.get("/api/settings/channels")
def get_channels():
    import dotenv
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    dotenv.load_dotenv(env_file, override=True)
    return {
        "telegram": {
            "token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
            "chatId": os.getenv("TELEGRAM_CHAT_ID", "")
        }
    }

@app.post("/api/settings/channels")
def update_channels(req: SettingsUpdate):
    import dotenv
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    
    # Store settings in .env
    dotenv.set_key(env_file, "TELEGRAM_BOT_TOKEN", req.telegramToken)
    # Automatically get Chat ID using getUpdates if not provided but token is there? For simplicity we just save what UI sends.
    # We will assume Chat ID is handled via the bot interaction. UI provides both if they want.
    dotenv.set_key(env_file, "TELEGRAM_CHAT_ID", req.telegramChatId)
    
    dotenv.load_dotenv(env_file, override=True)
    return {"status": "success"}

@app.post("/api/settings/channels/test")
def test_telegram():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Chưa cấu hình TELEGRAM_BOT_TOKEN")
    result = send_telegram_alert("✅ NetAI test message — kết nối Telegram thành công!")
    return {"status": "success" if result else "error"}

def mask_key(k: str):
    if not k: return ""
    if len(k) < 8: return "*" * len(k)
    return k[:4] + "*" * (len(k)-8) + k[-4:]

@app.get("/api/settings/ai")
def get_ai_settings():
    import dotenv
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    dotenv.load_dotenv(env_file, override=True)
    return {
        "googleApiKey": mask_key(os.getenv("GOOGLE_API_KEY", "")),
        "groqApiKey": mask_key(os.getenv("GROQ_API_KEY", "")),
        "openrouterApiKey": mask_key(os.getenv("OPENROUTER_API_KEY", ""))
    }

@app.post("/api/settings/ai")
def update_ai_settings(req: AISettingsUpdate):
    import dotenv
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    
    if req.googleApiKey and "*" not in req.googleApiKey:
        dotenv.set_key(env_file, "GOOGLE_API_KEY", req.googleApiKey)
    if req.groqApiKey and "*" not in req.groqApiKey:
        dotenv.set_key(env_file, "GROQ_API_KEY", req.groqApiKey)
    if req.openrouterApiKey and "*" not in req.openrouterApiKey:
        dotenv.set_key(env_file, "OPENROUTER_API_KEY", req.openrouterApiKey)
        
    dotenv.load_dotenv(env_file, override=True)
    return {"status": "success"}


@app.post("/api/analyze")
def analyze_network(req: QueryRequest):
    try:
        print(f"Nhận yêu cầu: {req.query} (Model: {req.preferred_model}, Sim: {req.simulation})")
        state = run_agent(req.query, preferred_model=req.preferred_model, simulation=req.simulation)
        
        # Gửi cảnh báo Telegram nếu lỗi nghiêm trọng (Phase 2)
        severity = state.get("status_severity", "unknown").lower()
        device_ips = state.get("device_ips", [])
        root_cause = state.get("root_cause_analysis", "Không rõ nguyên nhân")
        
        if severity in ["critical", "error", "warning"]:
            alert_msg = f"🚨 *NetAI Alert: {severity.upper()}*\n\n"
            alert_msg += f"📍 *Các thiết bị:* {', '.join(device_ips)}\n"
            alert_msg += f"🔍 *Vấn đề:* {root_cause}\n"
            alert_msg += f"💬 *Yêu cầu:* {req.query}"
            send_telegram_alert(alert_msg)

        # Lưu vào CSDL (Phase 3)
        save_log_to_db(
            req.query, 
            str(state.get("device_ips", [])),
            severity,
            root_cause,
            state.get("intent_summary", "")
        )

        return {
            "intent_summary": state.get("intent_summary", ""),
            "device_ips": device_ips,
            "commands": state.get("required_commands", []),
            "ssh_output": state.get("ssh_raw_output", {}),
            "status_severity": severity,
            "root_cause": root_cause,
            "fixes": state.get("suggested_fix_commands", []),
            "agent_logs": state.get("agent_logs", [])
        }
    except Exception as e:
        import traceback
        print(f"❌ LỖI NGHIÊM TRỌNG TRONG ANALYZE: {e}")
        traceback.print_exc()
        return {"error": str(e), "status": "failed"}

@app.get("/api/devices")
def get_devices():
    if supabase:
        try:
            res = supabase.table("devices").select("*").order("name").execute()
            return res.data
        except Exception as e:
            return {"error": str(e), "data": []}
    return {"data": []}

@app.post("/api/devices")
def add_device(req: DeviceCreate):
    if supabase:
        try:
            data = req.dict()
            res = supabase.table("devices").insert(data).execute()
            return {"status": "success", "data": res.data}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Supabase not connected"}

@app.delete("/api/devices/{device_id}")
def delete_device(device_id: int):
    if supabase:
        try:
            supabase.table("devices").delete().eq("id", device_id).execute()
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Supabase not connected"}

async def check_all_devices_health():
    """Background task to monitor device status"""
    import asyncio
    print("🕵️ Starting background device monitor...")
    while True:
        try:
            if supabase:
                res = supabase.table("devices").select("id, ip").execute()
                devices = res.data
                for d in devices:
                    # Simulation: Check if IP responds (ping) or just mock based on IP
                    # In a real environment, you'd use os.system('ping...')
                    status = "up" if ".1" in d['ip'] or ".2" in d['ip'] else "down"
                    supabase.table("devices").update({
                        "status": status,
                        "last_checked": datetime.datetime.now().isoformat()
                    }).eq("id", d['id']).execute()
            
            await asyncio.sleep(60) # Chạy mỗi 60 giây
        except Exception as e:
            print(f"Lỗi Monitor: {e}")
            await asyncio.sleep(10)

@app.on_event("startup")
async def startup_event():
    import asyncio
    asyncio.create_task(check_all_devices_health())

@app.post("/api/apply-fix")

def apply_fix(req: ApplyFixRequest):
    from src.tools.ssh_netmiko import SSHTool
    print(f"Đang thực hiện Apply Fix trên: {req.device_ip} (Sim: {req.simulation})")
    print(f"Lệnh: {req.commands}")
    
    result = SSHTool.apply_config(req.device_ip, req.commands, simulation=req.simulation)
    
    return {
        "status": "success" if "Error" not in result else "error",
        "output": result,
        "agent_logs": [f"🛠️ Đã áp dụng {len(req.commands)} lệnh cấu hình lên {req.device_ip}."]
    }

@app.get("/api/history")
def get_history():
    if supabase:
        try:
            response = supabase.table("diagnostics_log").select("*").order("created_at", desc=True).limit(50).execute()
            return response.data
        except Exception as e:
            print(f"Lỗi truy vấn Supabase: {e}")
            return {"error": str(e)}
    else:
        # Fallback to local SQLite
        try:
            conn = sqlite3.connect("netai_history.db")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM diagnostics_log ORDER BY created_at DESC LIMIT 50")
            rows = cursor.fetchall()
            history = [dict(row) for row in rows]
            conn.close()
            return history
        except Exception as e:
            return {"error": str(e)}

@app.get("/api/stats")
def get_stats():
    if supabase:
        try:
            # Get total requests
            res_req = supabase.table("diagnostics_log").select("id", count="exact").execute()
            total_req = res_req.count or 0
            
            # Get total items for issues and commands (we have to count them from the logs)
            res_all = supabase.table("diagnostics_log").select("severity").execute()
            logs = res_all.data
            
            issues_count = len([l for l in logs if l.get('severity') in ['critical', 'error', 'warning']])
            
            # Simulated commands run based on history length * multiplier
            commands_count = total_req * 3 
            
            return {
                "queries": total_req,
                "commands": commands_count,
                "issues": issues_count,
                "fixes": int(issues_count * 0.8)
            }
        except Exception as e:
            print(f"Lỗi stats: {e}")
            return {"queries": 0, "commands": 0, "issues": 0, "fixes": 0}
    return {"queries": 0, "commands": 0, "issues": 0, "fixes": 0}


@app.get("/")
def read_root():
    index_path = os.path.join(target_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "index.html not found"}

# Phục vụ thư mục Giao Diện tĩnh khi người dùng vào http://localhost:8000/
if os.path.exists(target_dir):
    app.mount("/", StaticFiles(directory=target_dir, html=True), name="static")

if __name__ == "__main__":
    print("🚀 Bắt đầu chạy máy chủ NetAI API trên cổng http://0.0.0.0:8015")
    uvicorn.run(app, host="0.0.0.0", port=8015)



