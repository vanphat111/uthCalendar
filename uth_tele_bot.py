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

dbConfig = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS")
}

teleToken = os.getenv("TELE_TOKEN")
adminId = os.getenv("ADMIN_ID")

def getNow(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def log(level, message): print(f"[{getNow()}] [{level}] {message}", flush=True)

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

def mainMenu(chatId):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("📅 Lịch hôm nay", "⏭️ Lịch ngày mai")
    markup.add("🔑 Đăng ký tài khoản", "🔍 Check ngày khác")
    markup.add("📩 Góp ý/Báo lỗi")
    if str(chatId) == adminId: markup.add("📊 Admin Stats")
    return markup

def setBotCommands():
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

@bot.message_handler(commands=['start', 'help'])
def welcome(message):
    log("INFO", f"User {message.chat.id} vừa nhấn {message.text}")
    
    welcomeText = (
        "👋 <b>Chào bạn! Mình là Bot nhắc lịch UTH.</b>\n\n"
        "Mình sẽ giúp bạn theo dõi lịch học và lấy link phòng học Online một cách nhanh chóng nhất.\n\n"
        "📢 <b>Tham gia nhóm hỗ trợ và cập nhật tin tức tại:</b>\n"
        "👉 https://t.me/UTH_Calendar\n\n"
        "Bạn hãy chọn các nút ở menu bên dưới để bắt đầu sử dụng nhé!"
    )
    
    bot.reply_to(
        message, 
        welcomeText, 
        parse_mode="HTML", 
        reply_markup=mainMenu(message.chat.id),
        disable_web_page_preview=False
    )

@bot.message_handler(commands=['login'])
@bot.message_handler(func=lambda m: m.text == "🔑 Đăng ký tài khoản")
def startLogin(message):
    log("ACTION", f"User {message.chat.id} bắt đầu quy trình đăng ký")
    msg = bot.send_message(message.chat.id, "🔹 Bước 1: Bạn vui lòng nhập <b>MSSV</b> của mình nhé:", parse_mode="HTML")
    bot.register_next_step_handler(msg, processMssvStep)

def processMssvStep(message):
    mssv = message.text
    if not mssv or len(mssv) < 5:
        log("WARN", f"User {message.chat.id} nhập MSSV không hợp lệ: {mssv}")
        bot.reply_to(message, "MSSV không hợp lệ, bạn vui lòng thử lại nha.")
        return
    log("INFO", f"User {message.chat.id} nhập MSSV: {mssv}")
    msg = bot.send_message(message.chat.id, f"✅ Nhận MSSV: <code>{mssv}</code>\n🔹 Bước 2: Bạn nhập <b>Mật khẩu UTH</b> nhé:", parse_mode="HTML")
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
        bot.send_message(message.chat.id, "🎉 <b>Đăng ký thành công!</b> Mình sẽ tự động nhắc lịch cho bạn.", reply_markup=mainMenu(message.chat.id), parse_mode="HTML")
    else:
        log("ERROR", f"User {message.chat.id} đăng ký thất bại: {reason}")
        bot.send_message(message.chat.id, f"❌ Thất bại: {reason}")

def processManual(chatId, dateStr, isAuto=False):
    try:
        datetime.strptime(dateStr, "%Y-%m-%d")
        
        conn = getDbConn()
        cur = conn.cursor()
        cur.execute("SELECT uth_user, uth_pass FROM users WHERE chat_id = %s", (str(chatId),))
        u = cur.fetchone()
        cur.close()
        conn.close()
        
        if not u:
            if not isAuto:
                bot.send_message(chatId, "Bạn chưa đăng ký tài khoản!", reply_markup=mainMenu(chatId))
            return

        classes = getClassesByDate(u[0], u[1], dateStr)
        if classes:
            header = f"🔔 <b>NHẮC LỊCH TỰ ĐỘNG ({dateStr})</b>\n" if isAuto else f"📅 <b>LỊCH HỌC {dateStr}</b>\n"
            msg = header + "━━━━━━━━━━━━━━━━━━\n"
            
            for c in classes:
                courseLink = c.get('link', 'https://courses.ut.edu.vn/')
                msg += f"\n📘 <a href='{courseLink}'>{c['tenMonHoc']}</a>"
                msg += f"\n⏰ {c['tuGio']} - {c['denGio']}"
                msg += f"\n📍 {c['tenPhong']}\n"
            
            msg += f"\n🔗 <a href='https://portal.ut.edu.vn/'>Portal UTH</a>"
            
            bot.send_message(
                chatId, 
                msg, 
                parse_mode="HTML", 
                reply_markup=mainMenu(chatId),
                disable_web_page_preview=True
            )
        else:
            if not isAuto:
                bot.send_message(chatId, f"🎉 Ngày {dateStr} bạn được nghỉ nè!", reply_markup=mainMenu(chatId))
                
    except Exception as e:
        log("ERROR", f"Lỗi processManual cho {chatId}: {e}")
        if not isAuto:
            bot.send_message(chatId, "Định dạng ngày không đúng (YYYY-MM-DD).", reply_markup=mainMenu(chatId))

def autoCheckAndNotify():
    log("AUTO", "Bắt đầu quy trình quét lịch tự động cho tất cả user...")
    today = datetime.now().strftime("%Y-%m-%d")
    
    try:
        conn = getDbConn()
        cur = conn.cursor()
        cur.execute("SELECT chat_id FROM users")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        successCount = 0
        for r in rows:
            processManual(r[0], today, isAuto=True)
            successCount += 1
            time.sleep(0.3)
            
        log("SUCCESS", f"Đã hoàn thành nhắc lịch tự động cho {successCount} người.")
    except Exception as e:
        log("DATABASE_ERROR", f"Lỗi khi lấy danh sách user: {e}")

def runScheduler():
    schedule.every().day.at("05:00").do(autoCheckAndNotify)
    schedule.every().day.at("12:00").do(autoCheckAndNotify)
    schedule.every().day.at("17:00").do(autoCheckAndNotify)
    
    log("SYSTEM", "Trình lập lịch đã được thiết lập (05:00, 12:00, 17:00).\n")
    while True:
        schedule.run_pending()
        time.sleep(30)

@bot.message_handler(func=lambda m: m.text == "📩 Góp ý/Báo lỗi")
@bot.message_handler(commands=['feedback'])
def handleFeedbackRequest(message):
    log("ACTION", f"Người dùng {message.chat.id} chuẩn bị gửi góp ý.")
    guideText = "😊 <b>Mình sẵn sàng lắng nghe!</b> Bạn hãy nhập nội dung góp ý hoặc báo lỗi vào đây nhé."
    msg = bot.send_message(message.chat.id, guideText, parse_mode="HTML")
    bot.register_next_step_handler(msg, processFeedbackContent)

def processFeedbackContent(message):
    feedbackText = message.text
    chatId = message.chat.id
    if not feedbackText or len(feedbackText) < 5:
        bot.send_message(chatId, "⚠️ Nội dung hơi ngắn, bạn viết kỹ hơn xíu nha.")
        return
    log("FEEDBACK", f"Nhận góp ý từ {chatId}")
    bot.send_message(chatId, "✅ <b>Gửi thành công!</b> Cảm ơn bạn.", reply_markup=mainMenu(chatId), parse_mode="HTML")
    if adminId:
        bot.send_message(adminId, f"📩 <b>FEEDBACK MỚI</b>\n👤 ID: <code>{chatId}</code>\n📝 Nội dung: {feedbackText}", parse_mode="HTML")

@bot.message_handler(commands=['broadcast'])
def adminBroadcastHandler(message):
    if str(message.chat.id) != str(adminId): 
        log("WARN", f"User {message.chat.id} try to use broadcast")
        return
    rawInput = message.text.split(maxsplit=1)
    if len(rawInput) < 2:
        bot.reply_to(message, "Nhập nội dung: <code>/broadcast Nội dung</code>", parse_mode="HTML")
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
            bot.send_message(user[0], f"📢 <b>THÔNG BÁO MỚI</b>\n\n{content}\n\n<i>Chúc bạn học tốt!</i>", parse_mode="HTML")
            count += 1; time.sleep(0.3)
        except: pass
    return count

@bot.message_handler(func=lambda m: True)
def menuHandler(message):
    if message.text == "📅 Lịch hôm nay":
        log("QUERY", f"User {message.chat.id} xem lịch hôm nay")
        processManual(message.chat.id, datetime.now().strftime("%Y-%m-%d"))
    elif message.text == "⏭️ Lịch ngày mai":
        log("QUERY", f"User {message.chat.id} xem lịch ngày mai")
        processManual(message.chat.id, (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
    elif message.text == "🔍 Check ngày khác":
        log("ACTION", f"User {message.chat.id} muốn check ngày tùy chọn")
        msg = bot.send_message(message.chat.id, "📅 Nhập ngày (<code>YYYY-MM-DD</code>):", parse_mode="HTML")
        bot.register_next_step_handler(msg, lambda m: processManual(m.chat.id, m.text))
    elif str(message.chat.id) == adminId and message.text == "📊 Admin Stats":
        log("ADMIN", f"Admin {adminId} đang xem thống kê")
        conn = getDbConn(); cur = conn.cursor(); cur.execute("SELECT COUNT(*) FROM users")
        count = cur.fetchone()[0]
        bot.send_message(message.chat.id, f"📊 Tổng số người dùng: <b>{count}</b>", parse_mode="HTML")
        cur.close(); conn.close()

if __name__ == "__main__":
    initDb()
    setBotCommands()
    threading.Thread(target=runScheduler, daemon=True).start()
    log("SYSTEM", "Bot UTH (camelCase Mode) khởi động!")
    bot.infinity_polling(timeout=60)