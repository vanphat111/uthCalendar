# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# redisManager.py

import redis
import json
import os
from utils import log

redisClient = redis.Redis(
    host=os.getenv('REDIS_HOST', 'uth_redis'), 
    port=6379, 
    db=0, 
    decode_responses=True
)

def saveSession(chatId, serviceType, data, expire=7200):
    key = f"auth:{serviceType}:{chatId}"
    redisClient.set(key, json.dumps(data), ex=expire)
    log("REDIS", f"Đã lưu cache session cho {chatId} - {serviceType}")

def getSession(chatId, serviceType):
    key = f"auth:{serviceType}:{chatId}"
    data = redisClient.get(key)
    if data:
        log("REDIS", f"Đã đẩy cache cho {chatId} - {serviceType}")
        return json.loads(data)
    return None

def deleteSession(chatId, serviceType):
    key = f"auth:{serviceType}:{chatId}"
    redisClient.delete(key)
    log("REDIS", f"Đã xoá cache cho {chatId} - {serviceType}")