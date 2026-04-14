# Copyright (c) 2026 vanphat111 <phathovan14122006@email.com> | All rights reserved
# redisManager.py

import json
import os
import time
import uuid

import redis
import requests

from utils import log

redisClient = redis.Redis(
    host=os.getenv("REDIS_HOST", "uth_redis"),
    port=6379,
    db=0,
    decode_responses=True,
)

AUTH_BROKER_URL = os.getenv("AUTH_BROKER_URL", "http://uth_auth_broker:8000")
AUTH_BROKER_TIMEOUT = int(os.getenv("AUTH_BROKER_TIMEOUT", "120"))
AUTH_REFRESH_LOCK_TTL = int(os.getenv("AUTH_REFRESH_LOCK_TTL", "120"))
AUTH_REFRESH_LOCK_WAIT = int(os.getenv("AUTH_REFRESH_LOCK_WAIT", "45"))
AUTH_REFRESH_LOCK_POLL = float(os.getenv("AUTH_REFRESH_LOCK_POLL", "1.0"))
DEFAULT_PORTAL_TTL = int(os.getenv("AUTH_PORTAL_CACHE_TTL", "5400"))
DEFAULT_COURSE_TTL = int(os.getenv("AUTH_COURSE_CACHE_TTL", "3600"))


def _session_key(chatId, serviceType):
    return f"auth:{serviceType}:{chatId}"


def _refresh_lock_key(chatId):
    return f"auth:refresh-lock:{chatId}"


def _decode_json(data):
    return json.loads(data) if data else None


def _valid_portal_session(data):
    return bool(data and data.get("token"))


def _valid_course_session(data):
    return bool(data and data.get("cookies") and data.get("sesskey"))


def _clamp_ttl(value, default_ttl):
    try:
        ttl = int(value)
    except (TypeError, ValueError):
        ttl = default_ttl
    return max(300, min(ttl, 86400))


def _broker_endpoint(force_refresh=False):
    path = "/auth/refresh" if force_refresh else "/auth/bootstrap"
    return f"{AUTH_BROKER_URL.rstrip('/')}{path}"


def _call_auth_broker(chatId, user, password, force_refresh=False):
    response = requests.post(
        _broker_endpoint(force_refresh),
        json={"chatId": str(chatId), "username": user, "password": password},
        timeout=AUTH_BROKER_TIMEOUT,
    )

    content_type = (response.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        raise RuntimeError(f"Auth broker trả về content-type bất thường: {content_type or 'unknown'}")

    data = response.json()
    if response.status_code >= 400:
        raise RuntimeError(data.get("message") or f"Auth broker lỗi {response.status_code}")

    if not data.get("token") or not data.get("sesskey"):
        raise RuntimeError("Auth broker trả về dữ liệu đăng nhập không đầy đủ")

    return data


def _release_refresh_lock(lock_key, lock_value):
    redisClient.eval(
        """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        end
        return 0
        """,
        1,
        lock_key,
        lock_value,
    )


def _wait_for_session(chatId, serviceType):
    deadline = time.time() + AUTH_REFRESH_LOCK_WAIT
    while time.time() < deadline:
        cached = getSession(chatId, serviceType)
        if serviceType == "portal" and _valid_portal_session(cached):
            return cached
        if serviceType == "course" and _valid_course_session(cached):
            return cached
        time.sleep(AUTH_REFRESH_LOCK_POLL)
    return None


def _save_auth_bundle(chatId, brokerData):
    expires = brokerData.get("expires") or {}
    portalData = {
        "token": brokerData.get("token"),
        "cookies": brokerData.get("portal_cookies") or {},
        "expires": expires,
    }
    courseData = {
        "cookies": brokerData.get("course_cookies") or {},
        "sesskey": brokerData.get("sesskey"),
        "expires": expires,
    }

    saveSession(chatId, "portal", portalData, _clamp_ttl(expires.get("portal_cache_ttl_seconds"), DEFAULT_PORTAL_TTL))
    saveSession(chatId, "course", courseData, _clamp_ttl(expires.get("course_cache_ttl_seconds"), DEFAULT_COURSE_TTL))


def saveSession(chatId, serviceType, data, expire=7200):
    redisClient.set(_session_key(chatId, serviceType), json.dumps(data), ex=expire)
    log("REDIS", f"Đã lưu cache session cho {chatId} - {serviceType}")


def getSession(chatId, serviceType):
    data = redisClient.get(_session_key(chatId, serviceType))
    if data:
        log("REDIS", f"Đã đọc cache cho {chatId} - {serviceType}")
    return _decode_json(data)


def deleteSession(chatId, serviceType):
    redisClient.delete(_session_key(chatId, serviceType))
    log("REDIS", f"Đã xoá cache cho {chatId} - {serviceType}")


def deleteAuthSessions(chatId):
    deleteSession(chatId, "portal")
    deleteSession(chatId, "course")


def refreshAuthBundle(chatId, user, password, force_refresh=False):
    lock_key = _refresh_lock_key(chatId)
    lock_value = str(uuid.uuid4())

    if redisClient.set(lock_key, lock_value, nx=True, ex=AUTH_REFRESH_LOCK_TTL):
        try:
            brokerData = _call_auth_broker(chatId, user, password, force_refresh=force_refresh)
            _save_auth_bundle(chatId, brokerData)
            return brokerData
        finally:
            _release_refresh_lock(lock_key, lock_value)

    log("INFO", f"Đang chờ auth refresh lock cho {chatId}")
    portalData = _wait_for_session(chatId, "portal")
    courseData = _wait_for_session(chatId, "course")
    if _valid_portal_session(portalData) and _valid_course_session(courseData):
        return {
            "token": portalData["token"],
            "portal_cookies": portalData.get("cookies") or {},
            "course_cookies": courseData.get("cookies") or {},
            "sesskey": courseData.get("sesskey"),
            "expires": courseData.get("expires") or portalData.get("expires") or {},
        }
    raise RuntimeError("Không thể chờ auth broker làm mới session")


def getPortalSession(chatId, user, password, force_refresh=False):
    cached = None if force_refresh else getSession(chatId, "portal")
    if _valid_portal_session(cached):
        return cached

    refreshAuthBundle(chatId, user, password, force_refresh=force_refresh)
    return getSession(chatId, "portal")


def getCourseSession(chatId, user, password, force_refresh=False):
    cached = None if force_refresh else getSession(chatId, "course")
    if _valid_course_session(cached):
        return cached

    refreshAuthBundle(chatId, user, password, force_refresh=force_refresh)
    return getSession(chatId, "course")


def loginAndSaveToken(chatId, user, password):
    portalData = getPortalSession(chatId, user, password, force_refresh=True)
    return portalData.get("token") if portalData else None
