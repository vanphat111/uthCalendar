from flask import Flask, jsonify, request
from browser_auth import AuthBootstrapError
from browser_auth import AuthUpstreamBlocked
from browser_auth import build_auth_bundle
from browser_auth import get_profile_lock
from browser_auth import get_settings

app = Flask(__name__)

def _json_error(status_code, message, error="broker_error"):
    return jsonify({"error": error, "message": message}), status_code


def _handle_auth(force_relogin=False):
    payload = request.get_json(silent=True) or {}
    chat_id = payload.get("chatId")
    username = payload.get("username")
    password = payload.get("password")

    if not chat_id or not username or not password:
        return _json_error(400, "Thiếu chatId, username hoặc password", "invalid_request")

    with get_profile_lock(chat_id):
        try:
            return jsonify(build_auth_bundle(chat_id, username, password, force_relogin=force_relogin))
        except AuthUpstreamBlocked as exc:
            return _json_error(401, str(exc), "upstream_blocked")
        except AuthBootstrapError as exc:
            return _json_error(502, f"Auth bootstrap lỗi: {exc}", "auth_failed")
        except ValueError as exc:
            return _json_error(401, str(exc), "auth_failed")
        except Exception as exc:
            return _json_error(500, f"Auth broker lỗi: {exc}")


@app.get("/health")
def healthcheck():
    return jsonify({"status": "ok", **get_settings()})


@app.post("/auth/bootstrap")
def auth_bootstrap():
    return _handle_auth(force_relogin=False)


@app.post("/auth/refresh")
def auth_refresh():
    return _handle_auth(force_relogin=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
