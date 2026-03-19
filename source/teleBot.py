# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# teleBot.py

from telebot import types
import portalService
import utils
import teleFunc
import courseService
from datetime import datetime, timedelta
import database as db

adminId = utils.os.getenv("ADMIN_ID")

# ==========================================
# 1. CẤU HÌNH HỆ THỐNG MENU (KEYBOARDS)
# ==========================================

def mainMenu(chatId):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🏛️ Portal Menu", "📚 Course Menu") 
    markup.add("🔑 Đăng ký", "📩 Góp ý/Báo lỗi")
    markup.add("🛠️ Kiểm tra hệ thống")
    if str(chatId) == adminId: 
        markup.add("📊 Admin Stats")
    return markup

def portalSubMenu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🔔 Bật tắt thông báo lịch")
    markup.add("📅 Lịch hôm nay", "⏭️ Lịch ngày mai")
    markup.add("📆 Lịch ngày tùy chọn")
    markup.add("🏠 Quay lại menu chính")
    return markup

def courseSubMenu():
    markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    markup.add("📢 Bật tắt thông báo hằng tuần")
    markup.add("📑 Quét deadline")
    markup.add("🏠 Quay lại menu chính")
    return markup

# ==========================================
# 2. ĐĂNG KÝ CÁC HANDLER
# ==========================================

def setBotCommands(bot):
    try:
        commands = [
            types.BotCommand("start", "🏠 Menu chính"),
            types.BotCommand("login", "🔑 Đăng ký tài khoản"),
            types.BotCommand("feedback", "📩 Góp ý/Báo lỗi"),
            types.BotCommand("help", "❓ Hướng dẫn sử dụng")
        ]
        bot.set_my_commands(commands)
    except: pass

def registerHandlers(bot):
    
    # --- LỆNH COMMAND (/) ---
    @bot.message_handler(commands=['start', 'help'])
    def welcome(message):
        welcomeText = (
            "👋 <b>Chào bạn! Mình là Bot nhắc lịch UTH.</b>\n\n"
            "Mình sẽ đồng hành cùng bạn trong việc theo dõi lịch học Portal và các deadline từ hệ thống Courses một cách tự động.\n\n"
            "📢 <b>Tham gia nhóm hỗ trợ và nhận cập nhật mới nhất tại:</b>\n"
            "👉 https://t.me/uth_notifier_group\n\n"
            "Bạn hãy chọn các chức năng ở menu bên dưới để bắt đầu trải nghiệm nhé! 😊"
        )
        bot.send_message(message.chat.id, welcomeText, parse_mode="HTML", reply_markup=mainMenu(message.chat.id))

    @bot.message_handler(commands=['broadcast'])
    def handleAdminBroadcast(message):
        if str(message.chat.id) != adminId: return
        rawInput = message.text.split(maxsplit=1)
        if len(rawInput) < 2:
            bot.reply_to(message, "Vui lòng nhập nội dung: <code>/broadcast Nội dung</code>", parse_mode="HTML")
            return
        bot.send_message(message.chat.id, "⏳ Đang gửi thông báo đến mọi người...")
        total = teleFunc.broadcastToAllUsers(bot, rawInput[1])
        bot.send_message(message.chat.id, f"✅ Đã gửi thông báo thành công cho {total} người dùng.")

    # --- ĐIỀU HƯỚNG MENU (FOLDERS) ---
    @bot.message_handler(func=lambda m: m.text == "🏛️ Portal Menu")
    def openPortal(message):
        bot.send_message(message.chat.id, "🏛️ <b>HỆ THỐNG PORTAL</b>", parse_mode="HTML", reply_markup=portalSubMenu())

    @bot.message_handler(func=lambda m: m.text == "📚 Course Menu")
    def openCourse(message):
        bot.send_message(message.chat.id, "📚 <b>HỆ THỐNG COURSES</b>", parse_mode="HTML", reply_markup=courseSubMenu())

    @bot.message_handler(func=lambda m: m.text == "🏠 Quay lại menu chính")
    def backToMain(message):
        bot.send_message(message.chat.id, "🏠 Đã quay lại Menu chính.", reply_markup=mainMenu(message.chat.id))

    # --- CHỨC NĂNG PORTAL ---
    @bot.message_handler(func=lambda m: m.text == "📅 Lịch hôm nay")
    def handleToday(message):
        today = datetime.now().strftime("%Y-%m-%d")
        bot.send_message(message.chat.id, portalService.formatCalendarMessage(message.chat.id, today), parse_mode="HTML", disable_web_page_preview=True)

    @bot.message_handler(func=lambda m: m.text == "⏭️ Lịch ngày mai")
    def handleTomorrow(message):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        bot.send_message(message.chat.id, portalService.formatCalendarMessage(message.chat.id, tomorrow), parse_mode="HTML", disable_web_page_preview=True)

    @bot.message_handler(func=lambda m: m.text == "📆 Lịch ngày tùy chọn")
    def handleCustomDateRequest(message):
        msg = bot.send_message(message.chat.id, "📅 Bạn vui lòng nhập ngày muốn xem (Định dạng: <code>YYYY-MM-DD</code>):", parse_mode="HTML")
        bot.register_next_step_handler(msg, processCustomDate, bot)

    @bot.message_handler(func=lambda m: m.text == "🔔 Bật tắt thông báo lịch")
    def handleTogglePortal(message):
        _, resMsg = teleFunc.handleToggleNotify(message.chat.id)
        bot.send_message(message.chat.id, resMsg, parse_mode="HTML")

    # --- CHỨC NĂNG COURSE ---
    @bot.message_handler(func=lambda m: m.text == "📑 Quét deadline")
    def handleDeadlineScan(message):
        bot.send_message(message.chat.id, "🔍 Đang kết nối với hệ thống Courses để kiểm tra bài tập giúp bạn...")
        courseService.scanAllDeadlines(bot, message.chat.id, isManual=True)

    @bot.message_handler(func=lambda m: m.text == "📢 Bật tắt thông báo hằng tuần")
    def handleToggleCourse(message):
        chatId = message.chat.id
        _, resMsg = teleFunc.handleToggleDeadlineNotify(chatId)
        bot.send_message(chatId, resMsg, parse_mode="HTML")

    # --- CÁC CHỨC NĂNG CHUNG ---
    @bot.message_handler(commands=['login'])
    @bot.message_handler(func=lambda m: m.text == "🔑 Đăng ký")
    def handleRegister(message):
        msg = bot.send_message(message.chat.id, "🔑 <b>Bắt đầu đăng ký:</b>\n\nBạn vui lòng nhập <b>MSSV</b> của mình nhé:", parse_mode="HTML")
        bot.register_next_step_handler(msg, processMssvStep, bot)

    @bot.message_handler(func=lambda m: m.text == "📩 Góp ý/Báo lỗi")
    def handleFeedbackRequest(message):
        msg = bot.send_message(message.chat.id, "😊 Bạn có thể nhập nội dung góp ý hoặc báo lỗi tại đây, mình sẽ gửi đến Admin giúp bạn:")
        bot.register_next_step_handler(msg, processFeedback, bot)

    @bot.message_handler(func=lambda m: m.text == "🛠️ Kiểm tra hệ thống")
    def handleStatus(message):
        msgWait = bot.send_message(message.chat.id, "⏳ Bạn đợi mình xíu nhé, mình đang kiểm tra kết nối...")
        teleFunc.getSystemStatus(bot, message.chat.id, msgWait.message_id)

    @bot.message_handler(func=lambda m: m.text == "📊 Admin Stats" and str(m.chat.id) == adminId)
    def handleAdminStats(message):
        bot.send_message(message.chat.id, teleFunc.getAdminStats(adminId), parse_mode="HTML")

    # --- CALLBACK NÚT BẤM (DEADLINE) ---
    @bot.callback_query_handler(func=lambda call: call.data.startswith('done_'))
    def onMarkDone(call):
        handleMarkDone(bot, call)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('undone_'))
    def onMarkUndone(call):
        handleMarkUndone(bot, call)

    # --- NHẮC LỆNH SAI ---
    @bot.message_handler(func=lambda m: True)
    def handleUnknown(message):
        bot.reply_to(message, "⚠️ Lệnh này mình chưa hiểu, bạn vui lòng sử dụng các nút ở menu nhé!", reply_markup=mainMenu(message.chat.id))

