import base64
import json
import os
import random
import re
import string
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

DATA_DIR = Path(os.getenv("AUTH_BROKER_DATA_DIR", "/data"))
DEFAULT_PORTAL_TTL = int(os.getenv("AUTH_BROKER_DEFAULT_PORTAL_TTL", "5400"))
DEFAULT_COURSE_TTL = int(os.getenv("AUTH_BROKER_DEFAULT_COURSE_TTL", "3600"))
FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL", "http://flaresolverr:8191")
FLARESOLVERR_TIMEOUT_MS = int(os.getenv("FLARESOLVERR_TIMEOUT_MS", "120000"))
FLARESOLVERR_WAIT_SECONDS = int(os.getenv("FLARESOLVERR_WAIT_SECONDS", "8"))
LOGIN_TIMEOUT_SECONDS = int(os.getenv("AUTH_BROKER_LOGIN_TIMEOUT_SECONDS", "45"))

_profile_locks = {}
_profile_locks_guard = threading.Lock()


class AuthBootstrapError(RuntimeError):
    pass


class AuthUpstreamBlocked(AuthBootstrapError):
    pass


def get_settings():
    return {
        "data_dir": str(DATA_DIR),
        "flaresolverr_url": FLARESOLVERR_URL,
    }


def get_profile_lock(chat_id):
    safe_chat_id = _safe_chat_id(chat_id)
    with _profile_locks_guard:
        if safe_chat_id not in _profile_locks:
            _profile_locks[safe_chat_id] = threading.Lock()
        return _profile_locks[safe_chat_id]


def build_auth_bundle(chat_id, username, password, force_relogin=False):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    session_id = f"uth-{_safe_chat_id(chat_id)}"

    if force_relogin:
        _destroy_flaresolverr_session(session_id)

    _create_flaresolverr_session(session_id)
    try:
        solve_data = _solve_portal_challenge(session_id)
        user_agent = solve_data.get("userAgent") or _default_user_agent()

        portal_session = requests.Session()
        portal_session.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://portal.ut.edu.vn/",
            "Origin": "https://portal.ut.edu.vn",
            "Connection": "close",
        })
        _apply_cookie_list(portal_session, solve_data.get("cookies") or [])

        login_result = _portal_login(portal_session, username, password)
        content_type = login_result.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            raise AuthUpstreamBlocked(
                "Portal login returned non-JSON response. "
                f"content-type={content_type or 'unknown'} body_snippet={_snippet(login_result.text)}"
            )

        try:
            login_data = login_result.json()
        except Exception as exc:
            raise AuthBootstrapError(f"Portal login JSON parse failed: {exc}. body_snippet={_snippet(login_result.text)}") from exc

        token = login_data.get("token")
        if login_result.status_code != 200 or not token:
            raise AuthBootstrapError(login_data.get("message") or f"Portal login failed: HTTP {login_result.status_code}")

        course_result = _bootstrap_course_session(portal_session, token, solve_data.get("cookies") or [])
        course_html = course_result.text
        sesskey = _extract_sesskey(course_html)
        if not sesskey:
            raise AuthBootstrapError(
                "Courses session missing sesskey. "
                f"content-type={course_result.headers.get('content-type', 'unknown')} body_snippet={_snippet(course_html)}"
            )

        portal_cookies = _cookie_dict_for_domain(portal_session.cookies, "portal.ut.edu.vn")
        course_cookies = _cookie_dict_for_domain(portal_session.cookies, "courses.ut.edu.vn")
        if not course_cookies:
            raise AuthBootstrapError("Courses bootstrap succeeded but no courses cookies were stored")

        token_expiry = _decode_token_expiry(token)
        course_expiry = _cookie_expiry(portal_session.cookies, "courses.ut.edu.vn")
        return {
            "token": token,
            "portal_cookies": portal_cookies,
            "course_cookies": course_cookies,
            "sesskey": sesskey,
            "user_agent": user_agent,
            "expires": {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "portal_token_exp_epoch": token_expiry,
                "portal_token_exp_iso": _iso_from_epoch(token_expiry),
                "portal_cache_ttl_seconds": _ttl_from_expiry(token_expiry, DEFAULT_PORTAL_TTL),
                "course_cookie_exp_epoch": course_expiry,
                "course_cookie_exp_iso": _iso_from_epoch(course_expiry),
                "course_cache_ttl_seconds": _ttl_from_expiry(course_expiry, DEFAULT_COURSE_TTL),
            },
        }
    finally:
        _destroy_flaresolverr_session(session_id)


def _safe_chat_id(chat_id):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(chat_id))


def _default_user_agent():
    return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


def _generate_fake_captcha(length=30):
    chars = string.ascii_letters + string.digits + "-_"
    return "".join(random.choice(chars) for _ in range(length))


def _iso_from_epoch(epoch_seconds):
    return datetime.fromtimestamp(epoch_seconds, timezone.utc).isoformat() if epoch_seconds else None


def _decode_token_expiry(token):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        exp_value = data.get("exp")
        return int(exp_value) if exp_value else None
    except Exception:
        return None


def _ttl_from_expiry(expiry_epoch, default_ttl):
    if not expiry_epoch:
        return default_ttl
    return max(300, int(expiry_epoch - time.time()))


def _extract_sesskey(html):
    match = re.search(r'"sesskey":"([^"]+)"', html)
    if match:
        return match.group(1)
    match = re.search(r'M\.cfg\s*=\s*\{.*?sesskey\s*:\s*"([^"]+)"', html, flags=re.DOTALL)
    return match.group(1) if match else None


def _snippet(text, limit=240):
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    return cleaned[:limit]


