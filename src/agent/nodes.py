import json
import logging
from typing import Dict, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from src.agent.state import AgentState
from src.tools.ssh_netmiko import SSHTool

logger = logging.getLogger(__name__)

# --- Models cho Output Parser ---
class IntentOutput(BaseModel):
    device_ips: list[str] = Field(description="Danh sách các địa chỉ IP của thiết bị mạng cần kiểm tra. Nếu không thấy IP nào cụ thể, hãy trả về ['192.168.1.1'].", default=["192.168.1.1"])
    commands: list[str] = Field(description="Danh sách các lệnh Cisco show cần thiết để chẩn đoán lỗi (VD: ['show vlan brief', 'show logging'])")
    intent_summary: str = Field(description="Mô tả tóm tắt mục đích kiểm tra.")

class DiagnoseOutput(BaseModel):
    status_severity: str = Field(description="Mức độ nghiêm trọng của hệ thống: 'ok', 'warning', 'critical'")
    root_cause: str = Field(description="Phân tích nguyên nhân gốc rễ và đánh giá tình trạng thiết bị mạng")
    fix_commands: list[str] = Field(description="Các lệnh cấu hình mẫu để khắc phục sự cố (ví dụ conf t, int vlan ...). Trả về list rỗng nếu không có.")

# --- Nodes ---
import os
from dotenv import load_dotenv

load_dotenv() # Đảm bảo biến môi trường được nạp

def init_llm(model_full_name: str):
    """
    Khởi tạo LLM object dựa trên tiền tố.
    Hỗ trợ: gemini/, groq/, openrouter/
    """
    if model_full_name.startswith("gemini/"):
        model_name = model_full_name.replace("gemini/", "")
        return ChatGoogleGenerativeAI(temperature=0, model=model_name, google_api_key=os.getenv("GOOGLE_API_KEY"), max_retries=0, timeout=10)
    
    elif model_full_name.startswith("groq/"):
        model_name = model_full_name.replace("groq/", "")
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key: return None
        return ChatGroq(temperature=0, model_name=model_name, groq_api_key=api_key, max_retries=0, timeout=10)
    
    elif model_full_name.startswith("openrouter/"):
        model_name = model_full_name.replace("openrouter/", "")
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key: return None
        return ChatOpenAI(
            temperature=0,
            model_name=model_name,
            openai_api_key=api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            max_retries=0,
            timeout=10,
            default_headers={
                "HTTP-Referer": "https://github.com/google/antigravity", # Required by OpenRouter
                "X-Title": "NetAI Agent"
            }
        )
    
    # Backward compatibility
    return ChatGoogleGenerativeAI(temperature=0, model=model_full_name, google_api_key=os.getenv("GOOGLE_API_KEY"), max_retries=0, timeout=10)

def parse_intent(state: AgentState) -> dict:
    """
    Node 1: Phân tích ý định của người dùng và sinh lệnh show Cisco.
    """
    logger.info("Node: parse_intent")
    query = state.get("user_query", "")
    api_key = os.getenv("GOOGLE_API_KEY")
    
    parser = PydanticOutputParser(pydantic_object=IntentOutput)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Bạn là một AI Network Engineer lão luyện. Nhiệm vụ của bạn là đọc yêu cầu từ quản trị viên, xác định thiết bị mạng (nếu có IP) và Lên danh sách các lệnh Cisco (IOS/NXOS) CẦN THIẾT (đặc biệt là lệnh 'show') để bắt bệnh hệ thống.\n\n{format_instructions}"),
        ("user", "Yêu cầu: {query}")
    ])
    
    # Predefined model fallbacks — Ưu tiên OpenRouter theo yêu cầu người dùng
    models = [
        "openrouter/meta-llama/llama-3.3-70b-instruct:free",
        "openrouter/google/gemma-3-27b-it:free",
        "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        "gemini/gemini-2.0-flash",
        "gemini/gemini-2.5-flash",
        "groq/llama-3.3-70b-versatile",
        "gemini/gemini-2.5-pro",
        "gemini/gemini-flash-latest",
        "openrouter/qwen/qwen3-coder:free",
        "openrouter/meta-llama/llama-3.2-3b-instruct:free",
    ]

    preferred = state.get("preferred_model")
    if preferred and preferred not in models:
        models.insert(0, preferred)

    logs = []
    
    import concurrent.futures
    def run_single_model(model_name):
        llm = init_llm(model_name)
        if not llm: raise Exception(f"Invalid model {model_name}")
        chain = prompt | llm | parser
        return chain.invoke({"query": query, "format_instructions": parser.get_format_instructions()}), model_name

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as executor:
        futures = {executor.submit(run_single_model, m): m for m in models}
        for future in concurrent.futures.as_completed(futures):
            model_full_name = futures[future]
            try:
                result, _ = future.result()
                try: 
                    executor.shutdown(wait=False, cancel_futures=True) 
                except: 
                    pass # Fallback for old Python
                return {
                    "device_ips": result.device_ips,
                    "required_commands": result.commands,
                    "intent_summary": result.intent_summary,
                    "agent_logs": logs + [f"Sử dụng AI Model (Siêu tốc độ): {model_full_name}"]
                }
            except Exception as e:
                raw_err = str(e).split('\n')[0][:80]
                logs.append(f"Model {model_full_name} bỏ qua: {raw_err}")
            
    return {
        "device_ips": ["192.168.1.1"],
        "required_commands": ["show vlan brief", "show ip interface brief", "show log"],
        "intent_summary": "Lỗi API, tự động kích hoạt kiểm tra tổng quát (Fallback Mode).",
        "agent_logs": logs + ["⚠️ TẤT CẢ MODEL AI ĐỀU LỖI. Hãy kiểm tra lại API Key và Region."]
    }

