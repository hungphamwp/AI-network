from typing import Annotated, TypedDict, List, Dict, Any

def append_messages(state_list: List, new_item: Any) -> List:
    if isinstance(new_item, list):
        return state_list + new_item
    return state_list + [new_item]

class AgentState(TypedDict):
    """
    Khai báo State lưu trữ dữ liệu truyền qua các Node của LangGraph workflow.
    """
    
    # 1. Đầu vào người dùng
    user_query: str
    
    # 2. Suy luận intent
    # device_ips: Danh sách các IP trích xuất từ câu query (VD: ['192.168.1.1', '192.168.1.2']).
    device_ips: List[str]
    # required_commands: Danh sách các lệnh show (VD: ["show vlan brief", "show logging"])
    required_commands: List[str]
    intent_summary: str
    
    # 3. Quá trình xử lý
    # Raw output dạng text sau khi chạy SSH
    ssh_raw_output: Dict[str, str]
    
    # 4. Phân tích kết quả
    # Điểm đánh giá mức độ nghiêm trọng (critical, warning, ok)
    status_severity: str
    # Tổng kết root cause
    root_cause_analysis: str
    
    # 5. Khắc phục sự cố
    # Nếu có lỗi, AI đề xuất các lệnh để config lại
    suggested_fix_commands: List[str]
    # Lịch sử hội thoại nếu làm dạng chat agent liên tục
    history: Annotated[List[Any], append_messages]
    # Nhật ký vận hành hệ thống (gửi cho UI Console)
    agent_logs: Annotated[List[str], append_messages]
    # Model AI ưa thích được chọn từ UI
    preferred_model: str
    
    # Bật chế độ giả lập không chạy SSH thật
    simulation: bool

