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
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_deadline BOOLEAN DEFAULT TRUE;")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS completed_tasks (
                    id SERIAL PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chat_id, task_id)
                );
            """)
            
            conn.commit(); cur.close(); conn.close()
            log("INFO", "Hệ thống Database đã sẵn sàng (Users & Completed Tasks).")
            return
        except Exception as e:
            log("RETRY", f"DB chưa sẵn sàng, đang thử lại sau 5s... ({retries}) - {e}")
            retries -= 1
            time.sleep(5)

def getCompletedTaskIds(chatId):
    try:
        conn = getDbConn(); cur = conn.cursor()
        cur.execute("SELECT task_id FROM completed_tasks WHERE chat_id = %s", (str(chatId),))
        res = [row[0] for row in cur.fetchall()]
        cur.close(); conn.close()
        return res
    except: return []

def markTaskCompleted(chatId, taskId):
    try:
        conn = getDbConn(); cur = conn.cursor()
        cur.execute("INSERT INTO completed_tasks (chat_id, task_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (str(chatId), str(taskId)))
        conn.commit(); cur.close(); conn.close()
        return True
    except: return False

def unmarkTaskCompleted(chatId, taskId):
    try:
        conn = getDbConn(); cur = conn.cursor()
        # Xoá bản ghi để trạng thái quay về "Chưa hoàn thành"
        cur.execute("DELETE FROM completed_tasks WHERE chat_id = %s AND task_id = %s", (str(chatId), str(taskId)))
        conn.commit(); cur.close(); conn.close()
        return True
    except: return False

def getUserCredentials(chatId):
    try:
        conn = getDbConn(); cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE chat_id = %s", (str(chatId),))
        res = cur.fetchone(); cur.close(); conn.close()
        return res
    except: return None

def updateDeadlineStatus(chatId, status):
    try:
        conn = getDbConn(); cur = conn.cursor()
        cur.execute("UPDATE users SET notify_deadline = %s WHERE chat_id = %s", (status, str(chatId)))
        conn.commit(); cur.close(); conn.close()
        return True
    except: return False

def getDeadlineStatus(chatId):
    try:
        conn = getDbConn(); cur = conn.cursor()
        cur.execute("SELECT notify_deadline FROM users WHERE chat_id = %s", (str(chatId),))
        res = cur.fetchone(); cur.close(); conn.close()
        return res[0] if res else True
    except: return True