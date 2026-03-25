# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# portalService.py

import requests
from datetime import datetime
import database as db
import utils
import redisManager

def verifyUthCredentials(user, password):
    try:
        r = requests.post("https://portal.ut.edu.vn/api/v1/user/login", json={"username": user, "password": password}, timeout=15)
        data = r.json()
        if r.status_code == 200 and data.get("token"): return True, "Thành công"
        return False, data.get("message", "Sai tài khoản hoặc mật khẩu")
    except: return False, "Lỗi kết nối server trường"

def getClassesByDate(chatId, user, password, targetDate):
    try:
        tk = getValidPortalToken(chatId, user, password)
        if not tk: return None
        
        # 1. Bẫy format ngày: Chuyển YYYY-MM-DD sang DD/MM/YYYY để khớp ngayBatDauHoc
        searchDate = datetime.strptime(targetDate, "%Y-%m-%d").strftime("%d/%m/%Y")
        
        # 2. Bẫy Headers: Portal giờ check Referer cực gắt, thiếu là nó trả body rỗng
        headers = {
            "authorization": f"Bearer {tk}",
            "Referer": "https://portal.ut.edu.vn/calendar",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "accept": "application/json, text/plain, */*"
        }
        
        res = requests.get(f"https://portal.ut.edu.vn/api/v1/lichhoc/lichTuan?date={targetDate}", headers=headers, timeout=20)
        
        if res.status_code == 401:
            utils.log("WARN", f"Token của {chatId} bị Invalid. Đang login lại")
            tk = redisManager.loginAndSaveToken(chatId, user, password) 
            
            if not tk: return None
        
        headers["authorization"] = f"Bearer {tk}"
        res = requests.get(f"https://portal.ut.edu.vn/api/v1/lichhoc/lichTuan?date={targetDate}", headers=headers)
            
        body = res.json().get("body", [])
        
        # 3. Logic lọc mới: Đừng tin thằng 'thu', hãy tin thằng 'ngayBatDauHoc'
        # Vì Portal giờ trả ngayBatDauHoc khớp với ngày thực tế của buổi học đó luôn
        if res.status_code == 200:
            return [c for c in body if c.get("ngayBatDauHoc") == searchDate]
        
    except Exception as e:
        print(f"Lỗi quét lịch: {e}")
        return None

def verifyAndSaveUser(chatId, mssv, password):
    isValid, reason = verifyUthCredentials(mssv, password)
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

def getValidPortalToken(chatId, rawUser, rawPass):
    cachedToken = redisManager.getSession(chatId, 'portal')
    if cachedToken: return cachedToken

    try:
        r = requests.post("https://portal.ut.edu.vn/api/v1/user/login", 
                        json={"username": rawUser, "password": rawPass}, timeout=15)
        token = r.json().get("token")
        if token:
            redisManager.saveSession(chatId, 'portal', token, expire=7200)
            return token
    except: pass
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
            msg += f"\n📘 <a href='{courseLink}'>{c['tenMonHoc']}</a>"
            msg += f"\n⏰ {c['tuGio']} - {c['denGio']}"
            msg += f"\n📍 {c['tenPhong']}\n"
        msg += f"\n🔗 <a href='https://portal.ut.edu.vn/'>Portal UTH</a>"
        return msg
    else:
        if not isAuto:
            return f"🎉 Ngày {dateStr} bạn được nghỉ nè!"