def connect_and_execute(state: AgentState) -> dict:
    """
    Node 2: SSH vào danh sách thiết bị mạng và chạy các lệnh.
    """
    logger.info("Node: connect_and_execute")
    device_ips = state.get("device_ips", ["192.168.1.1"])
    commands = state.get("required_commands", [])
    simulation = state.get("simulation", False)
    
    if not commands:
        return {"ssh_raw_output": {}, "agent_logs": ["Bỏ qua SSH do không có lệnh yêu cầu."]}

    import concurrent.futures
    all_outputs = {}
    logs = []

    def fetch_from_device(ip):
        return ip, SSHTool.execute_commands(ip, commands, simulation=simulation)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(device_ips)) as executor:
        future_to_ip = {executor.submit(fetch_from_device, ip): ip for ip in device_ips}
        for future in concurrent.futures.as_completed(future_to_ip):
            ip, results = future.result()
            all_outputs[ip] = results
            logs.append(f"Đã quét xong thiết bị: {ip}")
        
    return {
        "ssh_raw_output": all_outputs,
        "agent_logs": logs
    }

def analyze_and_diagnose(state: AgentState) -> dict:
    """
    Node 3: Phân tích output trả về, tìm Root Cause và gợi ý solution.
    """
    logger.info("Node: analyze_and_diagnose")
    raw_outputs = state.get("ssh_raw_output", {})
    query = state.get("user_query", "")
    api_key = os.getenv("GOOGLE_API_KEY")
    
    parser = PydanticOutputParser(pydantic_object=DiagnoseOutput)
    
    # Gộp tất cả output từ các device vào 1 string để AI phân tích tương quan
    output_text = ""
    for ip, results in raw_outputs.items():
        output_text += f"\n=== THIẾT BỊ: {ip} ===\n"
        output_text += "\n---\n".join([f"Lệnh: {cmd}\nKết quả:\n{out}" for cmd, out in results.items()])
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Bạn là một AI Cisco Expert Level 3 (CCIE). Ai đó đã chạy các câu lệnh bắt bệnh trên MỘT HOẶC NHIỀU thiết bị mạng.\n\nNhiệm vụ của bạn: Phân tích chi tiết lỗi, tìm mối tương quan giữa các thiết bị nếu có, đánh giá mức độ tổn hại (severity) và gợi ý danh sách chuẩn các câu lệnh cấu hình (Config fix) để sửa lỗi. TOÀN BỘ PHÂN TÍCH (bao gồm root_cause) PHẢI ĐƯỢC VIẾT BẰNG TIẾNG VIỆT.\n\n{format_instructions}"),
        ("user", "Yêu cầu gốc từ quản trị: {query}\n\n=======================\nOUTPUTS TỪ CÁC THIẾT BỊ:\n{outputs}")
    ])
    
    # Predefined model fallbacks — Ưu tiên OpenRouter theo yêu cầu người dùng
    models = [
        "openrouter/meta-llama/llama-3.3-70b-instruct:free",
        "openrouter/google/gemma-3-27b-it:free",
        "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        "gemini/gemini-2.0-flash",
        "gemini/gemini-2.5-flash",
        "groq/llama-3.3-70b-versatile",
        "gemini/gemini-2.5-pro",
        "gemini/gemini-flash-latest",
        "openrouter/qwen/qwen3-coder:free",
        "openrouter/meta-llama/llama-3.2-3b-instruct:free",
    ]

    preferred = state.get("preferred_model")
    if preferred and preferred not in models:
        models.insert(0, preferred)

    logs = []
    
    import concurrent.futures
    def run_diagnose_model(model_name):
        llm = init_llm(model_name)
        if not llm: raise Exception(f"Invalid model {model_name}")
        chain = prompt | llm | parser
        return chain.invoke({"query": query, "outputs": output_text, "format_instructions": parser.get_format_instructions()}), model_name

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as executor:
        futures = {executor.submit(run_diagnose_model, m): m for m in models}
        for future in concurrent.futures.as_completed(futures):
            model_full_name = futures[future]
            try:
                result, _ = future.result()
                try: 
                    executor.shutdown(wait=False, cancel_futures=True) 
                except: 
                    pass
                return {
                    "status_severity": result.status_severity,
                    "root_cause_analysis": result.root_cause,
                    "suggested_fix_commands": result.fix_commands,
                    "agent_logs": logs + [f"Phân tích chẩn đoán bằng (Siêu tốc): {model_full_name}"]
                }
            except Exception as e:
                raw_err = str(e).split('\n')[0][:80]
                logs.append(f"Model {model_full_name} chẩn đoán bỏ qua: {raw_err}")

    return {
        "status_severity": "unknown",
        "root_cause_analysis": f"Không thể phân tích bằng AI sau khi thử mọi model. Dữ liệu Raw:\n {output_text}",
        "suggested_fix_commands": [],
        "agent_logs": logs + ["⚠️ Chẩn đoán AI thất bại hoàn toàn. Hãy kiểm tra lại API Key."]
    }

