# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# utils.py

import os
from datetime import datetime
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

encryptionKey = os.getenv("ENCRYPTION_KEY")
cipherSuite = Fernet(encryptionKey.encode()) if encryptionKey else None

def getNow(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def log(level, message): print(f"[{getNow()}] [{level}] {message}", flush=True)

def encryptData(data):
    if not data: return None
    return cipherSuite.encrypt(data.encode()).decode()

def decryptData(encryptedData):
    if not encryptedData: return None
    return cipherSuite.decrypt(encryptedData.encode()).decode()