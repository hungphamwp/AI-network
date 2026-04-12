from langgraph.graph import StateGraph, END
import logging

from src.agent.state import AgentState
from src.agent.nodes import parse_intent, connect_and_execute, analyze_and_diagnose

logger = logging.getLogger(__name__)

def create_network_agent():
    """
    Tạo luồng Agent xử lý Mạng bằng LangGraph.
    Flow: 
    1. parse_intent (Hiểu ý định)
    2. connect_and_execute (Chạy lệnh SSH)
    3. analyze_and_diagnose (Chẩn đoán)
    """
    
    workflow = StateGraph(AgentState)
    
    workflow.add_node("parse_intent", parse_intent)
    workflow.add_node("connect_and_execute", connect_and_execute)
    workflow.add_node("analyze_and_diagnose", analyze_and_diagnose)
    
    workflow.set_entry_point("parse_intent")
    
    workflow.add_edge("parse_intent", "connect_and_execute")
    workflow.add_edge("connect_and_execute", "analyze_and_diagnose")
    workflow.add_edge("analyze_and_diagnose", END)
    
    return workflow.compile()

def run_agent(query: str, preferred_model: str = None):
    """ Hàm helper khởi chạy Agent truyền vào input tự nhiên. """
    app = create_network_agent()
    
    initial_state = {
        "user_query": query,
        "device_ip": "",
        "required_commands": [],
        "intent_summary": "",
        "ssh_raw_output": {},
        "status_severity": "",
        "root_cause_analysis": "",
        "suggested_fix_commands": [],
        "history": [],
        "agent_logs": [],
        "preferred_model": preferred_model
    }

    
    logger.info("=========================================")
    logger.info(f"KHỞI ĐỘNG AI NETWORK AGENT: {query}")
    logger.info("=========================================")
    
    final_state = app.invoke(initial_state)
    return final_state
