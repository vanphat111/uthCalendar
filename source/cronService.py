# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# cronService.py

import time
import traceback
import database as db
import portalService
import courseService
from utils import log

def autoCheckAndNotify(bot):
    log("AUTO", "Bắt đầu quét lịch tự động...")
    today = time.strftime("%Y-%m-%d")
    try:
        conn = db.getDbConn(); cur = conn.cursor()
        cur.execute("SELECT chat_id FROM users WHERE notify_enabled = TRUE")
        rows = cur.fetchall(); cur.close(); conn.close()
        
        for r in rows:
            chatId = r[0]
            try:
                msg = portalService.formatCalendarMessage(chatId, today, isAuto=True)
                if msg and len(msg.strip()) > 0:
                    bot.send_message(chatId, msg, parse_mode="HTML", disable_web_page_preview=True, timeout=20)
                time.sleep(0.5)
            except Exception:
                log("ERROR", f"Lỗi gửi lịch cho {chatId}:\n{traceback.format_exc()}")
                continue
    except Exception:
        log("ERROR", f"Lỗi autoNotify hệ thống:\n{traceback.format_exc()}")

def autoScanAllUsers(bot):
    log("AUTO", "Bắt đầu quét deadline toàn bộ hệ thống...")
    try:
        conn = db.getDbConn(); cur = conn.cursor()
        cur.execute("SELECT chat_id FROM users WHERE notify_deadline = TRUE")
        users = cur.fetchall(); cur.close(); conn.close()
        for u in users:
            try:
                courseService.scanAllDeadlines(bot, u[0], isManual=False)
                time.sleep(1)
            except Exception:
                log("ERROR", f"Lỗi quét deadline cho {u[0]}:\n{traceback.format_exc()}")
                continue
    except Exception:
        log("ERROR", f"Lỗi autoScan hệ thống:\n{traceback.format_exc()}")