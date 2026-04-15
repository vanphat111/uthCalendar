# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# tasks.py

import os
from datetime import datetime
from celeryApp import app
from telebot import TeleBot
import courseService
import portalService
from utils import log
import teleFunc
import json
import redisManager
import utils

# Khởi tạo Bot để gửi tin nhắn
bot = TeleBot(os.getenv("TELE_TOKEN"))
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

def sendWorkerCheckIn(_self, _chatId):
    workerName = _self.request.hostname
    log("INFO", f"Worker {workerName} đang xử lí lệnh cho user: {_chatId}")

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
def systemStatusTask(self, chatId):
    sendWorkerCheckIn(self, chatId)
    teleFunc.getSystemStatus(bot, chatId)

@app.task(bind=True, name='tasks.feedbackTask')
def feedbackTask(self, chatId, text, adminId):
    import teleFunc
    teleFunc.handleSendFeedback(bot, text, chatId, adminId)

@app.task(bind=True, name='tasks.customDeadlineTask', queue='high_priority')
def customDeadlineTask(self, chatId, startDateStr, numDays):
    sendWorkerCheckIn(self, chatId)
    startDate = datetime.strptime(startDateStr, "%d/%m/%Y")
    courseService.scanAllDeadlines(bot, chatId, isManual=True, startDate=startDate, numDays=numDays)


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

@app.task(
    name='tasks.updateWeatherTask',
    queue='low_priority'
)
def updateWeatherTask():
    if not WEATHER_API_KEY:
        log("ERROR", "WEATHER_API_KEY chưa được cấu hình!")
        return

    campuses = {
        "CS1": "10.8023,106.7147",
        "CS2": "10.7934,106.7320",
        "CS3": "10.8524,106.6361"
    }

    for code, coords in campuses.items():
        try:
            url = f"https://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={coords}&days=2&lang=vi"
            response = utils.safeRequest("GET", url)
            
            if response and response.status_code == 200:
                data = response.json() 
                
                forecast_data = []
                for day in data['forecast']['forecastday']:
                    forecast_data.extend(day['hour'])

                redisManager.redisClient.set(f"forecast:{code}", json.dumps(forecast_data), ex=3600)
                log("SUCCESS", f"Đã lưu dự báo 48h cho {code}")
            else:
                log("ERROR", f"Không thể lấy weather cho {code}, Code: {response.status_code if response else 'None'}")
                
        except Exception as e:
            log("ERROR", f"Lỗi fetch forecast {code}: {e}")