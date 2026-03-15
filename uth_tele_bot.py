import psycopg2
import telebot
from telebot import types, apihelper
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import time
import threading
import schedule
import os
from datetime import datetime, timedelta

# --- CONFIG TỪ DOCKER ENV ---
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "db"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS")
}
TELE_TOKEN = os.getenv("TELE_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# --- LOGGING ---
def get_now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def log(level, message): print(f"[{get_now()}] [{level}] {message}", flush=True)

# --- RESILIENCE CONFIG ---
apihelper.CONNECT_TIMEOUT = 60
apihelper.READ_TIMEOUT = 60
def create_retry_session():
    session = requests.Session()
    retry_strategy = Retry(total=5, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    return session
apihelper.CUSTOM_REQUEST_SENDER = lambda method, url, **kwargs: create_retry_session().request(method, url, **kwargs)

bot = telebot.TeleBot(TELE_TOKEN)

# --- DATABASE LOGIC ---
def get_db_conn(): return psycopg2.connect(**DB_CONFIG)

def init_db():
    log("SYSTEM", "Bắt đầu kiểm tra và khởi tạo Database...")
    retries = 10
    while retries > 0:
        try:
            conn = get_db_conn(); cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id TEXT PRIMARY KEY, 
                    uth_user TEXT NOT NULL, 
                    uth_pass TEXT NOT NULL, 
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit(); cur.close(); conn.close()
            log("INFO", "Hệ thống Database đã sẵn sàng và đã tạo bảng.")
            return
        except Exception as e:
            log("RETRY", f"DB chưa sẵn sàng, đang thử lại sau 5s... ({retries}) - {e}")
            retries -= 1
            time.sleep(5)
    log("CRITICAL", "Không thể khởi tạo Database sau nhiều lần thử!")

# --- API TRƯỜNG ---
def verify_uth_credentials(user, password):
    try:
        r = requests.post("https://portal.ut.edu.vn/api/v1/user/login", json={"username": user, "password": password}, timeout=15)
        data = r.json()
        if r.status_code == 200 and data.get("token"): return True, "Thành công"
        return False, data.get("message", "Sai tài khoản hoặc mật khẩu")
    except: return False, "Lỗi kết nối server trường"

def get_classes_by_date(user, password, target_date):
    try:
        r = requests.post("https://portal.ut.edu.vn/api/v1/user/login", json={"username": user, "password": password}, timeout=20)
        tk = r.json().get("token")
        if not tk: return None
        thu = datetime.strptime(target_date, "%Y-%m-%d").weekday() + 2 
        res = requests.get(f"https://portal.ut.edu.vn/api/v1/lichhoc/lichTuan?date={target_date}", headers={"authorization": f"Bearer {tk}"}, timeout=20)
        return [c for c in res.json().get("body", []) if c.get("thu") == thu]
    except: return None

# --- UI HELPER ---
def main_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("📅 Lịch hôm nay", "⏭️ Lịch ngày mai")
    markup.add("🔑 Đăng ký tài khoản", "🔍 Check ngày khác")
    markup.add("📩 Góp ý/Báo lỗi")
    if str(chat_id) == ADMIN_ID: markup.add("📊 Admin Stats")
    return markup

# --- HANDLERS ---
@bot.message_handler(commands=['start', 'help'])
def welcome(message):
    log("INFO", f"User {message.chat.id} vừa nhấn /start")
    bot.reply_to(message, "Chào bạn! Mình là Bot nhắc lịch UTH. Chọn nút bên dưới để bắt đầu nhé.", reply_markup=main_menu(message.chat.id))

@bot.message_handler(commands=['login'])
@bot.message_handler(func=lambda m: m.text == "🔑 Đăng ký tài khoản")
def start_login(message):
    log("ACTION", f"User {message.chat.id} bắt đầu quy trình đăng ký")
    msg = bot.send_message(message.chat.id, "🔹 Bước 1: Bạn vui lòng nhập **MSSV** của mình nhé:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_mssv_step)

def process_mssv_step(message):
    mssv = message.text
    if not mssv or len(mssv) < 5:
        log("WARN", f"User {message.chat.id} nhập MSSV không hợp lệ: {mssv}")
        bot.reply_to(message, "MSSV không hợp lệ, bạn vui lòng thử lại nha.")
        return
    log("INFO", f"User {message.chat.id} nhập MSSV: {mssv}")
    msg = bot.send_message(message.chat.id, f"✅ Nhận MSSV: `{mssv}`\n🔹 Bước 2: Bạn nhập **Mật khẩu UTH** nhé:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_password_step, {'mssv': mssv})

def process_password_step(message, user_data):
    pwd = message.text
    log("ACTION", f"Đang xác thực tài khoản cho User {message.chat.id} (MSSV: {user_data['mssv']})")
    bot.send_message(message.chat.id, "⏳ Đang xác thực thông tin, bạn đợi mình xíu nha...")
    is_valid, reason = verify_uth_credentials(user_data['mssv'], pwd)
    if is_valid:
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("INSERT INTO users (chat_id, uth_user, uth_pass) VALUES (%s, %s, %s) ON CONFLICT (chat_id) DO UPDATE SET uth_user = EXCLUDED.uth_user, uth_pass = EXCLUDED.uth_pass", (str(message.chat.id), user_data['mssv'], pwd))
        conn.commit(); cur.close(); conn.close()
        log("SUCCESS", f"User {message.chat.id} đã đăng ký thành công vào Database")
        bot.send_message(message.chat.id, "🎉 **Đăng ký thành công!** Mình sẽ tự động nhắc lịch cho bạn.", reply_markup=main_menu(message.chat.id), parse_mode="Markdown")
    else:
        log("ERROR", f"User {message.chat.id} đăng ký thất bại: {reason}")
        bot.send_message(message.chat.id, f"❌ Thất bại: {reason}")

@bot.message_handler(func=lambda m: True)
def menu_handler(message):
    if message.text == "📅 Lịch hôm nay":
        log("QUERY", f"User {message.chat.id} xem lịch hôm nay")
        process_manual(message, datetime.now().strftime("%Y-%m-%d"))
    elif message.text == "⏭️ Lịch ngày mai":
        log("QUERY", f"User {message.chat.id} xem lịch ngày mai")
        process_manual(message, (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
    elif message.text == "🔍 Check ngày khác":
        log("ACTION", f"User {message.chat.id} muốn check ngày tùy chọn")
        msg = bot.send_message(message.chat.id, "📅 Nhập ngày (YYYY-MM-DD):")
        bot.register_next_step_handler(msg, lambda m: process_manual(m, m.text))
    elif str(message.chat.id) == ADMIN_ID and message.text == "📊 Admin Stats":
        log("ADMIN", f"Admin {ADMIN_ID} đang xem thống kê hệ thống")
        conn = get_db_conn(); cur = conn.cursor(); cur.execute("SELECT COUNT(*) FROM users")
        count = cur.fetchone()[0]
        bot.send_message(message.chat.id, f"📊 Tổng số người dùng: {count}")
        cur.close(); conn.close()

def process_manual(message, date_str):
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        conn = get_db_conn(); cur = conn.cursor()
        cur.execute("SELECT uth_user, uth_pass FROM users WHERE chat_id = %s", (str(message.chat.id),))
        u = cur.fetchone(); cur.close(); conn.close()
        if not u:
            bot.reply_to(message, "Bạn chưa đăng ký tài khoản mà!")
            return
        classes = get_classes_by_date(u[0], u[1], date_str)
        if classes:
            msg = f"📅 **LỊCH HỌC {date_str}**\n"
            for c in classes: msg += f"\n📘 {c['tenMonHoc']}\n⏰ {c['tuGio']} - {c['denGio']}\n📍 {c['tenPhong']}\n"
            bot.send_message(message.chat.id, msg, parse_mode="Markdown")
        else: bot.send_message(message.chat.id, f"🎉 Ngày {date_str} bạn được nghỉ nè!")
    except:
        log("ERROR", f"User {message.chat.id} nhập sai định dạng ngày: {date_str}")
        bot.send_message(message.chat.id, "Định dạng ngày không đúng rồi (YYYY-MM-DD).")

# --- PHẦN XỬ LÝ GÓP Ý / BÁO LỖI ---

@bot.message_handler(func=lambda m: m.text == "📩 Góp ý/Báo lỗi")
@bot.message_handler(commands=['feedback'])
def handle_feedback_request(message):
    """Tiếp nhận yêu cầu gửi góp ý từ người dùng."""
    log("ACTION", f"Người dùng {message.chat.id} chuẩn bị gửi góp ý.")
    
    # Tin nhắn hướng dẫn thân thiện
    guide_text = (
        "😊 **Mình rất sẵn lòng lắng nghe bạn!**\n\n"
        "Bạn hãy nhập nội dung góp ý, báo lỗi hoặc tính năng mới mà bạn mong muốn vào đây nhé.\n\n"
        "*(Lưu ý: Bạn có thể đính kèm thông tin liên lạc nếu muốn mình phản hồi trực tiếp)*"
    )
    
    msg = bot.send_message(message.chat.id, guide_text, parse_mode="Markdown")
    # Chuyển hướng sang bước ghi nhận nội dung
    bot.register_next_step_handler(msg, process_feedback_content)

def process_feedback_content(message):
    """Ghi nhận nội dung và gửi cho Admin."""
    feedback_text = message.text
    chat_id = message.chat.id

    if not feedback_text or len(feedback_text) < 5:
        log("WARN", f"Góp ý từ {chat_id} quá ngắn hoặc trống.")
        bot.send_message(chat_id, "⚠️ Nội dung hơi ngắn thì phải, bạn có thể viết kỹ hơn một chút không?")
        return

    log("FEEDBACK", f"Nhận được góp ý từ {chat_id}: {feedback_text[:30]}...")

    # 1. Gửi thông báo xác nhận cho người dùng
    confirmation = (
        "✅ **Gửi thành công!**\n\n"
        "Cảm ơn bạn đã dành thời gian đóng góp để Bot ngày càng hoàn thiện hơn. "
        "Admin sẽ xem xét ý kiến của bạn sớm nhất có thể."
    )
    bot.send_message(chat_id, confirmation, parse_mode="Markdown", reply_markup=main_menu(chat_id))

    # 2. Chuyển tiếp góp ý đến Admin
    if ADMIN_ID:
        try:
            admin_alert = (
                f"📩 **CÓ GÓP Ý MỚI**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 **Người gửi:** `{chat_id}`\n"
                f"📝 **Nội dung:**\n{feedback_text}"
            )
            bot.send_message(ADMIN_ID, admin_alert, parse_mode="Markdown")
        except Exception as e:
            log("ADMIN_ERROR", f"Không thể chuyển feedback đến Admin: {e}")

            
def broadcast_to_all_users(content):
    """Hàm xử lý việc gửi tin nhắn đến toàn bộ người dùng trong DB."""
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT chat_id FROM users")
        user_list = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        log("DATABASE_ERROR", f"Không thể truy xuất danh sách người dùng: {e}")
        return 0

    count = 0
    for user in user_list:
        chat_id = user[0]
        try:
            # Nội dung thông báo thân thiện
            formatted_msg = (
                f"📢 **THÔNG BÁO MỚI**\n\n"
                f"{content}\n\n"
                f"--- \n"
                f"✨ *Chúc bạn một ngày học tập hiệu quả!*"
            )
            bot.send_message(chat_id, formatted_msg, parse_mode="Markdown")
            count += 1
            # Nghỉ 0.3s để tuân thủ giới hạn của Telegram API (Anti-flood)
            time.sleep(0.3)
        except Exception as e:
            log("SEND_ERROR", f"Không thể gửi thông báo đến Chat ID {chat_id}: {e}")
            
    return count

@bot.message_handler(commands=['broadcast'])
def admin_broadcast_handler(message):
    """Handler tiếp nhận lệnh phát loa từ Admin."""
    # Kiểm tra quyền Admin (Chuyển ADMIN_ID về string để so sánh cho chắc)
    if str(message.chat.id) != str(ADMIN_ID):
        log("SECURITY", f"User {message.chat.id} thử dùng lệnh Admin trái phép.")
        return

    # Tách lấy nội dung sau lệnh /broadcast
    raw_input = message.text.split(maxsplit=1)
    
    if len(raw_input) < 2:
        bot.reply_to(message, "Bạn vui lòng nhập nội dung cần thông báo nhé.\nVí dụ: `/broadcast Ngày mai có lịch nghỉ bù đó!`", parse_mode="Markdown")
        return

    broadcast_content = raw_input[1]
    log("ADMIN_ACTION", f"Admin {ADMIN_ID} đang gửi thông báo: {broadcast_content[:20]}...")

    # Phản hồi lại Admin và bắt đầu gửi
    bot.send_message(message.chat.id, "⏳ Hệ thống đang tiến hành gửi thông báo, bạn vui lòng đợi xíu...")
    
    total_delivered = broadcast_to_all_users(broadcast_content)
    
    bot.send_message(message.chat.id, f"✅ Đã gửi thông báo thành công đến {total_delivered} bạn sinh viên.")

# --- MAIN ---
if __name__ == "__main__":
    init_db()
    threading.Thread(target=lambda: (log("SCHEDULE", "Task tự động bắt đầu chạy."), schedule.every().day.at("05:00").do(lambda: log("AUTO", "Đang gửi lịch sáng...")), ), daemon=True).start()
    log("SYSTEM", "Bot UTH (Bản Full Log) đã sẵn sàng chiến đấu!")
    bot.infinity_polling(timeout=60, long_polling_timeout=40)