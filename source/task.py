# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# tasks.py

import os
import time
from celeryApp import app
from telebot import TeleBot
import courseService
import portalService
from utils import log
import teleFunc

# Khởi tạo Bot để gửi tin nhắn
bot = TeleBot(os.getenv("TELE_TOKEN"))

def sendWorkerCheckIn(_self, _chatId):
    workerName = _self.request.hostname

    try:
        bot.send_message(_chatId, f"🤖 <b>[{workerName}]</b> Đã tiếp nhận lệnh của bạn. Đang xử lý... ⏳", parse_mode="HTML")
        log("INFO", f"Đang xử lí lệnh cho user: {_chatId}")
    except Exception as e:
        log("ERROR", f"Không thể gửi báo danh: {e}")

# ==========================================
# 1. TASK ƯU TIÊN CAO (Dành cho User gọi lệnh)
# ==========================================

@app.task(bind=True, name='tasks.portalTask', queue='high_priority')
def portalTask(self, chatId, dateStr):
    sendWorkerCheckIn(self, chatId)
    try:
        msg = portalService.formatCalendarMessage(chatId, dateStr)
        if msg:
            bot.send_message(chatId, msg, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        log("ERROR", f"Lỗi Portal Task cho {chatId}: {e}")

@app.task(bind=True, name='tasks.deadlineTask', queue='high_priority')
def deadlineTask(self, chatId):
    sendWorkerCheckIn(self, chatId)
    try:
        courseService.scanAllDeadlines(bot, chatId, isManual=True)
    except Exception as e:
        log("ERROR", f"Lỗi Deadline Task cho {chatId}: {e}")

@app.task(bind=True, name='tasks.registrationTask')
def registrationTask(self, chatId, mssv, password):
    sendWorkerCheckIn(self, chatId)
    success, resultMsg = portalService.verifyAndSaveUser(chatId, mssv, password)
    if success:
        resultMsg += "\n\n✅ Tuyệt vời! Bạn đã đăng ký thành công. Bây giờ bạn có thể xem lịch và deadline rồi đó."
    bot.send_message(chatId, resultMsg, parse_mode="HTML")

@app.task(bind=True, name='tasks.systemStatusTask')
def systemStatusTask(self, chatId, msgWaitId):
    sendWorkerCheckIn(self, chatId)
    teleFunc.getSystemStatus(bot, chatId, msgWaitId)

@app.task(bind=True, name='tasks.feedbackTask')
def feedbackTask(self, chatId, text, adminId):
    import teleFunc
    teleFunc.handleSendFeedback(bot, text, chatId, adminId)


# ==========================================
# 2. TASK ƯU TIÊN THẤP (Dành cho Quét định kỳ)
# ==========================================

@app.task(
    bind=True,
    name='tasks.periodicCourseTask', 
    queue='low_priority', 
    rate_limit='1/s', # Khống chế 1 giây chỉ quét 1 ông để né IP trường
    autoretry_for=(Exception,), 
    retry_kwargs={'max_retries': 3, 'countdown': 60} # Lỗi thì thử lại sau 60s
)
def periodicCourseTask(self, chatId):
    sendWorkerCheckIn(self, chatId)

    log("WORKER", f"Đang quét deadline cho user: {chatId}")
    courseService.scanAllDeadlines(bot, chatId, isManual=False)


@app.task(
    bind=True,
    name='tasks.periodicPortalTask', 
    queue='low_priority', 
    rate_limit='1/s'
)
def periodicPortalTask(self, chatId, dateStr):
    sendWorkerCheckIn(self, chatId)

    log("WORKER", f"Đang quét lịch cho user: {chatId}")
    msg = portalService.formatCalendarMessage(chatId, dateStr, isAuto=True)
    if msg:
        bot.send_message(chatId, msg, parse_mode="HTML", disable_web_page_preview=True)