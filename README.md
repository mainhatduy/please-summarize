# Discord Group Chat Summarizer & Music Self-Bot

Dự án này là một Discord Self-bot (chạy dưới danh nghĩa tài khoản cá nhân) giúp thực hiện 2 tính năng chính trong Nhóm chat riêng tư (Group Chat / Group DM):
1. **Tóm tắt nội dung chat:** Thu thập $N$ tin nhắn gần nhất hoặc tin nhắn trong $N$ giờ trước đó, gửi qua Gemini API để dịch và tóm tắt ngắn gọn bằng tiếng Việt.
2. **Phát nhạc YouTube:** Tải luồng âm thanh từ YouTube thông qua `yt-dlp` và stream trực tiếp vào cuộc gọi thoại (Voice Call) của nhóm chat sử dụng `FFmpeg`.

---

## ⚠️ Lưu ý quan trọng (Discord ToS)

> [!WARNING]
> Việc sử dụng **Self-bot** (tự động hóa tài khoản cá nhân) là vi phạm **Điều khoản dịch vụ (ToS)** của Discord.
> Tài khoản chạy bot này có nguy cơ bị Discord quét và khóa vĩnh viễn. 
> Hãy **chỉ sử dụng tài khoản clone (tài khoản phụ)** để chạy thử nghiệm dự án này, tuyệt đối không dùng tài khoản chính.

---

## 🛠️ Yêu cầu hệ thống

Trước khi bắt đầu, hãy chắc chắn máy tính của bạn đã cài đặt:
1. **Python 3.11** trở lên.
2. **uv** (Bộ quản lý gói cực nhanh dành cho Python). Cài đặt thông qua:
   ```bash
   pip install uv
   ```
3. **FFmpeg** (Công cụ xử lý và giải mã âm thanh).
   - **Ubuntu/Debian:** `sudo apt update && sudo apt install -y ffmpeg`
   - **macOS (Homebrew):** `brew install ffmpeg`
   - **Windows:** Tải từ trang chủ FFmpeg và thêm thư mục `bin` vào biến môi trường PATH.

---

## ⚙️ Cấu hình và Cài đặt

### 1. Chuẩn bị file `.env`
Sao chép hoặc chỉnh sửa file `.env` ở thư mục gốc của dự án:
```env
DISCORD_TOKEN=your_discord_user_token_here
GEMINI_API_KEY=your_gemini_api_key_here
# CHANNEL_ID=your_target_channel_id_here  # (Tùy chọn)
```

> [!IMPORTANT]
> **Cách lấy Discord User Token (Self-bot Token):**
> 1. Mở Discord trên trình duyệt web (Chrome/Firefox) và đăng nhập tài khoản phụ.
> 2. Nhấn `F12` (hoặc `Ctrl + Shift + I`) để mở Developer Tools, chọn tab **Network** (Mạng).
> 3. Gõ một tin nhắn bất kỳ hoặc chuyển kênh để phát sinh request.
> 4. Tìm các request có tên bắt đầu bằng `messages` hoặc `science`.
> 5. Xem phần **Request Headers**, sao chép giá trị của trường **`Authorization`** (Đây chính là User Token của bạn, có dạng một chuỗi ký tự dài không bắt đầu bằng "Bot ").
> 6. Dán token này vào biến `DISCORD_TOKEN` trong `.env`.

> [!TIP]
> **Cách cấu hình lọc kênh bằng CHANNEL_ID (Tùy chọn):**
> Nếu muốn bot chỉ nhận và thực hiện lệnh trong một Group DM hoặc kênh chat cụ thể, bạn hãy thêm dòng `CHANNEL_ID=ID_KÊNH_CỦA_BẠN` vào file `.env`. Nếu không cấu hình biến này, bot sẽ phản hồi lệnh từ mọi kênh chat mà bạn tham gia.

### 2. Cài đặt các thư viện
Sử dụng `uv` để đồng bộ và cài đặt toàn bộ dependencies trong file `requirements.txt`:
```bash
uv pip install -r requirements.txt
```

---

## 🚀 Cách chạy Bot

### Chạy trực tiếp (Local)

Khởi chạy ứng dụng bằng lệnh `uv`:
```bash
uv run python -m app.main
```

Bot sẽ tự động tải các biến môi trường từ file `.env` và đăng nhập vào tài khoản cá nhân của bạn.

---

## 🐳 Deploy bằng Docker

> [!TIP]
> Khuyến nghị dùng Docker để chạy bot liên tục trên server/VPS mà không cần cài Python hay FFmpeg thủ công.

### Yêu cầu

- **Docker** đã được cài đặt ([hướng dẫn cài đặt](https://docs.docker.com/get-docker/))

### 1. Chuẩn bị file `.env`

Tạo file `.env` ở thư mục gốc (xem hướng dẫn bên trên):
```env
DISCORD_TOKEN=your_discord_user_token_here
GEMINI_API_KEY=your_gemini_api_key_here
```

> [!CAUTION]
> Không bao giờ commit file `.env` lên Git. File `.gitignore` đã được cấu hình để bỏ qua nó.

### 2. Build image

```bash
docker build -t discord-summarizer-bot .
```

### 3. Chạy container

```bash
docker run -d \
  --name discord-bot \
  --env-file .env \
  --restart unless-stopped \
  discord-summarizer-bot
```

| Flag | Ý nghĩa |
|---|---|
| `-d` | Chạy nền (detached mode) |
| `--name discord-bot` | Đặt tên container để dễ quản lý |
| `--env-file .env` | Nạp biến môi trường từ file `.env` |
| `--restart unless-stopped` | Tự restart nếu bot crash, trừ khi dừng thủ công |

### 4. Quản lý container

```bash
# Xem log (theo dõi realtime)
docker logs -f discord-bot

# Xem log 50 dòng gần nhất
docker logs discord-bot --tail 50

# Dừng bot
docker stop discord-bot

# Khởi động lại bot
docker restart discord-bot

# Xóa container (cần dừng trước)
docker rm discord-bot
```

### 5. Cập nhật bot (khi có thay đổi code)

```bash
# Build lại image với code mới
docker build -t discord-summarizer-bot .

# Xóa container cũ và chạy lại
docker rm -f discord-bot
docker run -d \
  --name discord-bot \
  --env-file .env \
  --restart unless-stopped \
  discord-summarizer-bot
```

---

## 📝 Danh sách câu lệnh (Prefix: `.`)

Tất cả thành viên trong Group DM đều có thể sử dụng các lệnh sau:

### 💬 Lệnh tóm tắt tin nhắn (Text)
*   `.tomtat <limit>` (hoặc `.sum_msgs`): Tóm tắt $N$ tin nhắn gần nhất trong group chat (Mặc định là 50 tin nhắn nếu không nhập số, tối đa 500 tin nhắn).
*   `.tomtat_time <hours>` (hoặc `.sum_time`): Tóm tắt toàn bộ tin nhắn chat phát sinh trong $N$ giờ trước đó (Mặc định là 1 giờ, tối đa 12 giờ, tổng hợp tối đa 500 tin nhắn).

### 🎶 Lệnh phát nhạc (Voice call)
*   `.join`: Yêu cầu bot tham gia vào cuộc gọi thoại đang diễn ra của nhóm chat.
*   `.play <tên bài hát hoặc link YouTube>`: Yêu cầu bot tham gia cuộc gọi (nếu chưa vào) và phát nhạc từ YouTube (hỗ trợ tìm kiếm theo tên hoặc nhận diện link trực tiếp).
*   `.leave` (hoặc `.stop`): Dừng phát nhạc và ngắt kết nối bot khỏi cuộc gọi thoại.
