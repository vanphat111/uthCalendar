# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# utils.py

import os
from datetime import datetime
from urllib.parse import urlparse
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import threading
import json
import string
import random
from curl_cffi import requests

load_dotenv()

encryptionKey = os.getenv("ENCRYPTION_KEY")
cipherSuite = Fernet(encryptionKey.encode()) if encryptionKey else None
cfClearance = os.getenv("CF_CLEARANCE")

def getNow(): return datetime.now().strftime('%d/%m/%Y %H:%M:%S')
def log(level, message): print(f"[{getNow()}] [{level}] {message}", flush=True)

def encryptData(data):
    if not data: return None
    return cipherSuite.encrypt(data.encode()).decode()

def decryptData(encryptedData):
    if not encryptedData: return None
    return cipherSuite.decrypt(encryptedData.encode()).decode()

userTimers = {}

def startStepTimeout(bot, chatId, seconds=60):
    cancelStepTimeout(chatId)
    
    def timeoutCallback():
        try:
            bot.clear_step_handler_by_chat_id(chatId)
            bot.send_message(chatId, "⏰ <b>Hết thời gian!</b>\nLệnh của bạn đã bị hủy do quá lâu không có phản hồi.", parse_mode="HTML")
            log("TIMEOUT", f"Đã hủy lệnh chờ của user {chatId} do hết thời gian.")
        except Exception as e:
            log("ERROR", f"Lỗi khi xử lý timeout: {e}")
        finally:
            if chatId in userTimers:
                del userTimers[chatId]

    timer = threading.Timer(seconds, timeoutCallback)
    timer.start()
    userTimers[chatId] = timer

def cancelStepTimeout(chatId):
    if chatId in userTimers:
        userTimers[chatId].cancel()
        del userTimers[chatId]

def getWeatherByHour(campusCode, targetTimeStr, dateStr):
    import redisManager
    try:
        cachedForecast = redisManager.redisClient.get(f"forecast:{campusCode}")
        if not cachedForecast: 
            return None
        
        forecastList = json.loads(cachedForecast)
        
        dtObj = datetime.strptime(f"{dateStr} {targetTimeStr}", "%d/%m/%Y %H:%M")
        targetHourStr = dtObj.strftime("%Y-%m-%d %H:00")

        for hourData in forecastList:
            if hourData['time'] == targetHourStr:
                conditionText = hourData['condition']['text'].lower()
                icon = "☀️"
                if "mưa" in conditionText: icon = "🌧️"
                elif "dông" in conditionText: icon = "⛈️"
                elif "mây" in conditionText: icon = "☁️"

                return {
                    "temp": hourData['temp_c'],
                    "desc": hourData['condition']['text'],
                    "icon": icon
                }
    except Exception as e:
        log("ERROR", f"Lỗi getWeatherByHour: {e}")
    
    return None

def generateFakeCaptcha(length=30):
    chars = string.ascii_letters + string.digits + "-_"
    return ''.join(random.choice(chars) for _ in range(length))

def safeRequest(method, url, **kwargs):
    headers = kwargs.get("headers", {})
    headers.update({"Connection": "close"})

    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if hostname.endswith("ut.edu.vn"):
        headers.setdefault("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36")
        headers.setdefault("Accept", "application/json, text/plain, */*")
        headers.setdefault("Referer", f"{parsed.scheme}://{hostname}/")
        headers.setdefault("Origin", f"{parsed.scheme}://{hostname}")
    kwargs["headers"] = headers

    if cfClearance and hostname.endswith("ut.edu.vn"):
        cookies = dict(kwargs.get("cookies") or {})
        cookies.setdefault("cf_clearance", cfClearance)
        kwargs["cookies"] = cookies
    
    kwargs.setdefault("impersonate", "chrome110")
    kwargs.setdefault("timeout", 20)

    try:
        with requests.Session() as s:
            respone = getattr(s, method.lower())(url, **kwargs)
            log(method, f"Gửi thành công request: {url} -> {respone.status_code}")
            return respone
    except Exception as e:
        log("WARN", f"Request Error: {e}")
        return None