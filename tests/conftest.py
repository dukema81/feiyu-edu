# -*- coding: utf-8 -*-
"""飞育测试夹具：临时库 + 进程内服务（session 级）。"""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

_tmp = tempfile.mkdtemp(prefix="feiyu_test_")
os.environ["EDU_DB"] = os.path.join(_tmp, "test.db")
os.environ["EDU_PORT"] = "0"

import db            # noqa: E402
import seed as seedmod  # noqa: E402
import server        # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def svc():
    db.init()
    seedmod.seed()
    srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield {"base": "http://127.0.0.1:%d" % srv.server_address[1]}
    srv.shutdown()


@pytest.fixture(scope="session")
def admin_token(svc):
    code, data = req("POST", "/api/auth/login",
                     {"username": "admin", "password": "123456"})
    assert code == 200
    return json.loads(data)["data"]["token"]


@pytest.fixture(scope="session")
def H(admin_token):
    return {"Authorization": "Bearer " + admin_token}


def req(method, path, body=None, headers=None, base="http://127.0.0.1:0"):
    if base == "http://127.0.0.1:0":
        base = _base[0]
    path = urllib.parse.quote(path, safe="/?=&%")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method,
                               headers={"Content-Type": "application/json",
                                        **(headers or {})})
    try:
        resp = urllib.request.urlopen(r, timeout=10)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


_base = [None]


@pytest.fixture(scope="session", autouse=True)
def _wire(svc):
    _base[0] = svc["base"]
    yield
