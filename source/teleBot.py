# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# teleBot.py

from telebot import types
import portalService
import utils
import teleFunc
from datetime import datetime, timedelta


adminId = utils.os.getenv("ADMIN_ID")

def setBotCommands(bot):
    try:
        commands = [
            types.BotCommand("start", "🏠 Menu chính"),
            types.BotCommand("login", "🔑 Đăng ký tài khoản"),
            types.BotCommand("feedback", "📩 Góp ý"),
            types.BotCommand("help", "❓ Hướng dẫn")
        ]
        bot.set_my_commands(commands)
    except: pass


#NOTE: chi lenh /
def registerHandlers(bot):
    @bot.message_handler(commands=['start', 'help'])
    def welcome(message):
        utils.log("INFO", f"User {message.chat.id} vừa nhấn {message.text}")
        
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

    @bot.message_handler(commands=['broadcast'])
    def handleAdminBroadcast(message):
        if str(message.chat.id) != adminId: return
        rawInput = message.text.split(maxsplit=1)
        if len(rawInput) < 2:
            bot.reply_to(message, "Nhập nội dung: <code>/broadcast Nội dung</code>", parse_mode="HTML")
            return
        bot.send_message(message.chat.id, "⏳ Đang gửi thông báo...")
        total = teleFunc.broadcastToAllUsers(bot, rawInput[1])
        bot.send_message(message.chat.id, f"✅ Đã gửi cho {total} bạn.")

#NOTE: main menu
    @bot.message_handler(commands=['login'])
    @bot.message_handler(func=lambda m: m.text == "🔑 Đăng ký tài khoản" or m.text == "/login")
    def startLogin(message):
        utils.log("ACTION", f"User {message.chat.id} bắt đầu quy trình đăng ký")
        msg = bot.send_message(message.chat.id, "🔹 Bước 1: Bạn vui lòng nhập <b>MSSV</b> của mình nhé:", parse_mode="HTML")
        bot.register_next_step_handler(msg, processMssvStep)

    def processMssvStep(message):
        mssv = message.text
        if not mssv or len(mssv) < 5:
            utils.log("WARN", f"User {message.chat.id} nhập MSSV không hợp lệ: {mssv}")
            bot.reply_to(message, "MSSV không hợp lệ, bạn vui lòng thử lại nha.")
            return
        utils.log("INFO", f"User {message.chat.id} nhập MSSV: {mssv}")
        msg = bot.send_message(message.chat.id, f"✅ Nhận MSSV: <code>{mssv}</code>\n🔹 Bước 2: Bạn nhập <b>Mật khẩu UTH</b> nhé:", parse_mode="HTML")
        bot.register_next_step_handler(msg, processPasswordStep, bot, mssv)
        
    def processPasswordStep(message, bot, mssv):
        pwd = message.text
        utils.log("ACTION", f"Đang xác thực tài khoản cho User {message.chat.id} (MSSV: {mssv})")
        bot.send_message(message.chat.id, "⏳ Đang xác thực thông tin, bạn đợi mình xíu nha...")
        success, resultMsg = portalService.verifyAndSaveUser(message.chat.id, mssv, pwd)
        bot.send_message(message.chat.id, resultMsg, parse_mode="HTML", reply_markup=mainMenu(message.chat.id))


# gop y
    @bot.message_handler(func=lambda m: m.text == "📩 Góp ý/Báo lỗi")
    def startFeedback(message):
        msg = bot.send_message(message.chat.id, "😊 Nhập nội dung góp ý của bạn:")
        bot.register_next_step_handler(msg, processFeedback, bot)

    def processFeedback(message, bot):
        if len(message.text) < 5:
            bot.send_message(message.chat.id, "⚠️ Nội dung quá ngắn.")
            return
        bot.send_message(message.chat.id, "✅ Cảm ơn bạn đã góp ý!")
        if adminId:
            bot.send_message(adminId, f"📩 <b>FEEDBACK</b>\n👤 ID: <code>{message.chat.id}</code>\n📝: {message.text}", parse_mode="HTML")

# admin stats
    @bot.message_handler(func=lambda m: m.text == "📊 Admin Stats" and str(m.chat.id) == adminId)
    def handleStats(message):
        bot.send_message(message.chat.id, teleFunc.getAdminStats(adminId), parse_mode="HTML")

