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

class ApplyFixRequest(BaseModel):
    device_ip: str
    commands: list[str]

@app.post("/api/analyze")
def analyze_network(req: QueryRequest):
    print(f"Nhận yêu cầu: {req.query} (Model: {req.preferred_model})")
    state = run_agent(req.query, preferred_model=req.preferred_model)
    
    return {
        "intent_summary": state.get("intent_summary", ""),
        "device_ip": state.get("device_ip", "192.168.1.1"),
        "commands": state.get("required_commands", []),
        "ssh_output": state.get("ssh_raw_output", {}),
        "status_severity": state.get("status_severity", "unknown"),
        "root_cause": state.get("root_cause_analysis", ""),
        "fixes": state.get("suggested_fix_commands", []),
        "agent_logs": state.get("agent_logs", [])
    }

@app.post("/api/apply-fix")
def apply_fix(req: ApplyFixRequest):
    from src.tools.ssh_netmiko import SSHTool
    print(f"Đang thực hiện Apply Fix trên: {req.device_ip}")
    print(f"Lệnh: {req.commands}")
    
    result = SSHTool.apply_config(req.device_ip, req.commands)
    
    return {
        "status": "success" if "Error" not in result else "error",
        "output": result,
        "agent_logs": [f"🛠️ Đã áp dụng {len(req.commands)} lệnh cấu hình lên {req.device_ip}."]
    }


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
    print("🚀 Bắt đầu chạy máy chủ NetAI API trên cổng http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
