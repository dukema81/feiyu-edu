# -*- coding: utf-8 -*-
"""飞育 API 集成测试。"""
import json

from conftest import req


def j(b):
    return json.loads(b)


# ---------------- 认证 ----------------
def test_login_ok(svc):
    st, b = req("POST", "/api/auth/login",
                {"username": "admin", "password": "123456"})
    assert st == 200 and j(b)["code"] == 200
    assert j(b)["data"]["token"]


def test_login_bad(svc):
    st, b = req("POST", "/api/auth/login", {"username": "admin", "password": "x"})
    assert st == 401


def test_me_and_change_pwd(svc, H):
    st, b = req("GET", "/api/auth/me", None, H)
    assert st == 200 and j(b)["data"]["role"] == "admin"


def test_unauthorized(svc):
    st, b = req("GET", "/api/students")
    assert st == 401


def test_apikey_channel(svc, H):
    st, b = req("POST", "/api/api-keys/create", {"name": "测试密钥", "scope": "read"}, H)
    key = j(b)["data"]["key"]
    st, b = req("GET", "/api/students", None, {"X-Edu-Key": key})
    assert st == 200 and j(b)["code"] == 200


# ---------------- RBAC ----------------
def test_teacher_cannot_fee_write(svc):
    st, b = req("POST", "/api/auth/login", {"username": "t01", "password": "123456"})
    h = {"Authorization": "Bearer " + j(b)["data"]["token"]}
    st, b = req("POST", "/api/fees/save", {"student_no": "ST0001", "amount": 100}, h)
    assert st == 403


def test_finance_can_fee(svc):
    st, b = req("POST", "/api/auth/login", {"username": "chenmm", "password": "123456"})
    h = {"Authorization": "Bearer " + j(b)["data"]["token"]}
    st, b = req("GET", "/api/fees/summary", None, h)
    assert st == 200


def test_reader_readonly(svc):
    st, b = req("POST", "/api/auth/login", {"username": "reader01", "password": "123456"})
    h = {"Authorization": "Bearer " + j(b)["data"]["token"]}
    st, b = req("GET", "/api/reports/summary", None, h)
    assert st == 200
    st, b = req("POST", "/api/scores/save", {"student_no": "ST0001", "course": "KC001",
                                             "score": 90}, h)
    assert st == 403


# ---------------- 组织域 ----------------
def test_dashboard(svc, H):
    st, b = req("GET", "/api/dashboard", None, H)
    d = j(b)["data"]
    assert st == 200 and d["kpi"]["students"] > 0 and "trend" in d


def test_schools(svc, H):
    st, b = req("GET", "/api/schools", None, H)
    lst = j(b)["data"]["list"]
    assert st == 200 and len(lst) >= 2
    st, b = req("GET", "/api/schools/S01", None, H)
    assert j(b)["data"]["stats"]["students"] > 0


def test_teachers_classes_courses(svc, H):
    for path in ("/api/teachers", "/api/classes", "/api/courses"):
        st, b = req("GET", path, None, H)
        assert st == 200 and (j(b)["data"]["total"] or 0) > 0, path


# ---------------- 学生流 ----------------
def test_student_crud(svc, H):
    st, b = req("POST", "/api/students/save",
                {"name": "集成测试生", "class_no": "CLS001", "grade": "高一",
                 "guardian_phone": "13900001111"}, H)
    assert st == 200
    no = j(b)["data"]["no"]
    st, b = req("GET", "/api/students/" + no, None, H)
    assert j(b)["data"]["name"] == "集成测试生"
    st, b = req("POST", "/api/students/save",
                {"no": no, "name": "集成测试生改", "class_no": "CLS001", "grade": "高一"}, H)
    assert st == 200
    st, b = req("POST", "/api/students/status", {"no": no, "status": "休学"}, H)
    assert j(b)["data"]["status"] == "休学"
    st, b = req("POST", "/api/students/status", {"no": no, "status": "X状态"}, H)
    assert st == 400


def test_student_validation(svc, H):
    st, b = req("POST", "/api/students/save", {"name": ""}, H)
    assert st == 400


# ---------------- 排课 ----------------
def test_schedule_conflict_api(svc, H):
    st, b = req("GET", "/api/schedule/conflicts", None, H)
    assert st == 200 and "list" in j(b)["data"]
    st, b = req("POST", "/api/schedule/save",
                {"class_no": "CLS001", "course": "KC009", "teacher": "", "weekday": 7,
                 "slot": 1}, H)
    assert st == 200


def test_schedule_bad_slot(svc, H):
    st, b = req("POST", "/api/schedule/save",
                {"class_no": "CLS001", "course": "KC001", "weekday": 9, "slot": 1}, H)
    assert st == 400


# ---------------- 成绩流 ----------------
def test_score_flow(svc, H):
    st, b = req("POST", "/api/scores/save", {"items": [
        {"student_no": "ST0001", "course": "KC001", "exam": "月考", "score": 88},
        {"student_no": "ST0002", "course": "KC001", "exam": "月考", "score": 92},
    ]}, H)
    assert st == 200 and j(b)["data"]["saved"] == 2
    st, b = req("GET", "/api/scores?exam=月考", None, H)
    assert len(j(b)["data"]["list"]) == 2
    st, b = req("POST", "/api/scores/save", {"items": [
        {"student_no": "ST0001", "course": "KC001", "score": 999}]}, H)
    assert st == 400


