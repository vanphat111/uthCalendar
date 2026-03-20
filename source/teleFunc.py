# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# teleFunc.py

import database as db
import portalService
import utils
import time

def getSystemStatus(bot, chatId, msgWaitId):
    u = portalService.getUserData(chatId)
    if not u:
        bot.edit_message_text("❌ Hình như bạn chưa đăng ký tài khoản. Hãy đăng ký để mình hỗ trợ tốt hơn nhé!", chatId, msgWaitId)
        return

    try:
        rawUser = utils.decryptData(u[0])
        rawPass = utils.decryptData(u[1])

        startTime = time.time()
        isValid, reason = portalService.verifyUthCredentials(rawUser, rawPass)
        latency = round((time.time() - startTime) * 1000)

        apiStatus = "✅ Hoạt động tốt" if isValid else f"❌ Có lỗi ({reason})"
        credStatus = "✅ Chính xác" if isValid else "❌ Mật khẩu chưa đúng"
        notifyStatus = "🔔 Đang bật" if u[2] else "🔕 Đang tắt"
        
        statusMsg = (
            "<b>📊 TRẠNG THÁI HỆ THỐNG CỦA BẠN</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🌐 <b>Kết nối Portal:</b> {apiStatus}\n"
            f"🔑 <b>Tài khoản UTH:</b> {credStatus}\n"
            f"📢 <b>Nhắc lịch tự động:</b> {notifyStatus}\n"
            f"⚡ <b>Độ trễ hệ thống:</b> <code>{latency}ms</code>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<i>Nếu thông tin chưa chính xác, bạn hãy chọn 'Đăng ký' để cập nhật mật khẩu mới nha!</i>"
        )
        
        bot.edit_message_text(statusMsg, chatId, msgWaitId, parse_mode="HTML")

    except Exception as e:
        utils.log("ERROR", f"Lỗi check status: {e}")
        bot.edit_message_text("⚠️ Có chút trục trặc nhỏ, mình chưa kiểm tra được. Bạn thử lại sau nhé!", chatId, msgWaitId)

def broadcastToAllUsers(bot, content):
    try:
        conn = db.getDbConn(); cur = conn.cursor()
        cur.execute("SELECT chat_id FROM users")
        userList = cur.fetchall(); cur.close(); conn.close()
    except: return 0
    count = 0
    for user in userList:
        try:
            bot.send_message(user[0], f"📢 <b>THÔNG BÁO MỚI</b>\n\n{content}\n\n<i>Chúc bạn học tốt!</i>", parse_mode="HTML")
            count += 1
            time.sleep(0.3)
        except: pass
    return count

def handleToggleNotify(chatId):
    u = db.getUserCredentials(chatId)
    if not u: return None, "❌ Bạn chưa đăng ký tài khoản."
    newStatus = not u[4]
    portalService.updateNotifyStatus(chatId, newStatus)
    return newStatus, f"✅ Đã <b>{'BẬT' if newStatus else 'TẮT'}</b> nhắc lịch tự động!"

def getAdminStats(adminId):
    try:
        utils.log("ADMIN", f"Admin {adminId} đang xem thống kê")
        conn = db.getDbConn(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        count = cur.fetchone()[0]
        cur.close(); conn.close()
        return f"📊 Tổng số người dùng: <b>{count}</b>"
    except: return "⚠️ Không thể lấy thống kê."

def handleToggleDeadlineNotify(chatId):
    u = db.getUserCredentials(chatId)
    if not u: return None, "❌ Bạn chưa đăng ký tài khoản."

    currentStatus = db.getDeadlineStatus(chatId)
    newStatus = not currentStatus
    
    if db.updateDeadlineStatus(chatId, newStatus):
        statusStr = "BẬT" if newStatus else "TẮT"
        return newStatus, f"✅ Đã <b>{statusStr}</b> thông báo deadline hằng tuần!"
    
    return currentStatus, "❌ Có lỗi xảy ra khi cập nhật, bạn vui lòng thử lại sau nha."

def handleSendFeedback(bot, message, adminId):
    if not message.text or len(message.text) < 5:
        bot.send_message(message.chat.id, "⚠️ Nội dung góp ý hơi ngắn, bạn vui lòng mô tả chi tiết hơn một chút để mình hỗ trợ nhé.")
        return False

    user = message.from_user
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Người dùng"
    username_display = f" (@{user.username})" if user.username else ""
    user_link = f"tg://user?id={user.id}" # Link nhấn vào là mở Profile

    bot.send_message(message.chat.id, "✅ Cảm ơn bạn rất nhiều! Góp ý của bạn đã được mình gửi đến Admin rồi nha.")

    if adminId:
        feedback_msg = (
            "📩 <b>CÓ GÓP Ý/BÁO LỖI MỚI!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Người gửi:</b> <a href='{user_link}'>{full_name}</a>{username_display}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"📝 <b>Nội dung:</b>\n<i>{message.text}</i>\n"
            "━━━━━━━━━━━━━━━━━━\n"
        )
        bot.send_message(adminId, feedback_msg, parse_mode="HTML")
    return True