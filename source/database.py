# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# database.py

import psycopg2
import os
import time
from utils import log

dbConfig = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS")
}

def getDbConn(): return psycopg2.connect(**dbConfig)

def initDb():
    log("SYSTEM", "Bắt đầu kiểm tra và khởi tạo Database...")
    retries = 10
    while retries > 0:
        try:
            conn = getDbConn(); cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id TEXT PRIMARY KEY, 
                    uth_user TEXT NOT NULL, 
                    uth_pass TEXT NOT NULL, 
                    notify_enabled BOOLEAN DEFAULT TRUE, 
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit(); cur.close(); conn.close()
            log("INFO", "Hệ thống Database đã sẵn sàng và đã tạo bảng.")
            return
        except Exception as e:
            log("RETRY", f"DB chưa sẵn sàng, đang thử lại sau 5s... ({retries}) - {e}")
            retries -= 1
            time.sleep(5)