# ==========================================
# 3. LOGIC XỬ LÝ NỘI BỘ
# ==========================================

def processMssvStep(message, bot):
    mssv = message.text
    if not mssv or len(mssv) < 5:
        bot.reply_to(message, "Mã số sinh viên có vẻ chưa đúng, bạn vui lòng nhập lại nhé.")
        return
    msg = bot.send_message(message.chat.id, f"✅ Đã nhận MSSV: <code>{mssv}</code>\n\nTiếp theo, bạn hãy nhập <b>Mật khẩu Portal</b> nha:", parse_mode="HTML")
    bot.register_next_step_handler(msg, processPasswordStep, bot, mssv)

def processPasswordStep(message, bot, mssv):
    pwd = message.text
    bot.send_message(message.chat.id, "⏳ Đang xác thực thông tin, bạn đợi mình một lát nhé...")
    success, resultMsg = portalService.verifyAndSaveUser(message.chat.id, mssv, pwd)
    if success:
        resultMsg += "\n\n✅ Tuyệt vời! Bạn đã đăng ký thành công. Bây giờ bạn có thể xem lịch và deadline rồi đó."
    bot.send_message(message.chat.id, resultMsg, parse_mode="HTML", reply_markup=mainMenu(message.chat.id))

def processCustomDate(message, bot):
    try:
        dateStr = message.text
        datetime.strptime(dateStr, "%Y-%m-%d")
        bot.send_message(message.chat.id, portalService.formatCalendarMessage(message.chat.id, dateStr), parse_mode="HTML", disable_web_page_preview=True)
    except:
        bot.send_message(message.chat.id, "❌ Định dạng ngày chưa đúng (Bạn hãy nhập YYYY-MM-DD, ví dụ: 2026-03-20).")

def processFeedback(message, bot):
    teleFunc.handleSendFeedback(bot, message, adminId)

def handleMarkDone(bot, call):
    chatId = call.message.chat.id
    taskId = call.data.split('_')[1]
    if db.markTaskCompleted(chatId, taskId):
        new_text = call.message.text.replace("❌ Chưa hoàn thành", "✅ Đã hoàn thành")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Đánh dấu chưa xong", callback_data=f"undone_{taskId}"))
        try:
            bot.edit_message_text(new_text, chatId, call.message.message_id, parse_mode="HTML", reply_markup=markup)
        except: pass
        bot.answer_callback_query(call.id, "✅ Tuyệt vời! Đã ghi nhận bạn hoàn thành bài tập.")

def handleMarkUndone(bot, call):
    chatId = call.message.chat.id
    taskId = call.data.split('_')[1]
    if db.unmarkTaskCompleted(chatId, taskId):
        new_text = call.message.text.replace("✅ Đã hoàn thành", "❌ Chưa hoàn thành")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Đánh dấu hoàn thành", callback_data=f"done_{taskId}"))
        try:
            bot.edit_message_text(new_text, chatId, call.message.message_id, parse_mode="HTML", reply_markup=markup)
        except: pass
        bot.answer_callback_query(call.id, "❌ Đã chuyển trạng thái về chưa hoàn thành.")