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
from dotenv import load_dotenv

load_dotenv()
# --- CONFIG TỪ DOCKER ENV ---
dbConfig = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS")
}

teleToken = os.getenv("TELE_TOKEN")
adminId = os.getenv("ADMIN_ID")

# --- LOGGING ---
def getNow(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def log(level, message): print(f"[{getNow()}] [{level}] {message}", flush=True)

# --- RESILIENCE CONFIG ---
apihelper.CONNECT_TIMEOUT = 60
apihelper.READ_TIMEOUT = 60

def createRetrySession():
    session = requests.Session()
    retryStrategy = Retry(total=5, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retryStrategy)
    session.mount("https://", adapter)
    return session

apihelper.CUSTOM_REQUEST_SENDER = lambda method, url, **kwargs: createRetrySession().request(method, url, **kwargs)

bot = telebot.TeleBot(teleToken)

# --- DATABASE LOGIC ---
def getDbConn(): return psycopg2.connect(**dbConfig)

def initDb():
    log("SYSTEM", "Bắt đầu kiểm tra và khởi tạo Database...")
    retries = 10
    while retries > 0:
        try:
            conn = getDbConn(); cur = conn.cursor()
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
def verifyUthCredentials(user, password):
    try:
        r = requests.post("https://portal.ut.edu.vn/api/v1/user/login", json={"username": user, "password": password}, timeout=15)
        data = r.json()
        if r.status_code == 200 and data.get("token"): return True, "Thành công"
        return False, data.get("message", "Sai tài khoản hoặc mật khẩu")
    except: return False, "Lỗi kết nối server trường"

def getClassesByDate(user, password, targetDate):
    try:
        r = requests.post("https://portal.ut.edu.vn/api/v1/user/login", json={"username": user, "password": password}, timeout=20)
        tk = r.json().get("token")
        if not tk: return None
        thu = datetime.strptime(targetDate, "%Y-%m-%d").weekday() + 2 
        res = requests.get(f"https://portal.ut.edu.vn/api/v1/lichhoc/lichTuan?date={targetDate}", headers={"authorization": f"Bearer {tk}"}, timeout=20)
        return [c for c in res.json().get("body", []) if c.get("thu") == thu]
    except: return None

# NOTE: main menu
def mainMenu(chatId):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("📅 Lịch hôm nay", "⏭️ Lịch ngày mai")
    markup.add("🔑 Đăng ký tài khoản", "🔍 Check ngày khác")
    markup.add("📩 Góp ý/Báo lỗi")
    if str(chatId) == adminId: markup.add("📊 Admin Stats")
    return markup

# NOTE: goi y lenh
def setBotCommands():
    """Thiết lập danh sách lệnh hiển thị trong menu 'Menu' của Telegram."""
    try:
        commands = [
            types.BotCommand("start", "🏠 Khởi động và hiện Menu chính"),
            types.BotCommand("login", "🔑 Đăng ký tài khoản UTH"),
            types.BotCommand("feedback", "📩 Gửi góp ý / Báo lỗi"),
            types.BotCommand("help", "❓ Hướng dẫn sử dụng")
        ]
        bot.set_my_commands(commands)
        log("SYSTEM", "Đã cập nhật danh sách lệnh hiển thị (Bot Menu).")
    except Exception as e:
        log("ERROR", f"Không thể thiết lập Bot Commands: {e}")

# --- HANDLERS ---

# start msg
@bot.message_handler(commands=['start', 'help'])
def welcome(message):
    log("INFO", f"User {message.chat.id} vừa nhấn /start")
    bot.reply_to(message, "Chào bạn! Mình là Bot nhắc lịch UTH. Chọn nút bên dưới để bắt đầu nhé.", reply_markup=mainMenu(message.chat.id))

# login
@bot.message_handler(commands=['login'])
@bot.message_handler(func=lambda m: m.text == "🔑 Đăng ký tài khoản")
def startLogin(message):
    log("ACTION", f"User {message.chat.id} bắt đầu quy trình đăng ký")
    msg = bot.send_message(message.chat.id, "🔹 Bước 1: Bạn vui lòng nhập **MSSV** của mình nhé:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, processMssvStep)

def processMssvStep(message):
    mssv = message.text
    if not mssv or len(mssv) < 5:
        log("WARN", f"User {message.chat.id} nhập MSSV không hợp lệ: {mssv}")
        bot.reply_to(message, "MSSV không hợp lệ, bạn vui lòng thử lại nha.")
        return
    log("INFO", f"User {message.chat.id} nhập MSSV: {mssv}")
    msg = bot.send_message(message.chat.id, f"✅ Nhận MSSV: `{mssv}`\n🔹 Bước 2: Bạn nhập **Mật khẩu UTH** nhé:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, processPasswordStep, {'mssv': mssv})

def processPasswordStep(message, userData):
    pwd = message.text
    log("ACTION", f"Đang xác thực tài khoản cho User {message.chat.id} (MSSV: {userData['mssv']})")
    bot.send_message(message.chat.id, "⏳ Đang xác thực thông tin, bạn đợi mình xíu nha...")
    isValid, reason = verifyUthCredentials(userData['mssv'], pwd)
    if isValid:
        conn = getDbConn(); cur = conn.cursor()
        cur.execute("INSERT INTO users (chat_id, uth_user, uth_pass) VALUES (%s, %s, %s) ON CONFLICT (chat_id) DO UPDATE SET uth_user = EXCLUDED.uth_user, uth_pass = EXCLUDED.uth_pass", (str(message.chat.id), userData['mssv'], pwd))
        conn.commit(); cur.close(); conn.close()
        log("SUCCESS", f"User {message.chat.id} đã đăng ký thành công")
        bot.send_message(message.chat.id, "🎉 **Đăng ký thành công!** Mình sẽ tự động nhắc lịch cho bạn.", reply_markup=mainMenu(message.chat.id), parse_mode="Markdown")
    else:
        log("ERROR", f"User {message.chat.id} đăng ký thất bại: {reason}")
        bot.send_message(message.chat.id, f"❌ Thất bại: {reason}")


# check lich
def processManual(message, dateStr):
    try:
        datetime.strptime(dateStr, "%Y-%m-%d")
        conn = getDbConn(); cur = conn.cursor()
        cur.execute("SELECT uth_user, uth_pass FROM users WHERE chat_id = %s", (str(message.chat.id),))
        u = cur.fetchone(); cur.close(); conn.close()
        if not u:
            bot.reply_to(message, "Bạn chưa đăng ký tài khoản mà!")
            return
        classes = getClassesByDate(u[0], u[1], dateStr)
        if classes:
            msg = f"📅 **LỊCH HỌC {dateStr}**\n"
            for c in classes:
                tenMon = c['tenMonHoc']
                courseLink = c.get('link') 

                msg += f"\n📘 [{tenMon}]({courseLink})"
                msg += f"\n⏰ {c['tuGio']} - {c['denGio']}"
                msg += f"\n📍 {c['tenPhong']}\n"
                
            msg += f"\n🔗 [Portal UTH](https://portal.ut.edu.vn/)"
            
            bot.send_message(
                message.chat.id, 
                msg, 
                parse_mode="Markdown", 
                reply_markup=mainMenu(message.chat.id),
                disable_web_page_preview=True
            )
        else: 
            bot.send_message(message.chat.id, f"🎉 Ngày {dateStr} bạn được nghỉ nè!", reply_markup=mainMenu(message.chat.id))
    except:
        log("ERROR", f"User {message.chat.id} nhập sai định dạng ngày: {dateStr}")
        bot.send_message(message.chat.id, "Định dạng ngày không đúng rồi (YYYY-MM-DD).", parse_mode="Markdown", reply_markup=mainMenu(message.chat.id))

# feedback
@bot.message_handler(func=lambda m: m.text == "📩 Góp ý/Báo lỗi")
@bot.message_handler(commands=['feedback'])
def handleFeedbackRequest(message):
    log("ACTION", f"Người dùng {message.chat.id} chuẩn bị gửi góp ý.")
    guideText = "😊 **Mình sẵn sàng lắng nghe!** Bạn hãy nhập nội dung góp ý hoặc báo lỗi vào đây nhé."
    msg = bot.send_message(message.chat.id, guideText, parse_mode="Markdown")
    bot.register_next_step_handler(msg, processFeedbackContent)

def processFeedbackContent(message):
    feedbackText = message.text
    chatId = message.chat.id
    if not feedbackText or len(feedbackText) < 5:
        bot.send_message(chatId, "⚠️ Nội dung hơi ngắn, bạn viết kỹ hơn xíu nha.")
        return
    log("FEEDBACK", f"Nhận góp ý từ {chatId}")
    bot.send_message(chatId, "✅ **Gửi thành công!** Cảm ơn bạn.", reply_markup=mainMenu(chatId))
    if adminId:
        bot.send_message(adminId, f"📩 **FEEDBACK MỚI**\n👤 ID: `{chatId}`\n📝 Nội dung: {feedbackText}")

# admin broadcast
@bot.message_handler(commands=['broadcast'])
def adminBroadcastHandler(message):
    if str(message.chat.id) != str(adminId): 
        log("WARN", "User {message.chat.id} try to use broadcast")
        return
    rawInput = message.text.split(maxsplit=1)
    if len(rawInput) < 2:
        bot.reply_to(message, "Nhập nội dung: `/broadcast Nội dung`", parse_mode="Markdown")
        return
    broadcastContent = rawInput[1]
    bot.send_message(message.chat.id, "⏳ Đang gửi thông báo...")
    totalDelivered = broadcastToAllUsers(broadcastContent)
    bot.send_message(message.chat.id, f"✅ Đã gửi cho {totalDelivered} bạn.")

def broadcastToAllUsers(content):
    try:
        conn = getDbConn(); cur = conn.cursor(); cur.execute("SELECT chat_id FROM users")
        userList = cur.fetchall(); cur.close(); conn.close()
    except: return 0
    count = 0
    for user in userList:
        try:
            bot.send_message(user[0], f"📢 **THÔNG BÁO MỚI**\n\n{content}\n\n✨ *Chúc bạn học tốt!*", parse_mode="Markdown")
            count += 1; time.sleep(0.3)
        except: pass
    return count

# NOTE: check menu duoi ban phim
@bot.message_handler(func=lambda m: True)
def menuHandler(message):
    if message.text == "📅 Lịch hôm nay":
        log("QUERY", f"User {message.chat.id} xem lịch hôm nay")
        processManual(message, datetime.now().strftime("%Y-%m-%d"))
    elif message.text == "⏭️ Lịch ngày mai":
        log("QUERY", f"User {message.chat.id} xem lịch ngày mai")
        processManual(message, (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
    elif message.text == "🔍 Check ngày khác":
        log("ACTION", f"User {message.chat.id} muốn check ngày tùy chọn")
        msg = bot.send_message(message.chat.id, "📅 Nhập ngày (YYYY-MM-DD):")
        bot.register_next_step_handler(msg, lambda m: processManual(m, m.text))
    elif str(message.chat.id) == adminId and message.text == "📊 Admin Stats":
        log("ADMIN", f"Admin {adminId} đang xem thống kê")
        conn = getDbConn(); cur = conn.cursor(); cur.execute("SELECT COUNT(*) FROM users")
        count = cur.fetchone()[0]
        bot.send_message(message.chat.id, f"📊 Tổng số người dùng: {count}")
        cur.close(); conn.close()

# --- MAIN ---
if __name__ == "__main__":
    initDb()
    setBotCommands()
    log("SYSTEM", "Bot UTH (camelCase Mode) khởi động!")
    bot.infinity_polling(timeout=60)