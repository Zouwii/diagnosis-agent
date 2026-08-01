#!/usr/bin/env python3
"""DiagKit Auth Proxy v4 — Flask session cookie passthrough.

参考 management-system 前端 LoginPage + authStore 的做法：
  restoreSession → GET /auth/me            → 验证 session 是否有效
  login          → GET /auth/dingtalk/url  → 获取 OAuth 链接 → 跳转钉钉
  callback       → POST /auth/get_token    → authCode 换 session → Set-Cookie
  logout         → POST /auth/logout       → 清除 session

Architecture:
    Browser :5433 → Auth Proxy (this script)
                   ├─ /                    → verify session → terminal or login
                   ├─ /auth/login          → redirect to DingTalk OAuth
                   ├─ /auth/callback       → POST backend /get_token → Set-Cookie → redirect /
                   ├─ /logout              → POST backend /logout → clear cookie → redirect /
                   └─ /ttyd/*, /ws         → reverse proxy to ttyd (:5434)

    Session 由 Flask 后端 (5002) 管理，proxy 只做 cookie 透传，
    不自建 session，不做 SID 轮询。

Dependencies: Python 3.7+ stdlib only.
"""

import sys
import os
import json
import time
import socket
import secrets
import threading
import http.server
import http.client
import urllib.parse
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════
PROXY_PORT   = int(os.getenv("DIAGKIT_PROXY_PORT", "5433"))
TTYD_PORT    = int(os.getenv("DIAGKIT_TTYD_PORT_INTERNAL", "5434"))
MGMT_API     = os.getenv("DIAGKIT_MGMT_API", "http://127.0.0.1:5002/api/bt")
LOG_DIR      = Path(os.path.expanduser("~/diagkit/logs"))
PENDING_DIR  = Path(os.path.expanduser("~/diagkit/.pending_users"))

for a in sys.argv[1:]:
    if a.startswith("--port="):       PROXY_PORT = int(a.split("=", 1)[1])
    elif a.startswith("--ttyd-port="): TTYD_PORT  = int(a.split("=", 1)[1])


def _server_ip() -> str:
    ip = os.getenv("DIAGKIT_SERVER_IP", "").strip()
    if ip:
        return ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"
    return ip


SERVER_IP      = _server_ip()
CALLBACK_URL   = f"http://{SERVER_IP}:{PROXY_PORT}/auth/callback"

# ═══════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════
LOG_DIR.mkdir(parents=True, exist_ok=True)
PENDING_DIR.mkdir(parents=True, exist_ok=True)
_log_lock    = threading.Lock()
_pending_seq = 0


def _log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[diagkit-proxy {ts}] {msg}"
    with _log_lock:
        try:
            (LOG_DIR / "proxy.log").open("a").write(line + "\n")
        except Exception:
            pass
    print(line, file=sys.stderr, flush=True)


