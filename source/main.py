# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# main.py

import telebot
import os
import threading
import schedule
import time
from database import initDb
import teleBot
import portalService
import database as db
from utils import log

teleToken = os.getenv("TELE_TOKEN")
bot = telebot.TeleBot(teleToken)

def autoCheckAndNotify():
    log("AUTO", "Bắt đầu quét lịch tự động...")
    today = time.strftime("%Y-%m-%d")
    try:
        conn = db.getDbConn(); cur = conn.cursor()
        cur.execute("SELECT chat_id FROM users WHERE notify_enabled = TRUE")
        rows = cur.fetchall(); cur.close(); conn.close()
        for r in rows:
            msg = portalService.formatCalendarMessage(r[0], today, isAuto=True)
            bot.send_message(r[0], msg, parse_mode="HTML", disable_web_page_preview=True)
            time.sleep(0.3)
    except Exception as e: log("ERROR", f"Lỗi autoNotify: {e}")

def runScheduler():
    schedule.every().day.at("05:00").do(autoCheckAndNotify)
    schedule.every().day.at("12:00").do(autoCheckAndNotify)
    schedule.every().day.at("17:00").do(autoCheckAndNotify)
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    initDb()
    teleBot.setBotCommands(bot)
    teleBot.registerHandlers(bot)
    threading.Thread(target=runScheduler, daemon=True).start()
    log("SYSTEM", "Bot UTH (camelCase) khởi động!")
    bot.infinity_polling(timeout=60)