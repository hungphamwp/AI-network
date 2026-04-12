import sys
import os
import logging
from colorama import init, Fore, Style
from dotenv import load_dotenv

# Đảm bảo có thể import các package trong src từ thư mục gốc
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.graph import run_agent
from src.tools.ssh_netmiko import SSHTool

init(autoreset=True)

# Cấu hình logging để tắt bớt rác từ netmiko/langchain
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("src")
logger.setLevel(logging.INFO)

load_dotenv()

def print_header():
    print(Fore.CYAN + Style.BRIGHT + "-"*60)
    print(Fore.CYAN + Style.BRIGHT + "   🤖 NET-AI ASSISTANT (Powered by LangGraph & Netmiko)")
    if os.getenv("MOCK_SSH", "False").lower() == "true":
         print(Fore.YELLOW + "   [!] Đang chạy ở chế độ MOCK_SSH=True (Thiết bị ảo)")
    else:
         print(Fore.GREEN + "   [*] Đang chạy ở chế độ LIVE (Kết nối Netmiko thật)")
    print(Fore.CYAN + Style.BRIGHT + "-"*60)

def main():
    print_header()
    
    while True:
        try:
            print(Fore.GREEN + "\n💬 Nhập yêu cầu (hoặc 'exit' để thoát): ")
            user_input = input(Fore.WHITE + "> ")
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Tạm biệt!")
                break
            
            if not user_input.strip():
                continue
                
            print(Fore.YELLOW + "\n⏳ Agent đang phân tích ý định...")
            
            # Chạy LangGraph
            state = run_agent(user_input)
            
            print(Fore.CYAN + "\n🎯 PHÂN TÍCH INTENT:")
            print(f"- Mục tiêu: {state.get('intent_summary')}")
            print(f"- Thiết bị ngắm tới: {state.get('device_ip')}")
            print(f"- Các lệnh cấu hình chạy: {state.get('required_commands')}")
            
            print(Fore.GREEN + "\n🩺 KẾT QUẢ CHẨN ĐOÁN BỞI AI:")
            severity = state.get("status_severity", "unknown").upper()
            color = Fore.RED if "CRIT" in severity else Fore.YELLOW if "WARN" in severity else Fore.GREEN
            print(f"[{color}{severity}{Fore.RESET}] {state.get('root_cause_analysis')}")
            
            fixes = state.get("suggested_fix_commands", [])
            if fixes:
                print(Fore.MAGENTA + "\n🛠 GỢI Ý CẤU HÌNH FIX LỖI:")
                for f in fixes:
                    print(f"   {f}")
                    
                # Optionally ask to apply fix
                confirm = input(Fore.YELLOW + "\nBạn có muốn tự động Push cấu hình này qua SSH không? (y/n): ")
                if confirm.lower() == 'y':
                    print(Fore.YELLOW + "Đang đẩy cấu hình xuống thiết bị...")
                    ip = state.get("device_ip")
                    result = SSHTool.apply_config(ip, fixes)
                    print(Fore.GREEN + "\n✅ KẾT QUẢ PUSH CONFIG:")
                    print(result)
            
        except KeyboardInterrupt:
            print("\nTạm biệt!")
            break
        except Exception as e:
            print(Fore.RED + f"\nLỗi: {e}")

if __name__ == "__main__":
    main()
