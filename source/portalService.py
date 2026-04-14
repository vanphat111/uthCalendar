# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# portalService.py

# from curl_cffi import requests
from datetime import datetime

import database as db
import redisManager
import utils

# session = requests.Session(impersonate="chrome110")

def _is_json_response(response):
    contentType = (response.headers.get("content-type") or "").lower()
    return "application/json" in contentType


def verifyUthCredentials(chatId, user, password):
    try:
        portalSession = redisManager.getPortalSession(chatId, user, password, force_refresh=True)
        if portalSession and portalSession.get("token"):
            return True, "Thành công"
        return False, "Không thể tạo session Portal"
    except Exception as e:
        utils.log("ERROR", f"verifyUthCredentials lỗi: {e}")
        return False, str(e)

def getClassesByDate(chatId, user, password, targetDate):
    try:
        portalSession = getValidPortalSession(chatId, user, password)
        if not portalSession:
            return None
        
        dateObj = datetime.strptime(targetDate, "%d/%m/%Y")
        isoDate = dateObj.strftime("%Y-%m-%d")
        searchDate = targetDate
        
        headers = {
            "authorization": f"Bearer {portalSession['token']}",
            "Referer": "https://portal.ut.edu.vn/calendar",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "accept": "application/json, text/plain, */*"
        }
        url = f"https://portal.ut.edu.vn/api/v1/lichhoc/lichTuan?date={isoDate}"
        res = utils.safeRequest("GET", url, headers=headers, cookies=portalSession.get("cookies") or {})
        if not res:
            return None

        if res.status_code == 401 or not _is_json_response(res):
            utils.log("WARN", f"Portal session của {chatId} hết hạn hoặc bị chặn. Đang làm mới")
            portalSession = getValidPortalSession(chatId, user, password, force_refresh=True)
            if not portalSession:
                return None
            headers["authorization"] = f"Bearer {portalSession['token']}"
            res = utils.safeRequest("GET", url, headers=headers, cookies=portalSession.get("cookies") or {})
            if not res or not _is_json_response(res):
                return None

        body = res.json().get("body", [])
        
        if res.status_code == 200:
            return [c for c in body if c.get("ngayBatDauHoc") == searchDate]
        
    except Exception as e:
        print(f"Lỗi quét lịch: {e}")
        return None

def verifyAndSaveUser(chatId, mssv, password):
    isValid, reason = verifyUthCredentials(chatId, mssv, password)
    if isValid:
        conn = db.getDbConn(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (chat_id, uth_user, uth_pass) VALUES (%s, %s, %s) ON CONFLICT (chat_id) DO UPDATE SET uth_user = EXCLUDED.uth_user, uth_pass = EXCLUDED.uth_pass",
            (str(chatId), utils.encryptData(mssv), utils.encryptData(password))
        )
        conn.commit(); cur.close(); conn.close()
        utils.log("SUCCESS", f"User {chatId} đã đăng ký thành công")
        return True, "🎉 <b>Đăng ký thành công!</b> Mình sẽ tự động nhắc lịch cho bạn."
    
    utils.log("ERROR", f"User {chatId} đăng ký thất bại: {reason}")
    return False, f"❌ Thất bại: {reason}"

def getValidPortalSession(chatId, rawUser, rawPass, force_refresh=False):
    try:
        portalSession = redisManager.getPortalSession(chatId, rawUser, rawPass, force_refresh=force_refresh)
        if portalSession and portalSession.get("token"):
            return portalSession
    except Exception as e:
        utils.log("ERROR", f"Lỗi Server Portal: {e}")
    return None

def formatCalendarMessage(chatId, dateStr, isAuto=False):
    u = db.getUserCredentials(chatId)
    if not u: return "Bạn chưa đăng ký tài khoản!"
    
    rawUser = utils.decryptData(u['uth_user'])
    rawPass = utils.decryptData(u['uth_pass'])

    classes = getClassesByDate(chatId, rawUser, rawPass, dateStr)
    if classes:
        header = f"🔔 <b>NHẮC LỊCH TỰ ĐỘNG ({dateStr})</b>\n" if isAuto else f"📅 <b>LỊCH HỌC {dateStr}</b>\n"
        msg = header + "━━━━━━━━━━━━━━━━━━\n"
        for c in classes:
            courseLink = c.get('link', 'https://courses.ut.edu.vn/')
            statusLabel = "🛑 Tạm ngưng" if c.get("isTamNgung") else "🟢 Bình thường"

            weatherLabel = ""
            target_cs = None
            ten_phong = c.get('tenPhong', '')
            co_so_display = c.get('coSoToDisplay', '')
            
            if "CS1" in ten_phong or "Cơ sở 1" in co_so_display: target_cs = "CS1"
            elif "CS3" in ten_phong or "Cơ sở 3" in co_so_display: target_cs = "CS3"
            elif "CS2" in ten_phong or "Cơ sở 2" in co_so_display: target_cs = "CS2"
            
            if target_cs:
                weatherData = utils.getWeatherByHour(target_cs, c['tuGio'], dateStr)
                if weatherData:
                    weatherLabel = (
                        f"\n🌡️ {target_cs} (<code>{c['tuGio']}</code>): "
                        f"{weatherData['icon']} {weatherData['temp']}°C ({weatherData['desc']})"
                    )

            msg += f"\n📘 <a href='{courseLink}'>{c['tenMonHoc']}</a>"
            msg += f"\n⏰ {c['tuGio']} - {c['denGio']}"
            msg += f"\n📍 {c['tenPhong']}"
            msg += weatherLabel
            msg += f"\n📌 {statusLabel}\n"
        msg += f"\n🔗 <a href='https://portal.ut.edu.vn/'>Portal UTH</a>"
        return msg
    else:
        return f"🎉 Ngày {dateStr} bạn được nghỉ nè!"
