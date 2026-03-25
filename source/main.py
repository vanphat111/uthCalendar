# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# main.py

import telebot, os, threading, schedule, time
import teleBot, cronService, database as db
from utils import log

bot = telebot.TeleBot(os.getenv("TELE_TOKEN"))
adminId = os.getenv("ADMIN_ID")

def runScheduler():
    schedule.every().day.at("05:00").do(cronService.autoCheckAndNotify, bot)
    schedule.every().day.at("12:00").do(cronService.autoCheckAndNotify, bot)
    schedule.every().day.at("17:00").do(cronService.autoCheckAndNotify, bot)
    schedule.every().monday.at("19:00").do(cronService.autoScanAllUsers, bot)
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    db.initDb()
    teleBot.registerHandlers(bot)
    threading.Thread(target=runScheduler, daemon=True).start()
    log("SYSTEM", "Bot UTH v2.1.2 (Multi-Task & Dict-based) đã sẵn sàng!")
    
    while True:
        try:
            bot.polling(non_stop=True, timeout=20)
        except Exception as e:
            log("ERROR", f"Polling Error: {e}")
            time.sleep(5)