def _flaresolverr_request(payload):
    response = requests.post(
        f"{FLARESOLVERR_URL.rstrip('/')}/v1",
        json=payload,
        timeout=max(30, FLARESOLVERR_TIMEOUT_MS / 1000 + 15),
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "ok":
        raise AuthBootstrapError(data.get("message") or "FlareSolverr request failed")
    return data


def _create_flaresolverr_session(session_id):
    _flaresolverr_request({"cmd": "sessions.create", "session": session_id})


def _destroy_flaresolverr_session(session_id):
    try:
        _flaresolverr_request({"cmd": "sessions.destroy", "session": session_id})
    except Exception:
        pass


def _solve_portal_challenge(session_id):
    # Giải quyết challenge của portal trước
    data_portal = _flaresolverr_request(
        {
            "cmd": "request.get",
            "session": session_id,
            "url": "https://portal.ut.edu.vn/",
            "maxTimeout": FLARESOLVERR_TIMEOUT_MS,
            "waitInSeconds": FLARESOLVERR_WAIT_SECONDS,
        }
    )
    solution = data_portal.get("solution") or {}
    
    # Sau đó giải quyết luôn challenge của courses trong cùng một session
    # Điều này đảm bảo flaresolverr đã pass cả 2 bên (vì cloudflare có thể phân lập challenge theo sub-domain)
    _flaresolverr_request(
        {
            "cmd": "request.get",
            "session": session_id,
            "url": "https://courses.ut.edu.vn/",
            "maxTimeout": FLARESOLVERR_TIMEOUT_MS,
            "waitInSeconds": FLARESOLVERR_WAIT_SECONDS,
        }
    )
    
    # Gom lại toàn bộ cookies của session hiện tại (bao gồm cả portal và courses)
    session_info = _flaresolverr_request(
        {
            "cmd": "sessions.list",
        }
    )
    
    # Vì API flaresolverr sessions.list không trả về cookie chi tiết của từng url, 
    # ta nên sử dụng kết quả của cookie lúc giải courses bổ sung vào portal
    # Thay vào đó, gọi thêm 1 lệnh request.get cho portal để lấy full cookies 
    final_data = _flaresolverr_request(
        {
            "cmd": "request.get",
            "session": session_id,
            "url": "https://portal.ut.edu.vn/",
            "maxTimeout": 10000, 
            "waitInSeconds": 1,
        }
    )
    
    final_solution = final_data.get("solution") or {}
    
    response_html = solution.get("response") or ""
    content_type = (solution.get("headers") or {}).get("content-type", "")
    if "just a moment" in response_html.lower() or "performing security verification" in response_html.lower():
        raise AuthUpstreamBlocked(f"Cloudflare challenge still present after FlareSolverr. body_snippet={_snippet(response_html)}")
    if not final_solution.get("cookies"):
        raise AuthBootstrapError("FlareSolverr did not return any portal cookies")
    if content_type and "text/html" not in content_type.lower():
        raise AuthBootstrapError(f"Unexpected portal bootstrap content-type from FlareSolverr: {content_type}")
    return final_solution


def _apply_cookie_list(session, cookies):
    for cookie in cookies:
        session.cookies.set(
            cookie.get("name"),
            cookie.get("value"),
            domain=(cookie.get("domain") or "").lstrip("."),
            path=cookie.get("path") or "/",
        )


def _portal_login(session, username, password):
    fake_captcha = _generate_fake_captcha()
    url = f"https://portal.ut.edu.vn/api/v1/user/login?g-recaptcha-response={fake_captcha}"
    return session.post(
        url,
        json={"username": username, "password": password},
        timeout=LOGIN_TIMEOUT_SECONDS,
    )


def _bootstrap_course_session(session, token, solve_data_cookies):
    # Trích xuất và áp dụng lại cookies từ Flaresolverr, đặc biệt là cf_clearance nếu có
    # cf_clearance từ courses.ut.edu.vn có thể được gán vào parent domain .ut.edu.vn
    _apply_cookie_list(session, solve_data_cookies)
    
    session.get(
        f"https://courses.ut.edu.vn/login/index.php?token={token}",
        timeout=LOGIN_TIMEOUT_SECONDS,
        headers={"Referer": "https://portal.ut.edu.vn/"},
    )
    return session.get(
        "https://courses.ut.edu.vn/my/",
        timeout=LOGIN_TIMEOUT_SECONDS,
        headers={"Referer": "https://courses.ut.edu.vn/login/index.php"},
    )


def _cookie_matches_domain(cookie_domain, target_host):
    cookie_domain = (cookie_domain or "").lstrip(".").lower()
    target_host = (target_host or "").lstrip(".").lower()
    if not cookie_domain or not target_host:
        return False
    return target_host == cookie_domain or target_host.endswith(f".{cookie_domain}") or cookie_domain.endswith(f".{target_host}")


def _cookie_dict_for_domain(cookiejar, domain_fragment):
    out = {}
    for cookie in cookiejar:
        # Check if the cookie is explicitly needed for our domain or if it's a Cloudflare clearance cookie
        if _cookie_matches_domain(cookie.domain, domain_fragment) or cookie.name == "cf_clearance":
            out[cookie.name] = cookie.value
    return out


def _cookie_expiry(cookiejar, domain_fragment):
    expiries = []
    for cookie in cookiejar:
        if domain_fragment in (cookie.domain or "") and cookie.expires:
            expiries.append(int(cookie.expires))
    return min(expiries) if expiries else None


__all__ = ["AuthBootstrapError", "AuthUpstreamBlocked", "build_auth_bundle", "get_profile_lock", "get_settings"]