def test_score_analysis_rank_transcript(svc, H):
    st, b = req("GET", "/api/scores/analysis", None, H)
    d = j(b)["data"]
    assert st == 200 and d["total"] > 0 and d["overall"]["count"] > 0
    st, b = req("GET", "/api/scores/rank?class_no=CLS001", None, H)
    lst = j(b)["data"]["list"]
    assert lst and lst[0]["rank"] == 1
    st, b = req("GET", "/api/scores/transcript/ST0001", None, H)
    d = j(b)["data"]
    assert st == 200 and d["student"]["no"] == "ST0001" and "rank" in d and "weighted" in d


# ---------------- 考勤流 ----------------
def test_attendance_flow(svc, H):
    st, b = req("POST", "/api/attendance/save", {"items": [
        {"student_no": "ST0001", "status": "迟到"},
        {"student_no": "ST0002", "status": "旷课"},
    ]}, H)
    assert st == 200
    st, b = req("POST", "/api/attendance/save", {"student_no": "ST0001", "status": "出差"}, H)
    assert st == 400
    st, b = req("GET", "/api/attendance/stats?days=30&class_no=CLS001", None, H)
    assert st == 200 and "overall" in j(b)["data"]


# ---------------- 缴费流 ----------------
def test_fee_flow(svc, H):
    st, b = req("POST", "/api/fees/save", {"student_no": "ST0001", "amount": 6200,
                                           "discount": 10, "due_date": "2026-09-15"}, H)
    no = j(b)["data"]["no"]
    assert st == 200 and j(b)["data"]["payable"] == 5580.0
    st, b = req("POST", "/api/fees/pay", {"no": no, "amount": 1000}, H)
    assert j(b)["data"]["status"] == "部分缴费"
    st, b = req("POST", "/api/fees/pay", {"no": no, "amount": 5000}, H)
    assert j(b)["data"]["status"] == "已缴清"
    st, b = req("POST", "/api/fees/pay", {"no": no, "amount": 100}, H)
    assert j(b)["data"].get("noop") is True
    st, b = req("GET", "/api/fees/summary", None, H)
    assert st == 200 and j(b)["data"]["total"] > 0


def test_fee_validation(svc, H):
    st, b = req("POST", "/api/fees/save", {"student_no": "", "amount": -5}, H)
    assert st == 400


# ---------------- 学籍变动流 ----------------
def test_transfer_flow(svc, H):
    st, b = req("POST", "/api/transfers/save", {"student_no": "ST0003", "kind": "转班",
                                                "to_value": "CLS002"}, H)
    no = j(b)["data"]["no"]
    assert j(b)["data"]["status"] == "待审批"
    st, b = req("POST", "/api/transfers/approve", {"no": no}, H)
    assert j(b)["data"]["status"] == "已审批"
    st, b = req("GET", "/api/students/ST0003", None, H)
    assert j(b)["data"]["class_no"] == "CLS002"
    st, b = req("POST", "/api/transfers/approve", {"no": no}, H)
    assert st == 400


# ---------------- 风险/报表 ----------------
def test_risk_scan_and_close(svc, H):
    st, b = req("POST", "/api/risks/scan", {}, H)
    assert st == 200 and "count" in j(b)["data"]
    st, b = req("GET", "/api/risks?status=待处理", None, H)
    lst = j(b)["data"]["list"]
    assert lst
    st, b = req("POST", "/api/risks/close", {"id": lst[0]["id"]}, H)
    assert j(b)["data"]["status"] == "已处理"


def test_reports(svc, H):
    st, b = req("GET", "/api/reports/summary", None, H)
    d = j(b)["data"]
    assert st == 200 and "teaching" in d and "academic" in d and "fee" in d
    st, b = req("GET", "/api/reports/grade-dist", None, H)
    assert st == 200 and j(b)["data"]["count"] > 0
    st, b = req("GET", "/api/reports/trend", None, H)
    assert st == 200


def test_export_csv(svc, H):
    st, b = req("GET", "/api/reports/export", None, H)
    assert st == 200 and "学号".encode() in b


# ---------------- 同步/幂等 ----------------
def test_sync(svc, H):
    st, b = req("GET", "/api/sync/version", None, H)
    v1 = j(b)["data"]["students"]
    st, b = req("GET", "/api/sync?entities=students&version=students:0", None, H)
    assert st == 200 and j(b)["data"]["entities"]["students"]["data"]
    st, b = req("POST", "/api/students/save", {"name": "同步测试生", "class_no": "CLS001",
                                               "grade": "高一"}, H)
    st, b = req("GET", "/api/sync/version", None, H)
    assert j(b)["data"]["students"] == v1 + 1


def test_idempotency(svc, H):
    h = dict(H)
    h["Idempotency-Key"] = "pytest-idem-001"
    body = {"title": "幂等公告测试"}
    st1, b1 = req("POST", "/api/notices/save", body, h)
    st2, b2 = req("POST", "/api/notices/save", body, h)
    assert st1 == 200 and st2 == 200
    st, b = req("GET", "/api/notices", None, H)
    assert sum(1 for n in j(b)["data"] if n["title"] == "幂等公告测试") == 1


def test_apidoc_and_static(svc, H):
    st, b = req("GET", "/api/apidoc", None, H)
    assert st == 200 and len(j(b)["data"]["routes"]) >= 60
    st, b = req("GET", "/index.html")
    assert st == 200 and "飞育".encode() in b
    st, b = req("GET", "/")
    assert st == 200