# ═══════════════════════════════════════════════════════════════════════
# Backend HTTP helpers — 跟 management-system 前端一样调后端 API
# ═══════════════════════════════════════════════════════════════════════
def _call_backend(method: str, path: str, body: dict | None = None,
                  cookie: str | None = None, timeout: int = 10):
    """调用 management-system 后端，返回 (status, resp_json, resp_headers_lowercase)."""
    conn = http.client.HTTPConnection("127.0.0.1", 5002, timeout=timeout)
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie

    full = f"{MGMT_API}{path}"
    p = urllib.parse.urlparse(full)
    req_path = p.path + ("?" + p.query if p.query else "")

    try:
        conn.request(method, req_path,
                     body=json.dumps(body) if body else None,
                     headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        try:
            data = json.loads(raw)
        except Exception:
            data = {"_raw": raw.decode("utf-8", errors="replace")}
        headers_lower = {k.lower(): v for k, v in resp.getheaders()}
        return resp.status, data, headers_lower
    except Exception as e:
        _log(f"backend {method} {path} error: {e}")
        return 502, {"error": str(e)}, {}
    finally:
        conn.close()


def _verify_session(cookie: str) -> dict | None:
    """用浏览器的 session cookie 去后端 /auth/me 验证身份。"""
    if not cookie:
        return None
    status, data, _ = _call_backend("GET", "/auth/me", cookie=cookie)
    if status == 200:
        user = data.get("data")
        if isinstance(user, dict) and user.get("name"):
            return user
    return None


def _build_oauth_url() -> str | None:
    """从后端获取 OAuth URL 模板，把 redirect_uri 换成 proxy 的 callback。"""
    status, data, _ = _call_backend("GET", "/auth/dingtalk/url")
    if status != 200:
        _log(f"get oauth url failed: status={status}")
        return None
    oauth_url = (data.get("data") or {}).get("url", "")
    if not oauth_url:
        _log("oauth url empty")
        return None

    parsed = urllib.parse.urlparse(oauth_url)
    params = dict(urllib.parse.parse_qsl(parsed.query))
    params["redirect_uri"] = CALLBACK_URL
    # CSRF state
    state = secrets.token_hex(16)
    params["state"] = state
    _save_oauth_state(state)
    _log(f"oauth state created: {state[:8]}...")
    return parsed._replace(query=urllib.parse.urlencode(params)).geturl()


# ═══════════════════════════════════════════════════════════════════════
# OAuth CSRF state store (TTL 10 min)
# ═══════════════════════════════════════════════════════════════════════
_oauth_states: dict[str, float] = {}
_oauth_lock = threading.Lock()
OAUTH_STATE_TTL = 600


def _save_oauth_state(state: str) -> None:
    now = time.time()
    with _oauth_lock:
        expired = [s for s, ts in _oauth_states.items() if now - ts > OAUTH_STATE_TTL]
        for s in expired:
            _oauth_states.pop(s, None)
        _oauth_states[state] = now


def _validate_oauth_state(state: str) -> bool:
    now = time.time()
    with _oauth_lock:
        if state not in _oauth_states:
            return False
        if now - _oauth_states[state] > OAUTH_STATE_TTL:
            _oauth_states.pop(state, None)
            return False
        _oauth_states.pop(state, None)
        return True


# ═══════════════════════════════════════════════════════════════════════
# Pending user file — 供 diagkit-launch.sh 读取用户身份
# ═══════════════════════════════════════════════════════════════════════
def _write_pending_user(user_id: str, name: str) -> None:
    global _pending_seq
    _pending_seq += 1
    fname = f"{int(time.time() * 1000)}-{_pending_seq}.json"
    try:
        (PENDING_DIR / fname).write_text(
            json.dumps({"userId": user_id, "name": name}, ensure_ascii=False))
    except Exception:
        pass
    # 清理 > 60s 的旧文件
    now = time.time()
    for f in PENDING_DIR.glob("*.json"):
        try:
            ts = int(f.stem.split("-")[0]) / 1000
            if now - ts > 60:
                f.unlink()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════
# HTML pages
# ═══════════════════════════════════════════════════════════════════════
_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>迦智诊断助手</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);color:#eee;display:flex;justify-content:center;align-items:center;min-height:100vh}
.card{background:rgba(22,33,62,.95);border-radius:20px;padding:48px 40px;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,.4);max-width:420px;width:90%;border:1px solid rgba(255,255,255,.1)}
.logo{font-size:56px;margin-bottom:12px}
h1{font-size:26px;font-weight:600;margin-bottom:8px;background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.subtitle{color:#8892b0;margin-bottom:32px;font-size:15px;line-height:1.6}
.btn{display:inline-block;background:linear-gradient(135deg,#0088ff,#0066cc);color:#fff;padding:15px 48px;border-radius:10px;text-decoration:none;font-size:17px;font-weight:500;transition:all .3s;box-shadow:0 4px 15px rgba(0,136,255,.3)}
.btn:hover{background:linear-gradient(135deg,#1a94ff,#0077ee);transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,136,255,.4)}
.footer{margin-top:32px;color:#556;font-size:12px}
.error{background:rgba(255,107,107,.15);color:#ff6b6b;padding:12px;border-radius:8px;margin-bottom:24px;font-size:14px}
</style></head>
<body><div class="card">
<div class="logo">🤖</div>
<h1>迦智诊断助手</h1>
<p class="subtitle">智能故障诊断 · 知识驱动分析<br>请使用钉钉扫码登录</p>
{error_html}
<a class="btn" href="/auth/login">🔐 钉钉账号登录</a>
<div class="footer">迦智科技 · 技术支持诊断系统</div>
</div></body></html>"""


def _login_html(error: str = "") -> str:
    err = f'<div class="error">{error}</div>' if error else ""
    return _LOGIN_PAGE.replace("{error_html}", err)


_ERROR_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>登录失败</title>
<style>body{font-family:sans-serif;background:#1a1a2e;color:#eee;display:flex;justify-content:center;align-items:center;min-height:100vh}
.card{background:#16213e;border-radius:16px;padding:48px;text-align:center;max-width:400px}h2{color:#ff6b6b}a{color:#0a7cff}</style></head>
<body><div class="card"><h2>登录失败</h2><p>{msg}</p><br><a href="/">重新登录</a></div></body></html>"""


def _error_html(msg: str) -> str:
    return _ERROR_PAGE.replace("{msg}", msg)


_TERMINAL_PAGE = """<!DOCTYPE html><html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>迦智诊断助手 - {user_name}</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;overflow:hidden;background:#0d1117}
.toolbar{height:36px;background:#161b22;display:flex;align-items:center;padding:0 12px;border-bottom:1px solid #21262d;gap:12px;position:relative;z-index:100}
.toolbar .title{color:#c9d1d9;font-size:13px;font-weight:500;flex:1}
.toolbar .user{color:#8b949e;font-size:13px}
.toolbar .logout{color:#f85149;font-size:12px;text-decoration:none;padding:4px 10px;border-radius:4px;border:1px solid #f8514940;cursor:pointer}
.toolbar .logout:hover{background:#f8514920}
#terminal-frame{position:absolute;top:36px;left:0;width:100%;height:calc(100% - 36px);border:none}
</style></head>
<body>
<div class="toolbar"><span class="title">🔧 迦智诊断助手</span><span class="user">👤 {user_name}</span><a class="logout" href="/logout">退出</a></div>
<iframe id="terminal-frame" src="/ttyd/"></iframe>
</body></html>"""


def _terminal_html(user_name: str) -> str:
    return _TERMINAL_PAGE.replace("{user_name}", user_name)


# ═══════════════════════════════════════════════════════════════════════
# TTYD reverse proxy — 透传 HTTP 和 WebSocket 到 ttyd (:5434)
# ═══════════════════════════════════════════════════════════════════════
def _proxy_http_to_ttyd(handler, method: str | None = None) -> None:
    path = handler.path
    if path.startswith("/ttyd"):
        path = path[5:] or "/"

    conn = http.client.HTTPConnection("127.0.0.1", TTYD_PORT, timeout=30)
    headers = {k: v for k, v in handler.headers.items()
               if k.lower() not in ("host", "connection", "proxy-connection", "cookie")}
    headers["Host"] = f"127.0.0.1:{TTYD_PORT}"

    body = None
    cl = handler.headers.get("Content-Length")
    if cl:
        try:
            body = handler.rfile.read(int(cl))
        except Exception:
            body = None

    try:
        conn.request(method or handler.command, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        handler.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() in ("transfer-encoding", "connection"):
                continue
            handler.send_header(k, v)
        handler.end_headers()
        handler.wfile.write(data)
    except Exception as e:
        _log(f"ttyd proxy error: {e}")
        handler.send_response(502)
        handler.end_headers()
    finally:
        conn.close()


def _proxy_ws_to_ttyd(handler) -> None:
    client = handler.connection
    backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    backend.settimeout(30)
    try:
        backend.connect(("127.0.0.1", TTYD_PORT))
    except Exception as e:
        _log(f"ws connect error: {e}")
        handler.send_response(502)
        handler.end_headers()
        return

    path = handler.path
    if path.startswith("/ttyd"):
        path = path[5:] or "/"

    req_line = f"GET {path} HTTP/1.1\r\n"
    hdrs = ""
    for k, v in handler.headers.items():
        kl = k.lower()
        if kl in ("host", "connection", "proxy-connection", "cookie", "origin"):
            continue
        hdrs += f"{k}: {v}\r\n"
    hdrs += f"Host: 127.0.0.1:{TTYD_PORT}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n"

    try:
        backend.sendall((req_line + hdrs).encode())
    except Exception:
        backend.close()
        return

    resp_data = b""
    try:
        while b"\r\n\r\n" not in resp_data:
            chunk = backend.recv(4096)
            if not chunk:
                break
            resp_data += chunk
            if len(resp_data) > 65536:
                break
    except Exception:
        backend.close()
        return

    status = 500
    try:
        status = int(resp_data.decode("latin-1").split(" ")[1])
    except Exception:
        pass

    handler.wfile.write(resp_data)
    handler.wfile.flush()
    if status != 101:
        backend.close()
        return

    def _pipe(src, dst):
        try:
            while True:
                data = src.recv(8192)
                if not data:
                    break
                dst.sendall(data)
        except Exception:
            pass
        finally:
            try:
                dst.close()
            except Exception:
                pass

    t1 = threading.Thread(target=_pipe, args=(client, backend), daemon=True)
    t2 = threading.Thread(target=_pipe, args=(backend, client), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=7200)
    t2.join(timeout=7200)


# ═══════════════════════════════════════════════════════════════════════
# HTTP Handler — 对应 management-system 的 LoginPage + authStore
# ═══════════════════════════════════════════════════════════════════════
class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        _log(f"{self.client_address[0]} {fmt % args}")

    # ── helpers ──────────────────────────────────────────────────
    def _html(self, code: int, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, extra_headers: list[tuple[str, str]] | None = None) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        if extra_headers:
            for k, v in extra_headers:
                self.send_header(k, v)
        self.end_headers()

    def _unauthorized(self, msg: str = "请先登录") -> None:
        self._html(401, _login_html(msg))

    # ── route dispatch ───────────────────────────────────────────
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = urllib.parse.parse_qs(parsed.query)

        # ── / ────────────────────────────────────────────────
        if path == "/":
            cookie = self.headers.get("Cookie", "")
            user = _verify_session(cookie)
            if user:
                self._html(200, _terminal_html(user.get("name", "用户")))
            else:
                self._html(200, _login_html())
            return

        # ── /auth/login ──────────────────────────────────────
        # 对应 management-system: LoginPage.handleLogin → GET /auth/dingtalk/url → window.location.href
        if path == "/auth/login":
            url = _build_oauth_url()
            if url:
                self._redirect(url)
            else:
                self._html(500, _error_html("无法获取钉钉登录链接，请检查后端服务是否正常"))
            return

        # ── /auth/callback ───────────────────────────────────
        # 钉钉 OAuth 回调 → POST /auth/get_token 换 session → 透传 Set-Cookie
        if path == "/auth/callback":
            auth_code = (qs.get("authCode", [""])[0] or qs.get("code", [""])[0]).strip()
            state = (qs.get("state", [""])[0]).strip()

            if not auth_code:
                self._html(400, _error_html("缺少认证参数"))
                return
            if not state:
                self._html(400, _error_html("缺少安全校验参数"))
                return
            if not _validate_oauth_state(state):
                _log(f"invalid/expired oauth state: {state[:8]}...")
                self._html(400, _error_html("登录请求已过期，请返回重新登录"))
                return

            # 用 authCode 换 Flask session（后端自动 Set-Cookie）
            # 对应 management-system: auth_dingtalk_callback → _session_from_dingtalk_auth_code → session["auth_user"]
            status, data, resp_hdrs = _call_backend(
                "POST", "/auth/get_token",
                body={"code": auth_code},
            )

            if status != 200:
                err = data.get("error", "钉钉认证失败")
                _log(f"get_token failed: {err}")
                self._html(401, _error_html(f"登录失败: {err}"))
                return

            user = data.get("data", {}).get("user") or data.get("data", {})
            user_id = str(user.get("user_id", user.get("id", "unknown")))
            user_name = str(user.get("name", user_id))

            _log(f"LOGIN: {user_name} ({user_id})")
            _write_pending_user(user_id, user_name)

            # 透传 Flask 的 Set-Cookie 到浏览器
            # Flask session cookie 格式: session=<signed>; HttpOnly; Path=/; SameSite=Lax
            extra = []
            set_cookie = resp_hdrs.get("set-cookie", "")
            if set_cookie:
                extra.append(("Set-Cookie", set_cookie))
                _log(f"session cookie set ({len(set_cookie)} bytes)")

            self._redirect("/", extra_headers=extra if extra else None)
            return

        # ── /logout ─────────────────────────────────────────
        # 对应 management-system: authStore.logout → POST /auth/logout → 清 session
        if path == "/logout":
            cookie = self.headers.get("Cookie", "")
            user = _verify_session(cookie)
            if user:
                _log(f"LOGOUT: {user.get('name', '?')} ({user.get('user_id', '?')})")

            # 调后端清除 session（即使失败也不影响本地清理）
            try:
                _call_backend("POST", "/auth/logout", cookie=cookie)
            except Exception:
                pass

            # 清除浏览器 cookie
            self._redirect("/", extra_headers=[
                ("Set-Cookie", "session=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; SameSite=Lax"),
            ])
            return

        # ── ttyd proxy — 需要登录 ────────────────────────────
        if path.startswith("/ttyd") or path == "/token" or path.startswith("/ws"):
            cookie = self.headers.get("Cookie", "")
            user = _verify_session(cookie)
            if not user:
                self._unauthorized()
                return

            upgrade = self.headers.get("Upgrade", "").lower()
            if upgrade == "websocket":
                _write_pending_user(
                    str(user.get("user_id", user.get("id", ""))),
                    str(user.get("name", "用户")),
                )
                _proxy_ws_to_ttyd(self)
            else:
                _proxy_http_to_ttyd(self)
            return

        # ── 其他路径 — 已登录则代理到 ttyd，否则显示登录页 ──
        cookie = self.headers.get("Cookie", "")
        if _verify_session(cookie):
            _proxy_http_to_ttyd(self)
        else:
            self._html(200, _login_html())

    def do_POST(self) -> None:
        cookie = self.headers.get("Cookie", "")
        if not _verify_session(cookie):
            self._unauthorized()
            return
        _proxy_http_to_ttyd(self, method="POST")

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    _log(f"DiagKit Auth Proxy v4 (Flask session passthrough)")
    _log(f"proxy  : http://{SERVER_IP}:{PROXY_PORT}")
    _log(f"ttyd   : 127.0.0.1:{TTYD_PORT}")
    _log(f"backend: {MGMT_API}")
    _log(f"callback: {CALLBACK_URL}")

    # ThreadingHTTPServer: 支持并发请求（Python 3.7+）
    class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
        daemon_threads = True

    httpd = ThreadingHTTPServer(("0.0.0.0", PROXY_PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _log("shutting down")
        httpd.server_close()
