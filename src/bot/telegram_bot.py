import os
import sys
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Thêm đường dẫn gốc vào sys.path để import từ src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.graph import run_agent
from src.tools.ssh_netmiko import SSHTool

# Tắt bớt log debug của thư viện
logging.getLogger("httpx").setLevel(logging.WARNING)

# Lưu trữ context của user tạm trên Memory
# Ví dụ: user_contexts[chat_id] = {"device_ip": "1.1.1.1", "fixes": ["comm 1", "comm 2"]}
user_contexts = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = (
        "🤖 *NetAI Assistant Bot*\n\n"
        "Chào bạn! Mình có thể giúp gì cho hệ thống mạng hôm nay?\n\n"
        "Ví dụ:\n"
        "`check vlan 10`\n"
        "`check trunk port Gi0/1`\n\n"
        "Sau khi có lỗi, hãy dán lệnh `fix` để mình tự động sửa nhé."
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    
    # 1. Nếu user gõ chữ "fix"
    if text.lower() == "fix":
        ctx = user_contexts.get(chat_id)
        if not ctx or not ctx.get("fixes"):
            await update.message.reply_text("Không có lỗi nào đang chờ xử lý hoặc chưa có lệnh khắc phục. Vui lòng check trước.")
            return
            
        device_ips = ctx.get("device_ips", [])
        fixes = ctx.get("fixes", [])
        
        if not device_ips:
            await update.message.reply_text("Không xác định được thiết bị cần fix.")
            return
            
        ip = device_ips[0] # Cho demo: chỉ lấy thiết bị đầu tiên
        
        msg = await update.message.reply_text(f"⏳ Đang thực thi {len(fixes)} lệnh cấu hình lên {ip}...")
        
        # Mặc định bật simulation như server.py nếu đang ở môi trường chưa có thiết bị thật
        # Lấy từ env: MOCK_SSH 
        is_mock = os.getenv("MOCK_SSH", "True").lower() == "true"
        
        result = SSHTool.apply_config(ip, fixes, simulation=is_mock)
        
        if "Error" in result:
            await msg.edit_text(f"❌ *Sửa lỗi thất bại:*\n```\n{result}\n```", parse_mode="Markdown")
        else:
            await msg.edit_text(f"✅ *Đã sửa!*\n\nĐã cấu hình thành công trên thiết bị {ip}.", parse_mode="Markdown")
            # Clear context after fix
            user_contexts.pop(chat_id, None)
            
        return

    # 2. Xử lý các câu query chẩn đoán bình thường
    msg = await update.message.reply_text("⏳ Cho NetAI 1 xíu để phân tích nhé...")
    
    try:
        # Chạy agent trong chế độ simulation giống môi trường
        is_mock = os.getenv("MOCK_SSH", "True").lower() == "true"
        state = run_agent(text, simulation=is_mock)
        
        severity = state.get("status_severity", "unknown").lower()
        root_cause = state.get("root_cause_analysis", "Không tìm thấy nguyên nhân rõ rệt.")
        device_ips = state.get("device_ips", [])
        fixes = state.get("suggested_fix_commands", [])
        
        icon = "🟢" if severity == "ok" else "🔴" if severity in ["critical", "error"] else "🟡"
        
        reply = f"{icon} *Kết quả chẩn đoán:*\n\n"
        reply += f"📍 *Module:* {', '.join(device_ips) if device_ips else 'Không rõ'}\n"
        reply += f"🔍 *Chi tiết:* {root_cause}\n"
        
        if fixes:
            reply += f"\n🛠 *Đề xuất sửa lỗi:* Đã tìm thấy {len(fixes)} lệnh khắc phục."
            reply += "\n👉 *Hãy chat `fix` để mình tự động nạp vào cấu hình.*"
            # Lưu context cho lượt sau
            user_contexts[chat_id] = {
                "device_ips": device_ips,
                "fixes": fixes
            }
        else:
            # Xoá context
            user_contexts.pop(chat_id, None)
            
        await msg.edit_text(reply, parse_mode="Markdown")
        
    except Exception as e:
        await msg.edit_text(f"❌ Lỗi xử lý backend: {e}")

def main():
    # Force reload dotenv from absolute path just to be sure
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    load_dotenv(env_file, override=True)
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token or token == "token_cua_ban":
        print("Vui lòng cập nhật TELEGRAM_BOT_TOKEN bằng Token chuẩn thông qua Web UI hoặc trong file .env trước khi chạy bot.")
        return
        
    print("🚀 Khởi động Telegram Bot thành công. Đang lắng nghe...")
    
    app = ApplicationBuilder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    app.run_polling()

if __name__ == '__main__':
    main()
