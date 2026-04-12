# NetAI Agent - Trợ lý AI Quản trị Mạng

NetAI Agent là một hệ thống AIOps (Artificial Intelligence for IT Operations) ứng dụng sức mạnh của các mô hình ngôn ngữ lớn (LLMs như Google Gemini, Llama 3) kết hợp với LangGraph và thư viện Netmiko để chẩn đoán, phân tích, và tự động hóa các tác vụ quản trị mạng.

Dự án bao gồm:
1. **Web Dashboard:** Giao diện quản trị bắt mắt giúp theo dõi quá trình AI xử lý, hiển thị sơ đồ luồng, và cấu hình các thông số hệ thống.
2. **Telegram Chat Bot:** Một Bot phụ trợ kết nối thời gian thực, cho phép quản trị viên lấy log lỗi hoặc ra lệnh sửa lỗi siêu tốc qua kết nối Telegram.

---

## 🚀 Hướng dấn Cài đặt

Dự án sử dụng Python. Tốt nhất là bạn nên chạy dự án trong môi trường ảo (virtual environment).

**Bươc 1: Clone dự án và truy cập thư mục gốc**
```bash
cd net_ai_assistant
```

**Bước 2: Khởi tạo và kích hoạt môi trường ảo (Virtual Environment)**
```bash
# Trên MacOS / Linux
python3 -m venv venv
source venv/bin/activate

# Trên Windows
python -m venv venv
.\venv\Scripts\activate
```

**Bước 3: Cài đặt thư viện phụ thuộc**
```bash
pip install -r requirements.txt
```

---

## ⚙️ Cấu hình hệ thống (.env)

Hệ thống cho phép cấu hình trực tiếp từ giao diện Web, nhưng bạn cũng có thể mở file `.env` (hoặc sao chép từ `.env.example`) để định cấu hình tay ban đầu. 

Một số cấu hình chính:
- Thẻ API Keys: `GOOGLE_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`
- Hệ thống Mạng: Cấu hình `MOCK_SSH=True` nếu như bạn chỉ đang Demo trên thiết bị ảo mà không có Router Switch vật lý.

---

## 🏃 Thao tác Khởi chạy (Cách chạy Demo)

Nếu bạn chia Terminal ra làm 2 màn hình (Split Terminal), quá trình kết nối sẽ mang lại hiệu ứng cực kì trực quan.

### 1. Khởi chạy Giao diện Dashboard (Web Server)

Mở màn hình Terminal thứ #1, gõ:
```bash
# Đảm bảo dùng Python bên trong môi trường ảo
venv/bin/python src/server.py
```
👉 Sau đó truy cập vào URL: **[http://localhost:8000](http://localhost:8000)** để xem giao diện trên trình duyệt.

### 2. Khởi chạy Telegram Bot

Mở màn hình Terminal thứ #2, gõ:
```bash
venv/bin/python -m src.bot.telegram_bot
```
*(Nếu Bot chưa chạy, hãy lên Web Dashboard mục `Settings > Kênh kết nối` để cấp Token cho Telegram Bot nhé).*

---

## 🎬 Kịch bản sử dụng (Demo Example)

Khi báo cáo với giảng viên hoặc sử dụng trong thực tế, bạn có thể thực hiện Demo theo các bước sau:
1. Truy cập vào **Telegram Bot** của bạn.
2. Gõ câu lệnh hỏi AI bắt bệnh: 
   - `"check vlan 10"` hoặc `"hệ thống mạng bị lỗi Trunk port rớt, check hộ mình config GigabitEthernet0/1"`
3. AI sẽ mất khoảng 5 giây SSH vào thiết bị, phân tích bệnh (Root Cause Analysis).
4. Nếu AI liệt kê được các mã config gợi ý, bạn lập tức chat một chữ duy nhất:
   - **`fix`** 
5. Bot AI sẽ chủ động xác nhận và tự nạp lệnh vào vòng lặp config của Switch mạng và trả về kết quả cấu hình thành công!