# check lich
    @bot.message_handler(func=lambda m: m.text == "📅 Lịch hôm nay")
    def handleToday(message):
        utils.log("QUERY", f"User {message.chat.id} xem lịch hôm nay")
        chatId = message.chat.id
        today = datetime.now().strftime("%Y-%m-%d")
        bot.send_message(chatId, portalService.formatCalendarMessage(chatId, today), parse_mode="HTML", disable_web_page_preview=True)

    @bot.message_handler(func=lambda m: m.text == "⏭️ Lịch ngày mai")
    def handleTomorrow(message):
        utils.log("QUERY", f"User {message.chat.id} xem lịch ngày mai")
        chatId = message.chat.id
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        bot.send_message(chatId, portalService.formatCalendarMessage(chatId, tomorrow), parse_mode="HTML", disable_web_page_preview=True)

# check ngay khac
    @bot.message_handler(func=lambda m: m.text == "🔍 Check ngày khác")
    def askCustomDate(message):
        utils.log("ACTION", f"User {message.chat.id} muốn check ngày tùy chọn")
        msg = bot.send_message(message.chat.id, "📅 Nhập ngày (<code>YYYY-MM-DD</code>):", parse_mode="HTML")
        bot.register_next_step_handler(msg, processCustomDate, bot)

    def processCustomDate(message, bot):
        dateStr = message.text
        try:
            datetime.strptime(dateStr, "%Y-%m-%d")
            bot.send_message(message.chat.id, portalService.formatCalendarMessage(message.chat.id, dateStr), parse_mode="HTML", disable_web_page_preview=True)
        except:
            bot.send_message(message.chat.id, "❌ Định dạng ngày sai (YYYY-MM-DD).")


#NOTE: setting menu
    @bot.message_handler(func=lambda m: m.text == "⚙️ Cài đặt")
    def openSettings(message):
        bot.send_message(message.chat.id, "⚙️ <b>TRÌNH CÀI ĐẶT</b>", parse_mode="HTML", reply_markup=settingsMenu(message.chat.id))

    @bot.message_handler(func=lambda m: m.text in ["🔕 Tắt nhắc lịch", "🔔 Bật nhắc lịch"])
    def handleToggle(message):
        _, resMsg = teleFunc.handleToggleNotify(message.chat.id)
        bot.send_message(message.chat.id, resMsg, parse_mode="HTML", reply_markup=settingsMenu(message.chat.id))

    @bot.message_handler(func=lambda m: m.text == "🔍 Kiểm tra trạng thái")
    def showStatus(message):
        utils.log("ACTION", f"User {message.chat.id} đang check status")
        msgWait = bot.send_message(message.chat.id, "⏳ Đợi mình xíu nhé, mình đang kiểm tra hệ thống giúp bạn...")
        teleFunc.getSystemStatus(bot, message.chat.id, msgWait.message_id)

    @bot.message_handler(func=lambda m: m.text == "🔙 Quay lại menu chính")
    def handleBackMain(message):
        bot.send_message(message.chat.id, "🔙 Đã quay lại Menu chính.", reply_markup=mainMenu(message.chat.id))


#NOTE: nhac lenh k hop le
    @bot.message_handler(func=lambda m: True)
    def handleUnknown(message):
        bot.reply_to(message, "⚠️ Lệnh không hợp lệ, mày vui lòng chọn các nút ở Menu bên dưới nhé!", reply_markup=mainMenu(message.chat.id))

def mainMenu(chatId):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("📅 Lịch hôm nay", "⏭️ Lịch ngày mai")
    markup.add("🔑 Đăng ký tài khoản", "🔍 Check ngày khác")
    markup.add("📩 Góp ý/Báo lỗi", "⚙️ Cài đặt")
    if str(chatId) == adminId: markup.add("📊 Admin Stats")
    return markup

def settingsMenu(chatId):
    import database as db
    conn = db.getDbConn(); cur = conn.cursor()
    cur.execute("SELECT notify_enabled FROM users WHERE chat_id = %s", (str(chatId),))
    res = cur.fetchone(); cur.close(); conn.close()
    status = res[0] if res else True
    toggleText = "🔕 Tắt nhắc lịch" if status else "🔔 Bật nhắc lịch"
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(toggleText, "🔍 Kiểm tra trạng thái")
    markup.add("🔙 Quay lại menu chính")
    return markup