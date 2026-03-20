import requests
import time
from datetime import datetime
import database as db
import utils
import re

def fetchMoodleSession(username, password):
    session = requests.Session()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        r_portal = session.post("https://portal.ut.edu.vn/api/v1/user/login", 
                                json={"username": username, "password": password}, headers=headers, timeout=15)
        jwt = r_portal.json().get("token")
        if not jwt: return None, None

        jump_url = f"https://courses.ut.edu.vn/login/index.php?token={jwt}"
        session.get(jump_url, timeout=15)

        r_home = session.get("https://courses.ut.edu.vn/my/", timeout=15)
        sesskey_match = re.search(r'"sesskey":"([^"]+)"', r_home.text)
        sesskey = sesskey_match.group(1) if sesskey_match else None
        
        return session, sesskey
    except Exception as e:
        utils.log("ERROR", f"Lỗi login Moodle: {e}")
        return None, None

from datetime import datetime

def getEventsViaAjax(session, sesskey):
    url = f"https://courses.ut.edu.vn/lib/ajax/service.php?sesskey={sesskey}"
    now_dt = datetime.now()
    now_ts = int(time.time())
    
    # Mốc chặn: 7 ngày sau (7 ngày * 24h * 3600s)
    seven_days_later = now_ts + (7 * 24 * 60 * 60)
    
    payload = [{
        "index": 0,
        "methodname": "core_calendar_get_calendar_monthly_view",
        "args": {
            "year": str(now_dt.year),
            "month": str(now_dt.month),
            "courseid": 1,
            "day": 1,
            "view": "month"
        }
    }]
    
    try:
        r = session.post(url, json=payload, timeout=15)
        res = r.json()[0]
        if res.get('error'): return []

        weeks = res['data']['weeks']
        all_events = []
        
        for week in weeks:
            for day in week['days']:
                if day['events']:
                    for event in day['events']:
                        # CHỐT CHẶN: Chỉ lấy từ Bây giờ đến 7 ngày sau
                        if now_ts <= event['timesort'] <= seven_days_later:
                            all_events.append(event)
        
        all_events.sort(key=lambda x: x['timesort'])
        return all_events

    except Exception as e:
        utils.log("ERROR", f"Lỗi lọc Monthly Events 7 ngày: {e}")
        return []

    except Exception as e:
        utils.log("ERROR", f"Lỗi lấy Monthly Events: {e}")
        return []

def scanAllDeadlines(bot, chatId, isManual=False):
    u = db.getUserCredentials(chatId)
    if not u: return False

    rawUser = utils.decryptData(u[1]); rawPass = utils.decryptData(u[2])
    session, sesskey = fetchMoodleSession(rawUser, rawPass)
    
    if not session or not sesskey:
        if isManual: bot.send_message(chatId, "❌ Không thể kết nối hệ thống Courses.")
        return False

    events = getEventsViaAjax(session, sesskey)
    completedIds = db.getCompletedTaskIds(chatId)

    for e in events:
        due = datetime.fromtimestamp(e['timesort']).strftime('%d/%m %H:%M')
        isDone = str(e['id']) in completedIds
        
        statusIcon = "✅" if isDone else "❌"
        statusText = "Đã hoàn thành" if isDone else "Chưa hoàn thành"
        # Thay đổi text và callback dựa trên trạng thái
        btnText = "❌ Đánh dấu chưa xong" if isDone else "✅ Đánh dấu hoàn thành"
        callbackData = f"undone_{e['id']}" if isDone else f"done_{e['id']}"
        
        text = (
            f"🔔 <a href='{e.get('url')}'><b>{e['name']}</b></a>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📝 <b>Trạng thái:</b> {statusIcon} {statusText}\n"
            f"📚 <b>Môn:</b> {e['course']['fullname']}\n"
            f"⏰ <b>Hạn:</b> <code>{due}</code>"
        )
        
        from telebot import types
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(btnText, callback_data=callbackData))
        
        bot.send_message(chatId, text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    return True

def getEventIcon(eventType):
    icons = {'assign': '📝', 'quiz': '✍️', 'course': '📚', 'site': '🌐'}
    return icons.get(eventType, '🔔')