# -*- coding: utf-8 -*-
"""飞育线上冒烟：python tools/smoke_api.py --base http://host:port[/edu]

不依赖 pytest，覆盖关键只读链路 + 登录 + 内核计算接口，部署后立即验证。
"""
import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),               # 绕过系统代理，直连
    urllib.request.HTTPSHandler(context=CTX))

PASS = []
FAIL = []


def call(base, method, path, body=None, token=None, raw=False):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=h, method=method)
    try:
        with OPENER.open(req, timeout=15) as r:
            b = r.read()
            return r.status, b if raw else json.loads(b or b"{}")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"{}")
        except Exception:                                 # noqa: BLE001
            return e.code, {}


def check(name, cond, extra=""):
    if cond:
        PASS.append(name)
        print("  OK   " + name)
    else:
        FAIL.append(name)
        print("  FAIL " + name + " " + str(extra)[:160])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    a = ap.parse_args()
    base = a.base.rstrip("/")

    st, r = call(base, "GET", "/api/health")
    check("health", st == 200, (st, str(r)[:120]))

    st, r = call(base, "POST", "/api/auth/login",
                 {"username": "admin", "password": "123456"})
    check("login", st == 200, (st, str(r)[:120]))
    tk = (r.get("data") or {}).get("token", "")

    st, r = call(base, "GET", "/api/dashboard", token=tk)
    check("dashboard", st == 200 and (r.get("data") or {}).get("kpi"), (st, ""))

    for p in ("/api/schools", "/api/teachers", "/api/classes", "/api/courses",
              "/api/policies"):
        st, r = call(base, "GET", p, token=tk)
        n = ((r.get("data") or {}).get("total")) if isinstance(r.get("data"), dict) else 0
        check(p, st == 200 and (n or 0) > 0, (st, n))

    st, r = call(base, "GET", "/api/students", token=tk)
    check("students", st == 200 and (r.get("data") or {}).get("total", 0) > 0, st)

    st, r = call(base, "GET", "/api/schedule/conflicts", token=tk)
    check("schedule-conflicts", st == 200 and "list" in (r.get("data") or {}), st)

    st, r = call(base, "GET", "/api/scores/analysis", token=tk)
    d = r.get("data") or {}
    check("scores-analysis", st == 200 and d.get("total", 0) > 0, st)

    st, r = call(base, "GET", "/api/scores/rank?class_no=CLS001", token=tk)
    check("scores-rank", st == 200 and (r.get("data") or {}).get("total", 0) > 0, st)

    st, r = call(base, "GET", "/api/scores/transcript/ST0001", token=tk)
    check("transcript", st == 200 and (r.get("data") or {}).get("student"), st)

    st, r = call(base, "GET", "/api/attendance/stats?days=30", token=tk)
    check("attendance-stats", st == 200 and (r.get("data") or {}).get("overall"), st)

    st, r = call(base, "GET", "/api/fees/summary", token=tk)
    d = r.get("data") or {}
    check("fee-summary", st == 200 and d.get("bills", 0) > 0, (st, d.get("bills")))

    st, r = call(base, "GET", "/api/risks", token=tk)
    check("risks", st == 200, st)

    st, r = call(base, "GET", "/api/transfers", token=tk)
    check("transfers", st == 200, st)

    for p in ("/api/reports/summary", "/api/reports/trend", "/api/reports/attendance",
              "/api/reports/fee", "/api/reports/grade-dist"):
        st, r = call(base, "GET", p, token=tk)
        check(p, st == 200, st)

    st, r = call(base, "GET", "/api/reports/export", token=tk, raw=True)
    check("export-csv", st == 200 and isinstance(r, bytes) and len(r) > 300,
          (st, len(r) if isinstance(r, bytes) else type(r)))

    st, r = call(base, "GET", "/api/apidoc")
    check("apidoc", st == 200 and len((r.get("data") or {}).get("routes", [])) >= 60, st)

    st, r = call(base, "GET", "/api/sync/version", token=tk)
    check("sync-version", st == 200, st)

    # 静态页
    st, r = call(base, "GET", "/index.html", raw=True)
    check("index.html", st == 200 and "飞育".encode() in r, st)
    st, r = call(base, "GET", "/login.html", raw=True)
    check("login.html", st == 200, st)

    print("\n==== 冒烟  PASS=%d  FAIL=%d ====" % (len(PASS), len(FAIL)))
    sys.exit(0 if not FAIL else 1)


if __name__ == "__main__":
    main()
