# -*- coding: utf-8 -*-
"""飞育教育管理系统 · HTTP 服务层

零依赖：http.server.ThreadingHTTPServer + sqlite3，Python 3.9+ 即可运行。
统一响应 {code, message, data}，code 与 HTTP 状态码一致。
五通道鉴权 / 幂等 / 增量同步 / RBAC 与飞税同范式。
"""
import hashlib
import json
import os
import re
import sys
import time
import traceback
import urllib.parse
from decimal import Decimal

D = Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db                                           # noqa: E402
import edu as K                                     # noqa: E402
import seed as seedmod                              # noqa: E402

BRAND = "飞育教育管理系统"
VERSION = "1.0.0"
PORT = int(os.environ.get("EDU_PORT") or 8025)
PREFIX = (os.environ.get("EDU_PREFIX") or "").rstrip("/")
FRONTEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

CURRENT_TERM = "2026-2027-1"


# ==================================================== 工具
class ApiError(Exception):
    def __init__(self, message, code=400):
        self.message = message
        self.code = code
        super().__init__(message)


def sha(s):
    return hashlib.sha256(str(s).encode()).hexdigest()


def num(x, default=0.0):
    try:
        return float(x)
    except Exception:                                    # noqa: BLE001
        return default


def intn(x, default=0):
    try:
        return int(x)
    except Exception:                                    # noqa: BLE001
        return default


def jdumps(o):
    return json.dumps(o, ensure_ascii=False, default=str)


def has_perm(u, need):
    return K.has_perm(u.get("perms") or [], need)


def need(u, perm):
    if not has_perm(u, perm):
        raise ApiError("无权限：需要 %s" % perm, 403)


def log(u, action, target="", detail="", ip=""):
    db.run("INSERT INTO logs (ts,username,action,target,detail,ip) VALUES (?,?,?,?,?,?)",
           (db.now(), (u or {}).get("username", "-"), action, target,
            str(detail)[:800], ip))


def listwrap(items):
    items = items or []
    return {"list": items, "total": len(items)}


# ==================================================== 鉴权
ROLE_LABELS = {
    "admin": "系统管理员", "principal": "校长", "dean": "教务/学生处",
    "teacher": "教师", "finance": "财务", "reader": "只读用户",
}


def build_user(r):
    perms = sorted(K.ROLE_PERMS.get(r.get("role") or "reader", []))
    dept = db.one("SELECT name FROM depts WHERE code=?", (r.get("dept") or "",))
    return {
        "username": r["username"], "name": r["name"], "role": r["role"],
        "roleLabel": ROLE_LABELS.get(r["role"], r["role"]),
        "dept": r.get("dept") or "", "deptName": (dept or {}).get("name", ""),
        "title": r.get("title") or "", "phone": r.get("phone") or "",
        "email": r.get("email") or "", "perms": perms,
    }


def user_by_token(value):
    if not value:
        return None
    tok = str(value)
    if tok.lower().startswith("bearer "):
        tok = tok[7:].strip()
    r = db.one("SELECT u.* FROM tokens t JOIN users u ON u.username=t.username "
               "WHERE t.token=?", (tok,))
    if not r or r.get("status") != "启用":
        return None
    return build_user(r)


def user_by_apikey(value):
    if not value:
        return None
    h = sha(value)
    k = db.one("SELECT * FROM api_keys WHERE key_hash=? AND status='启用'", (h,))
    if not k:
        return None
    db.run("UPDATE api_keys SET last_used=? WHERE id=?", (db.now(), k["id"]))
    scope = k.get("scope") or "read"
    perms = ["edu.read", "report.read", "policy.read", "dashboard.read"]
    if scope in ("write", "full"):
        perms += ["score.write", "fee.write", "fee.read", "edu.write"]
    if scope == "full":
        perms += ["risk.read", "org.read", "system.read"]
    return {"username": "__apikey__", "name": k["name"], "role": "apikey",
            "roleLabel": "接口密钥", "dept": "", "deptName": "",
            "perms": perms, "api_key_id": k["id"]}


# ==================================================== 认证
def api_health(u, b, q):
    return {
        "brand": BRAND, "version": VERSION, "routes": len(ROUTES),
        "users": db.val("SELECT COUNT(*) FROM users", (), 0),
        "schools": db.val("SELECT COUNT(*) FROM schools", (), 0),
        "students": db.val("SELECT COUNT(*) FROM students WHERE status='在读'", (), 0),
        "teachers": db.val("SELECT COUNT(*) FROM teachers WHERE status='在职'", (), 0),
        "classes": db.val("SELECT COUNT(*) FROM classes", (), 0),
        "courses": db.val("SELECT COUNT(*) FROM courses", (), 0),
        "term": CURRENT_TERM,
        "time": db.now(),
    }


def api_login(u, b, q):
    un = (b.get("username") or "").strip()
    pw = b.get("password") or ""
    if not un or not pw:
        raise ApiError("用户名与密码必填", 401)
    r = db.one("SELECT * FROM users WHERE username=?", (un,))
    if not r or r.get("pwd") != sha(pw):
        raise ApiError("用户名或密码错误", 401)
    if r.get("status") != "启用":
        raise ApiError("账号已停用", 403)
    tok = sha(un + str(time.time()) + os.urandom(8).hex())
    db.run("INSERT INTO tokens (token,username,created_at) VALUES (?,?,?)",
           (tok, un, db.now()))
    me = build_user(r)
    log(me, "登录", un)
    return {"token": tok, "username": un, "name": r["name"], "role": r["role"],
            "roleLabel": me["roleLabel"], "dept": r.get("dept") or ""}


def api_logout(u, b, q):
    tok = (b.get("token") or "").strip()
    if tok:
        db.run("DELETE FROM tokens WHERE token=?", (tok,))
    return {"ok": True}


def api_me(u, b, q):
    return u


def api_change_pwd(u, b, q):
    old = b.get("old_password") or ""
    new = b.get("new_password") or ""
    if len(new) < 6:
        raise ApiError("新密码至少 6 位")
    r = db.one("SELECT * FROM users WHERE username=?", (u["username"],))
    if not r or r.get("pwd") != sha(old):
        raise ApiError("原密码不正确")
    db.run("UPDATE users SET pwd=? WHERE username=?", (sha(new), u["username"]))
    db.run("DELETE FROM tokens WHERE username=?", (u["username"],))
    log(u, "修改密码", u["username"])
    return {"ok": True, "relogin": True}


# ==================================================== 工作台
def api_dashboard(u, b, q):
    need(u, "dashboard.read")
    term = (q.get("term") or [None])[0] or CURRENT_TERM
    kpi = {
        "schools": db.val("SELECT COUNT(*) FROM schools WHERE status='启用'", (), 0),
        "students": db.val("SELECT COUNT(*) FROM students WHERE status='在读'", (), 0),
        "teachers": db.val("SELECT COUNT(*) FROM teachers WHERE status='在职'", (), 0),
        "classes": db.val("SELECT COUNT(*) FROM classes WHERE status='在读'", (), 0),
        "courses": db.val("SELECT COUNT(*) FROM courses WHERE status='开课'", (), 0),
    }
    # 当期收费
    fee_amt = num(db.val("SELECT SUM(amount*(100-discount)/100) FROM fees WHERE term=?", (term,), 0))
    fee_paid = num(db.val("SELECT SUM(paid_amount) FROM fees WHERE term=?", (term,), 0))
    kpi["feeAmount"] = K.money(fee_amt)
    kpi["feePaid"] = K.money(fee_paid)
    kpi["feeOverdue"] = db.val(
        "SELECT COUNT(*) FROM fees WHERE status!='已缴清' AND due_date!='' AND due_date<?",
        (db.today(),), 0)
    # 当期均分
    avg = num(db.val("SELECT AVG(score) FROM scores WHERE term=?", (term,), 0))
    kpi["avgScore"] = round(avg, 1)
    kpi["passRate"] = num(db.val(
        "SELECT 100.0*SUM(CASE WHEN score>=60 THEN 1 ELSE 0 END)/COUNT(*) "
        "FROM scores WHERE term=?", (term,), 0))
    # 出勤率（近 30 天）
    att = K.attendance_stats(db.rows(
        "SELECT status FROM attendance WHERE adate>=?",
        (time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * 30)),)))
    kpi["attendanceRate"] = att["rate"]
    kpi["riskOpen"] = db.val("SELECT COUNT(*) FROM risks WHERE status='待处理'", (), 0)
    kpi["riskHigh"] = db.val(
        "SELECT COUNT(*) FROM risks WHERE status='待处理' AND level='险'", (), 0)

    # 近 6 次考试均分趋势
    trend = []
    for exam in ("期中", "期末"):
        a = num(db.val("SELECT AVG(score) FROM scores WHERE term=? AND exam=?", (term, exam), 0))
        trend.append({"exam": exam, "avg": round(a, 1)})
    # 学科均分
    by_course = db.rows(
        "SELECT course AS name, ROUND(AVG(score),1) AS avg, COUNT(*) AS cnt "
        "FROM scores WHERE term=? GROUP BY course ORDER BY avg DESC", (term,))
    # 待办
    pending_fees = db.rows(
        "SELECT no,student_no,amount,paid_amount,due_date,status FROM fees "
        "WHERE status!='已缴清' ORDER BY due_date LIMIT 8")
    pending_transfers = db.rows(
        "SELECT no,student_no,kind,status,effect_date FROM transfers "
        "WHERE status='待审批' LIMIT 8")
    return {
        "term": term, "kpi": kpi, "trend": trend, "byCourse": by_course,
        "pendingFees": pending_fees, "pendingTransfers": pending_transfers,
        "notices": db.rows("SELECT id,title,created_at,top FROM notices "
                           "ORDER BY top DESC, id DESC LIMIT 4"),
        "risks": db.rows("SELECT id,school,level,title,status FROM risks "
                         "WHERE status='待处理' ORDER BY weight DESC LIMIT 5"),
    }


# ==================================================== 校区
def api_schools(u, b, q):
    need(u, "edu.read")
    kw = (q.get("kw") or [""])[0]
    sql = "SELECT * FROM schools WHERE 1=1"
    args = []
    if kw:
        sql += " AND (name LIKE ? OR code LIKE ? OR city LIKE ?)"
        args += ["%%%s%%" % kw] * 3
    sql += " ORDER BY code"
    return listwrap(db.rows(sql, tuple(args)))


def api_school_get(u, b, q, code):
    need(u, "edu.read")
    r = db.one("SELECT * FROM schools WHERE code=?", (code,))
    if not r:
        raise ApiError("校区不存在：%s" % code, 404)
    r["stats"] = {
        "students": db.val("SELECT COUNT(*) FROM students WHERE school=? AND status='在读'",
                           (code,), 0),
        "teachers": db.val("SELECT COUNT(*) FROM teachers WHERE school=? AND status='在职'",
                           (code,), 0),
        "classes": db.val("SELECT COUNT(*) FROM classes WHERE school=? AND status='在读'",
                          (code,), 0),
        "courses": db.val("SELECT COUNT(*) FROM courses WHERE school=?", (code,), 0),
    }
    return r


def api_school_save(u, b, q):
    need(u, "edu.write")
    b = b or {}
    if not (b.get("name") or "").strip():
        raise ApiError("校区名称必填")
    code = (b.get("code") or "").strip() or db.gen_no("schools", "S")
    exists = db.one("SELECT 1 FROM schools WHERE code=?", (code,))
    data = {
        "name": b["name"].strip(), "city": b.get("city") or "",
        "address": b.get("address") or "", "principal": b.get("principal") or "",
        "contact": b.get("contact") or "", "phone": b.get("phone") or "",
        "opened_at": b.get("opened_at") or "", "status": b.get("status") or "启用",
        "memo": b.get("memo") or "",
    }
    if exists:
        db.run("UPDATE schools SET name=?,city=?,address=?,principal=?,contact=?,phone=?,"
               "opened_at=?,status=?,memo=? WHERE code=?",
               (data["name"], data["city"], data["address"], data["principal"],
                data["contact"], data["phone"], data["opened_at"], data["status"],
                data["memo"], code))
    else:
        db.insert("schools", data | {"code": code, "created_at": db.now()})
    log(u, "校区保存", code)
    db.bumpsync("schools")
    return {"code": code}


# ==================================================== 教师
def api_teachers(u, b, q):
    need(u, "edu.read")
    kw = (q.get("kw") or [""])[0]
    school = (q.get("school") or [""])[0]
    sql = "SELECT * FROM teachers WHERE 1=1"
    args = []
    if kw:
        sql += " AND (name LIKE ? OR no LIKE ? OR subject LIKE ?)"
        args += ["%%%s%%" % kw] * 3
    if school:
        sql += " AND school=?"
        args.append(school)
    sql += " ORDER BY no"
    return listwrap(db.rows(sql, tuple(args)))


def api_teacher_get(u, b, q, no):
    need(u, "edu.read")
    r = db.one("SELECT * FROM teachers WHERE no=?", (no,))
    if not r:
        raise ApiError("教师不存在：%s" % no, 404)
    r["stats"] = {
        "courses": db.val("SELECT COUNT(*) FROM courses WHERE teacher=?", (no,), 0),
        "scheduleSlots": db.val("SELECT COUNT(*) FROM schedule WHERE teacher=?", (no,), 0),
        "classes": db.val("SELECT COUNT(DISTINCT class_no) FROM schedule WHERE teacher=?",
                          (no,), 0),
    }
    return r


def api_teacher_save(u, b, q):
    need(u, "edu.write")
    b = b or {}
    if not (b.get("name") or "").strip():
        raise ApiError("教师姓名必填")
    no = (b.get("no") or "").strip() or db.gen_no("teachers", "T")
    data = {
        "name": b["name"].strip(), "gender": b.get("gender") or "男",
        "school": b.get("school") or "S01", "subject": b.get("subject") or "",
        "title": b.get("title") or "教师", "phone": b.get("phone") or "",
        "email": b.get("email") or "", "hire_date": b.get("hire_date") or "",
        "status": b.get("status") or "在职", "memo": b.get("memo") or "",
    }
    if db.one("SELECT 1 FROM teachers WHERE no=?", (no,)):
        db.run("UPDATE teachers SET name=?,gender=?,school=?,subject=?,title=?,phone=?,"
               "email=?,hire_date=?,status=?,memo=? WHERE no=?",
               tuple(data[k] for k in ("name", "gender", "school", "subject", "title",
                                       "phone", "email", "hire_date", "status", "memo")) + (no,))
    else:
        db.insert("teachers", data | {"no": no, "created_at": db.now()})
    log(u, "教师保存", no)
    db.bumpsync("teachers")
    return {"no": no}


# ==================================================== 班级
def api_classes(u, b, q):
    need(u, "edu.read")
    kw = (q.get("kw") or [""])[0]
    grade = (q.get("grade") or [""])[0]
    sql = "SELECT * FROM classes WHERE 1=1"
    args = []
    if kw:
        sql += " AND (name LIKE ? OR no LIKE ?)"
        args += ["%%%s%%" % kw] * 2
    if grade:
        sql += " AND grade=?"
        args.append(grade)
    sql += " ORDER BY no"
    return listwrap(db.rows(sql, tuple(args)))


def api_class_get(u, b, q, no):
    need(u, "edu.read")
    r = db.one("SELECT * FROM classes WHERE no=?", (no,))
    if not r:
        raise ApiError("班级不存在：%s" % no, 404)
    stus = db.rows("SELECT no,name,gender,guardian,guardian_phone,status FROM students "
                   "WHERE class_no=? ORDER BY no", (no,))
    r["students"] = stus
    r["schedule"] = db.rows("SELECT * FROM schedule WHERE class_no=? AND term=? "
                            "ORDER BY weekday,slot", (no, r.get("term") or CURRENT_TERM))
    return r


def api_class_save(u, b, q):
    need(u, "edu.write")
    b = b or {}
    if not (b.get("name") or "").strip():
        raise ApiError("班级名称必填")
    no = (b.get("no") or "").strip() or db.gen_no("classes", "CLS")
    data = {
        "name": b["name"].strip(), "school": b.get("school") or "S01",
        "grade": b.get("grade") or "", "head_teacher": b.get("head_teacher") or "",
        "room": b.get("room") or "", "capacity": intn(b.get("capacity"), 45),
        "term": b.get("term") or CURRENT_TERM, "status": b.get("status") or "在读",
        "memo": b.get("memo") or "",
    }
    if db.one("SELECT 1 FROM classes WHERE no=?", (no,)):
        db.run("UPDATE classes SET name=?,school=?,grade=?,head_teacher=?,room=?,"
               "capacity=?,term=?,status=?,memo=? WHERE no=?",
               tuple(data[k] for k in ("name", "school", "grade", "head_teacher",
                                       "room", "capacity", "term", "status", "memo")) + (no,))
    else:
        db.insert("classes", data | {"no": no, "created_at": db.now()})
    db.run("UPDATE classes SET student_count=(SELECT COUNT(*) FROM students "
           "WHERE class_no=? AND status='在读') WHERE no=?", (no, no))
    log(u, "班级保存", no)
    db.bumpsync("classes")
    return {"no": no}


# ==================================================== 学生
def api_students(u, b, q):
    need(u, "edu.read")
    kw = (q.get("kw") or [""])[0]
    class_no = (q.get("class_no") or [""])[0]
    grade = (q.get("grade") or [""])[0]
    status = (q.get("status") or [""])[0]
    sql = "SELECT * FROM students WHERE 1=1"
    args = []
    if kw:
        sql += " AND (name LIKE ? OR no LIKE ? OR guardian LIKE ?)"
        args += ["%%%s%%" % kw] * 3
    if class_no:
        sql += " AND class_no=?"
        args.append(class_no)
    if grade:
        sql += " AND grade=?"
        args.append(grade)
    if status:
        sql += " AND status=?"
        args.append(status)
    sql += " ORDER BY no"
    return listwrap(db.rows(sql, tuple(args)))


def api_student_get(u, b, q, no):
    need(u, "edu.read")
    r = db.one("SELECT * FROM students WHERE no=?", (no,))
    if not r:
        raise ApiError("学生不存在：%s" % no, 404)
    scores = db.rows("SELECT * FROM scores WHERE student_no=? ORDER BY term,exam,id", (no,))
    r["scores"] = scores
    r["transcript"] = K.rank_scores(scores) if scores else []
    r["gpa"] = round(sum(K.gpa_point(s["score"], s["full_score"]) for s in scores) /
                     len(scores), 2) if scores else 0.0
    r["attendance"] = K.attendance_stats(db.rows(
        "SELECT status FROM attendance WHERE student_no=? "
        "ORDER BY adate DESC LIMIT 60", (no,)))
    r["fees"] = db.rows("SELECT no,item,term,amount,paid_amount,status,due_date "
                        "FROM fees WHERE student_no=? ORDER BY term DESC", (no,))
    r["transfers"] = db.rows("SELECT no,kind,status,effect_date FROM transfers "
                             "WHERE student_no=? ORDER BY no DESC", (no,))
    cls = db.one("SELECT name,head_teacher FROM classes WHERE no=?",
                 (r.get("class_no") or "",))
    r["className"] = (cls or {}).get("name", "")
    r["headTeacher"] = (cls or {}).get("head_teacher", "")
    return r


def api_student_save(u, b, q):
    need(u, "edu.write")
    b = b or {}
    errs = K.validate_student(b)
    if errs:
        raise ApiError("；".join(errs))
    no = (b.get("no") or "").strip() or db.gen_no("students", "ST")
    data = {
        "name": b["name"].strip(), "gender": b.get("gender") or "男",
        "school": b.get("school") or "S01", "grade": b.get("grade") or "",
        "class_no": b.get("class_no") or "", "birth": b.get("birth") or "",
        "guardian": b.get("guardian") or "", "relation": b.get("relation") or "家长",
        "guardian_phone": b.get("guardian_phone") or "",
        "address": b.get("address") or "", "enroll_date": b.get("enroll_date") or "",
        "status": b.get("status") or "在读", "memo": b.get("memo") or "",
    }
    if db.one("SELECT 1 FROM students WHERE no=?", (no,)):
        db.run("UPDATE students SET name=?,gender=?,school=?,grade=?,class_no=?,birth=?,"
               "guardian=?,relation=?,guardian_phone=?,address=?,enroll_date=?,status=?,memo=? "
               "WHERE no=?",
               tuple(data[k] for k in ("name", "gender", "school", "grade", "class_no",
                                       "birth", "guardian", "relation", "guardian_phone",
                                       "address", "enroll_date", "status", "memo")) + (no,))
    else:
        db.insert("students", data | {"no": no, "created_at": db.now()})
    db.run("UPDATE classes SET student_count=(SELECT COUNT(*) FROM students "
           "WHERE class_no=? AND status='在读') WHERE no=?",
           (data["class_no"], data["class_no"]))
    log(u, "学生保存", no)
    db.bumpsync("students")
    return {"no": no}


def api_student_status(u, b, q):
    """学籍状态变更（转出/毕业/休学/退学/复学）。"""
    need(u, "edu.write")
    no = (b.get("no") or "").strip()
    st = (b.get("status") or "").strip()
    if not no:
        raise ApiError("学号必填")
    if st not in ("在读", "休学", "转出", "毕业", "退学"):
        raise ApiError("非法状态：%s" % st)
    if not db.one("SELECT 1 FROM students WHERE no=?", (no,)):
        raise ApiError("学生不存在：%s" % no, 404)
    db.run("UPDATE students SET status=? WHERE no=?", (st, no))
    log(u, "学籍变更", no, st)
    db.bumpsync("students")
    return {"no": no, "status": st}


# ==================================================== 课程
def api_courses(u, b, q):
    need(u, "edu.read")
    kw = (q.get("kw") or [""])[0]
    sql = "SELECT * FROM courses WHERE 1=1"
    args = []
    if kw:
        sql += " AND (name LIKE ? OR code LIKE ? OR subject LIKE ?)"
        args += ["%%%s%%" % kw] * 3
    sql += " ORDER BY code"
    return listwrap(db.rows(sql, tuple(args)))


def api_course_get(u, b, q, code):
    need(u, "edu.read")
    r = db.one("SELECT * FROM courses WHERE code=?", (code,))
    if not r:
        raise ApiError("课程不存在：%s" % code, 404)
    r["stats"] = {
        "students": db.val("SELECT COUNT(DISTINCT student_no) FROM scores WHERE course=?",
                           (code,), 0),
        "avg": round(num(db.val("SELECT AVG(score) FROM scores WHERE course=?", (code,), 0)), 1),
        "slots": db.val("SELECT COUNT(*) FROM schedule WHERE course=?", (code,), 0),
    }
    return r


def api_course_save(u, b, q):
    need(u, "edu.write")
    b = b or {}
    if not (b.get("name") or "").strip():
        raise ApiError("课程名称必填")
    code = (b.get("code") or "").strip() or db.gen_no("courses", "KC", col="code")
    data = {
        "name": b["name"].strip(), "subject": b.get("subject") or "",
        "school": b.get("school") or "S01", "teacher": b.get("teacher") or "",
        "grade": b.get("grade") or "", "hours_per_week": intn(b.get("hours_per_week"), 4),
        "credit": num(b.get("credit"), 2), "status": b.get("status") or "开课",
        "memo": b.get("memo") or "",
    }
    if db.one("SELECT 1 FROM courses WHERE code=?", (code,)):
        db.run("UPDATE courses SET name=?,subject=?,school=?,teacher=?,grade=?,"
               "hours_per_week=?,credit=?,status=?,memo=? WHERE code=?",
               tuple(data[k] for k in ("name", "subject", "school", "teacher", "grade",
                                       "hours_per_week", "credit", "status", "memo")) + (code,))
    else:
        db.insert("courses", data | {"code": code, "created_at": db.now()})
    log(u, "课程保存", code)
    db.bumpsync("courses")
    return {"code": code}


# ==================================================== 排课
def api_schedule(u, b, q):
    need(u, "edu.read")
    class_no = (q.get("class_no") or [""])[0]
    term = (q.get("term") or [""])[0] or CURRENT_TERM
    sql = "SELECT * FROM schedule WHERE term=?"
    args = [term]
    if class_no:
        sql += " AND class_no=?"
        args.append(class_no)
    sql += " ORDER BY class_no, weekday, slot"
    items = db.rows(sql, tuple(args))
    if (q.get("with_conflicts") or [""])[0] in ("1", "true"):
        return {"list": items, "conflicts": K.schedule_conflicts(items)}
    return listwrap(items)


def api_schedule_save(u, b, q):
    need(u, "edu.write")
    b = b or {}
    items = b.get("items") or ([b] if b.get("class_no") else [])
    if not items:
        raise ApiError("排课明细必填")
    saved = 0
    for it in items:
        class_no = (it.get("class_no") or "").strip()
        course = (it.get("course") or "").strip()
        if not class_no or not course:
            raise ApiError("排课明细须包含班级与课程")
        wd = intn(it.get("weekday"), 0)
        slot = intn(it.get("slot"), 0)
        if not 1 <= wd <= 7 or not 1 <= slot <= 12:
            raise ApiError("weekday 须为 1~7，slot 须为 1~12")
        db.insert("schedule", {
            "class_no": class_no, "course": course,
            "teacher": it.get("teacher") or "", "weekday": wd, "slot": slot,
            "room": it.get("room") or "", "term": it.get("term") or CURRENT_TERM})
        saved += 1
    log(u, "排课保存", class_no, "%d 条" % saved)
    db.bumpsync("schedule")
    return {"saved": saved}


def api_schedule_conflicts(u, b, q):
    need(u, "edu.read")
    term = (q.get("term") or [""])[0] or CURRENT_TERM
    class_no = (q.get("class_no") or [""])[0]
    sql = "SELECT * FROM schedule WHERE term=?"
    args = [term]
    if class_no:
        sql += " AND class_no=?"
        args.append(class_no)
    items = db.rows(sql, tuple(args))
    return {"list": K.schedule_conflicts(items), "total": len(items)}


# ==================================================== 成绩
def api_scores(u, b, q):
    need(u, "edu.read")
    student_no = (q.get("student_no") or [""])[0]
    course = (q.get("course") or [""])[0]
    exam = (q.get("exam") or [""])[0]
    term = (q.get("term") or [""])[0] or CURRENT_TERM
    sql = "SELECT s.*, st.name AS student_name, st.class_no FROM scores s " \
          "LEFT JOIN students st ON st.no=s.student_no WHERE s.term=?"
    args = [term]
    if student_no:
        sql += " AND s.student_no=?"
        args.append(student_no)
    if course:
        sql += " AND s.course=?"
        args.append(course)
    if exam:
        sql += " AND s.exam=?"
        args.append(exam)
    sql += " ORDER BY s.id DESC LIMIT 2000"
    return listwrap(db.rows(sql, tuple(args)))


def api_scores_save(u, b, q):
    need(u, "score.write")
    b = b or {}
    items = b.get("items") or ([b] if b.get("student_no") else [])
    if not items:
        raise ApiError("成绩明细必填")
    saved = 0
    for it in items:
        sno = (it.get("student_no") or "").strip()
        course = (it.get("course") or "").strip()
        if not sno or not course:
            raise ApiError("成绩明细须包含学号与课程")
        sc = num(it.get("score"), -1)
        full = num(it.get("full_score"), 100)
        if sc < 0 or sc > full:
            raise ApiError("成绩须在 0~%s 之间" % full)
        exam = it.get("exam") or "期末"
        term = it.get("term") or CURRENT_TERM
        old = db.one("SELECT id FROM scores WHERE student_no=? AND course=? AND exam=? AND term=?",
                     (sno, course, exam, term))
        if old:
            db.run("UPDATE scores SET score=?,full_score=?,graded_by=?,graded_at=? WHERE id=?",
                   (sc, full, u["username"], db.now(), old["id"]))
        else:
            db.insert("scores", {
                "student_no": sno, "course": course, "exam": exam, "term": term,
                "score": sc, "full_score": full, "graded_by": u["username"],
                "graded_at": db.now(), "memo": it.get("memo") or ""})
        saved += 1
    log(u, "成绩录入", "%d 条" % saved)
    db.bumpsync("scores")
    return {"saved": saved}


def api_scores_analysis(u, b, q):
    """成绩分析：按课程/班级统计均分、及格率、优秀率、排名。"""
    need(u, "edu.read")
    term = (q.get("term") or [""])[0] or CURRENT_TERM
    exam = (q.get("exam") or [""])[0] or "期末"
    class_no = (q.get("class_no") or [""])[0]
    course = (q.get("course") or [""])[0]
    sql = ("SELECT s.*, st.name AS student_name, st.class_no FROM scores s "
           "LEFT JOIN students st ON st.no=s.student_no WHERE s.term=? AND s.exam=?")
    args = [term, exam]
    if class_no:
        sql += " AND st.class_no=?"
        args.append(class_no)
    if course:
        sql += " AND s.course=?"
        args.append(course)
    rows_ = db.rows(sql, tuple(args))
    by_course = {}
    for r in rows_:
        by_course.setdefault(r["course"], []).append(r)
    out = []
    for c, arr in sorted(by_course.items()):
        full = num(arr[0].get("full_score"), 100)
        st = K.grade_stats(arr, full)
        st["course"] = c
        cname = db.val("SELECT name FROM courses WHERE code=?", (c,), c)
        st["course_name"] = cname
        st["rank"] = K.rank_scores(arr, full)[:10]
        out.append(st)
    return {"list": out, "total": len(out), "overall": K.grade_stats(rows_)}


def api_scores_rank(u, b, q):
    """班级排名榜。"""
    need(u, "edu.read")
    term = (q.get("term") or [""])[0] or CURRENT_TERM
    exam = (q.get("exam") or [""])[0] or "期末"
    class_no = (q.get("class_no") or [""])[0]
    if not class_no:
        raise ApiError("class_no 必填")
    rows_ = db.rows(
        "SELECT student_no, SUM(score) AS total, AVG(score) AS avg, "
        "COUNT(*) AS subjects FROM scores WHERE term=? AND exam=? "
        "GROUP BY student_no", (term, exam))
    if not rows_:
        return listwrap([])
    names = {r["no"]: r["name"] for r in db.rows(
        "SELECT no,name FROM students WHERE class_no=?", (class_no,))}
    arr = [r for r in rows_ if r["student_no"] in names]
    for r in arr:
        r["name"] = names[r["student_no"]]
    return listwrap(K.rank_scores(arr))


def api_scores_transcript(u, b, q, no):
    """学生成绩单：各科成绩 + 等级 + GPA + 班级排名。"""
    need(u, "edu.read")
    stu = db.one("SELECT * FROM students WHERE no=?", (no,))
    if not stu:
        raise ApiError("学生不存在：%s" % no, 404)
    rows_ = db.rows("SELECT * FROM scores WHERE student_no=? ORDER BY term,exam", (no,))
    items = []
    for r in rows_:
        r["level"] = K.grade_level(r["score"], r["full_score"])
        r["gpa"] = K.gpa_point(r["score"], r["full_score"])
        items.append(r)
    # 班级排名（最近学期考试）
    rank = None
    if rows_:
        last = rows_[-1]
        peers = db.rows(
            "SELECT s.student_no, st.name, SUM(s.score) AS score FROM scores s "
            "JOIN students st ON st.no=s.student_no WHERE s.term=? AND s.exam=? "
            "AND st.class_no=? GROUP BY s.student_no",
            (last["term"], last["exam"], stu.get("class_no") or ""))
        rl = K.rank_scores(peers)
        rank = next((r for r in rl if r["student_no"] == no), None)
    return {
        "student": stu, "items": items,
        "stats": K.grade_stats(rows_),
        "weighted": K.weighted_avg(
            [{"score": r["score"], "credit": db.val(
                "SELECT credit FROM courses WHERE code=?", (r["course"],), 2)}
             for r in rows_]),
        "rank": rank,
    }


# ==================================================== 考勤
def api_attendance(u, b, q):
    need(u, "edu.read")
    student_no = (q.get("student_no") or [""])[0]
    class_no = (q.get("class_no") or [""])[0]
    adate = (q.get("adate") or [""])[0]
    sql = ("SELECT a.*, st.name AS student_name, st.class_no FROM attendance a "
           "LEFT JOIN students st ON st.no=a.student_no WHERE 1=1")
    args = []
    if student_no:
        sql += " AND a.student_no=?"
        args.append(student_no)
    if class_no:
        sql += " AND st.class_no=?"
        args.append(class_no)
    if adate:
        sql += " AND a.adate=?"
        args.append(adate)
    sql += " ORDER BY a.adate DESC, a.id DESC LIMIT 2000"
    return listwrap(db.rows(sql, tuple(args)))


def api_attendance_save(u, b, q):
    need(u, "edu.write")
    b = b or {}
    items = b.get("items") or ([b] if b.get("student_no") else [])
    if not items:
        raise ApiError("考勤明细必填")
    saved = 0
    for it in items:
        sno = (it.get("student_no") or "").strip()
        st = it.get("status") or "出勤"
        if not sno:
            raise ApiError("学号必填")
        if st not in K.ATT_STATUSES:
            raise ApiError("非法考勤状态：%s" % st)
        db.insert("attendance", {
            "student_no": sno, "adate": it.get("adate") or db.today(),
            "status": st, "slot": it.get("slot") or "上午",
            "memo": it.get("memo") or "", "recorded_by": u["username"],
            "recorded_at": db.now()})
        saved += 1
    log(u, "考勤登记", "%d 条" % saved)
    db.bumpsync("attendance")
    return {"saved": saved}


def api_attendance_stats(u, b, q):
    need(u, "edu.read")
    days = intn((q.get("days") or ["30"])[0], 30)
    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * days))
    class_no = (q.get("class_no") or [""])[0]
    if class_no:
        recs = db.rows(
            "SELECT a.status FROM attendance a JOIN students st ON st.no=a.student_no "
            "WHERE a.adate>=? AND st.class_no=?", (since, class_no))
        overall = K.attendance_stats(recs)
        by_student = []
        for stu in db.rows("SELECT no,name FROM students WHERE class_no=?", (class_no,)):
            rr = db.rows("SELECT status FROM attendance WHERE student_no=? AND adate>=?",
                         (stu["no"], since))
            st_ = K.attendance_stats(rr)
            st_["student_no"] = stu["no"]
            st_["name"] = stu["name"]
            by_student.append(st_)
        by_student.sort(key=lambda x: x["rate"])
        return {"days": days, "overall": overall, "byStudent": by_student}
    recs = db.rows("SELECT status FROM attendance WHERE adate>=?", (since,))
    return {"days": days, "overall": K.attendance_stats(recs)}


# ==================================================== 缴费
def api_fees(u, b, q):
    need(u, "edu.read")
    student_no = (q.get("student_no") or [""])[0]
    term = (q.get("term") or [""])[0]
    status = (q.get("status") or [""])[0]
    sql = ("SELECT f.*, st.name AS student_name, st.class_no FROM fees f "
           "LEFT JOIN students st ON st.no=f.student_no WHERE 1=1")
    args = []
    if student_no:
        sql += " AND f.student_no=?"
        args.append(student_no)
    if term:
        sql += " AND f.term=?"
        args.append(term)
    if status:
        sql += " AND f.status=?"
        args.append(status)
    sql += " ORDER BY f.no"
    return listwrap(db.rows(sql, tuple(args)))


def api_fee_save(u, b, q):
    need(u, "fee.write")
    b = b or {}
    errs = K.validate_fee(b)
    if errs:
        raise ApiError("；".join(errs))
    no = (b.get("no") or "").strip() or db.gen_no("fees", "F")
    data = {
        "student_no": b["student_no"].strip(), "item": b.get("item") or "学费",
        "term": b.get("term") or CURRENT_TERM, "amount": num(b.get("amount")),
        "discount": num(b.get("discount")), "paid_amount": num(b.get("paid_amount")),
        "due_date": b.get("due_date") or "", "pay_method": b.get("pay_method") or "",
        "memo": b.get("memo") or "",
    }
    payable = K.tuition_payable(data["amount"], data["discount"], 0)
    data["status"] = "已缴清" if data["paid_amount"] >= payable else (
        "部分缴费" if data["paid_amount"] > 0 else "待缴")
    if db.one("SELECT 1 FROM fees WHERE no=?", (no,)):
        db.run("UPDATE fees SET student_no=?,item=?,term=?,amount=?,discount=?,"
               "paid_amount=?,due_date=?,pay_method=?,memo=?,status=? WHERE no=?",
               tuple(data[k] for k in ("student_no", "item", "term", "amount", "discount",
                                       "paid_amount", "due_date", "pay_method", "memo",
                                       "status")) + (no,))
    else:
        db.insert("fees", data | {"no": no, "created_by": u["username"],
                                  "created_at": db.now()})
    log(u, "缴费保存", no)
    db.bumpsync("fees")
    return {"no": no, "payable": payable, "status": data["status"]}


def api_fee_pay(u, b, q):
    """缴费核销：paid_amount 增加，满额自动缴清。幂等键支持。"""
    need(u, "fee.write")
    no = (b.get("no") or "").strip()
    amt = num(b.get("amount"), -1)
    if not no:
        raise ApiError("缴费单号必填")
    r = db.one("SELECT * FROM fees WHERE no=?", (no,))
    if not r:
        raise ApiError("缴费单不存在：%s" % no, 404)
    if r.get("status") == "已缴清":
        return {"no": no, "status": "已缴清", "paid": r["paid_amount"], "noop": True}
    if amt < 0:
        raise ApiError("缴费金额不能为负")
    payable = K.tuition_payable(r["amount"], r["discount"], 0)
    paid = min(payable, num(r["paid_amount"]) + amt)
    status = "已缴清" if paid >= payable else "部分缴费"
    db.run("UPDATE fees SET paid_amount=?,status=?,paid_at=?,pay_method=? WHERE no=?",
           (paid, status, db.now() if status == "已缴清" else "",
            b.get("pay_method") or r.get("pay_method") or "", no))
    log(u, "缴费核销", no, "%.2f" % amt)
    db.bumpsync("fees")
    return {"no": no, "payable": payable, "paid": K.money(paid), "status": status}


def api_fee_summary(u, b, q):
    need(u, "edu.read")
    term = (q.get("term") or [""])[0] or CURRENT_TERM
    rows_ = db.rows("SELECT * FROM fees WHERE term=?", (term,))
    total = sum(K.tuition_payable(r["amount"], r["discount"], 0) for r in rows_)
    paid = sum(num(r["paid_amount"]) for r in rows_)
    by_status = {}
    for r in rows_:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    overdue = [r["no"] for r in rows_ if K.fee_overdue(r, db.today())]
    return {"term": term, "bills": len(rows_),
            "total": K.money(total), "paid": K.money(paid),
            "unpaid": K.money(max(0, total - paid)),
            "rate": round(paid * 100.0 / total, 2) if total else 0.0,
            "overdueCount": len(overdue), "overdueNos": overdue[:20],
            "byStatus": by_status}


# ==================================================== 学籍变动
def api_transfers(u, b, q):
    need(u, "edu.read")
    student_no = (q.get("student_no") or [""])[0]
    status = (q.get("status") or [""])[0]
    sql = ("SELECT t.*, st.name AS student_name FROM transfers t "
           "LEFT JOIN students st ON st.no=t.student_no WHERE 1=1")
    args = []
    if student_no:
        sql += " AND t.student_no=?"
        args.append(student_no)
    if status:
        sql += " AND t.status=?"
        args.append(status)
    sql += " ORDER BY t.no DESC"
    return listwrap(db.rows(sql, tuple(args)))


def api_transfer_save(u, b, q):
    need(u, "edu.write")
    b = b or {}
    sno = (b.get("student_no") or "").strip()
    kind = (b.get("kind") or "").strip()
    if not sno:
        raise ApiError("学号必填")
    if kind not in ("转班", "转入", "转出", "休学", "复学", "退学", "毕业"):
        raise ApiError("非法变动类型：%s" % kind)
    if not db.one("SELECT 1 FROM students WHERE no=?", (sno,)):
        raise ApiError("学生不存在：%s" % sno, 404)
    no = db.gen_no("transfers", "TR")
    db.insert("transfers", {
        "no": no, "student_no": sno, "kind": kind,
        "from_value": b.get("from_value") or "", "to_value": b.get("to_value") or "",
        "reason": b.get("reason") or "", "effect_date": b.get("effect_date") or db.today(),
        "status": "待审批", "created_by": u["username"], "created_at": db.now()})
    log(u, "学籍变动申请", no, "%s %s" % (sno, kind))
    db.bumpsync("transfers")
    return {"no": no, "status": "待审批"}


def api_transfer_approve(u, b, q):
    need(u, "edu.write")
    no = (b.get("no") or "").strip()
    action = b.get("action") or "approve"
    r = db.one("SELECT * FROM transfers WHERE no=?", (no,))
    if not r:
        raise ApiError("变动单不存在：%s" % no, 404)
    if r.get("status") != "待审批":
        raise ApiError("变动单已处理：%s" % r["status"])
    if action == "approve":
        stu = db.one("SELECT * FROM students WHERE no=?", (r["student_no"],))
        if r["kind"] == "转班" and r.get("to_value") and stu:
            old_cls = stu["class_no"]
            db.run("UPDATE students SET class_no=?,grade=? WHERE no=?",
                   (r["to_value"],
                    db.val("SELECT grade FROM classes WHERE no=?", (r["to_value"],),
                           stu["grade"]) or stu["grade"], r["student_no"]))
            for c in (old_cls, r["to_value"]):
                db.run("UPDATE classes SET student_count=(SELECT COUNT(*) FROM students "
                       "WHERE class_no=? AND status='在读') WHERE no=?", (c, c))
        elif r["kind"] in ("休学", "转出", "退学"):
            db.run("UPDATE students SET status=? WHERE no=?", (r["kind"], r["student_no"]))
        elif r["kind"] in ("复学", "转入"):
            db.run("UPDATE students SET status='在读' WHERE no=?", (r["student_no"],))
        db.run("UPDATE transfers SET status='已审批',approver=?,approved_at=? WHERE no=?",
               (u["username"], db.now(), no))
        log(u, "学籍变动审批", no, "通过")
    else:
        db.run("UPDATE transfers SET status='已驳回',approver=?,approved_at=? WHERE no=?",
               (u["username"], db.now(), no))
        log(u, "学籍变动审批", no, "驳回")
    db.bumpsync("transfers", "students")
    return {"no": no, "status": "已审批" if action == "approve" else "已驳回"}


# ==================================================== 风险预警
def api_risks(u, b, q):
    need(u, "risk.read")
    status = (q.get("status") or [""])[0]
    sql = "SELECT * FROM risks WHERE 1=1"
    args = []
    if status:
        sql += " AND status=?"
        args.append(status)
    sql += " ORDER BY weight DESC, id DESC"
    return listwrap(db.rows(sql, tuple(args)))


def api_risk_close(u, b, q):
    need(u, "risk.read")
    rid = intn(b.get("id"), 0)
    r = db.one("SELECT * FROM risks WHERE id=?", (rid,))
    if not r:
        raise ApiError("预警不存在", 404)
    db.run("UPDATE risks SET status='已处理',handler=?,closed_at=? WHERE id=?",
           (u["username"], db.now(), rid))
    log(u, "预警处理", str(rid))
    return {"id": rid, "status": "已处理"}


def api_risk_scan(u, b, q):
    """规则引擎扫描：欠费逾期 / 成绩预警 / 出勤异常 → 写入 risks。"""
    need(u, "risk.read")
    created = []
    today = db.today()
    # 1. 欠费逾期
    overdue = db.rows(
        "SELECT student_no, COUNT(*) AS cnt, SUM(amount*(100-discount)/100-paid_amount) AS amt "
        "FROM fees WHERE status!='已缴清' AND due_date!='' AND due_date<? GROUP BY student_no",
        (today,))
    for o in overdue:
        if num(o["amt"]) <= 0:
            continue
        title = "学生 %s 学费逾期未缴" % o["student_no"]
        if not db.one("SELECT 1 FROM risks WHERE title=? AND status='待处理'", (title,)):
            db.insert("risks", {
                "school": db.val("SELECT school FROM students WHERE no=?",
                                 (o["student_no"],), ""),
                "code": "R-FEE", "level": "险" if num(o["amt"]) > 3000 else "警",
                "title": title,
                "detail": "逾期单数 %d，欠费 %.2f 元" % (o["cnt"], num(o["amt"])),
                "weight": min(90, 40 + int(num(o["amt"]) / 500)), "status": "待处理",
                "created_at": db.now()})
            created.append(title)
    # 2. 学业预警：最近一次考试均分 < 60 或挂科 ≥2 门
    for sno, name in [(r["no"], r["name"]) for r in db.rows(
            "SELECT no,name FROM students WHERE status='在读'")]:
        scores = db.rows(
            "SELECT score FROM scores WHERE student_no=? AND term=? AND exam=?",
            (sno, CURRENT_TERM, "期末"))
        if not scores:
            continue
        fails = sum(1 for s in scores if num(s["score"]) < 60)
        avg = num(sum(num(s["score"]) for s in scores) / len(scores))
        if fails >= 2 or avg < 60:
            title = "学生 %s 学业预警（挂科 %d 门）" % (sno, fails)
            if not db.one("SELECT 1 FROM risks WHERE title=? AND status='待处理'", (title,)):
                db.insert("risks", {
                    "school": db.val("SELECT school FROM students WHERE no=?", (sno,), ""),
                    "code": "R-SCORE", "level": "警", "title": title,
                    "detail": "期末均分 %.1f，挂科 %d 门，建议班主任约谈" % (avg, fails),
                    "weight": 55, "status": "待处理", "created_at": db.now()})
                created.append(title)
    # 3. 旷课 ≥3 次
    for r in db.rows(
            "SELECT student_no, COUNT(*) AS cnt FROM attendance "
            "WHERE status='旷课' AND adate>=? GROUP BY student_no HAVING cnt>=?",
            (time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * 30)), 3)):
        title = "学生 %s 近 30 天旷课 %d 次" % (r["student_no"], r["cnt"])
        if not db.one("SELECT 1 FROM risks WHERE title=? AND status='待处理'", (title,)):
            db.insert("risks", {
                "school": db.val("SELECT school FROM students WHERE no=?",
                                 (r["student_no"],), ""),
                "code": "R-ATT", "level": "警", "title": title,
                "detail": "近 30 天旷课 %d 次，建议学生处关注" % r["cnt"],
                "weight": 50, "status": "待处理", "created_at": db.now()})
            created.append(title)
    log(u, "风险扫描", "scan", "新增 %d 条" % len(created))
    return {"created": created, "count": len(created)}


# ==================================================== 政策/公告/系统
def api_policies(u, b, q):
    need(u, "edu.read")
    kw = (q.get("kw") or [""])[0]
    sql = "SELECT id,title,doc_no,category,effect_date,expire_date,summary,tags,status " \
          "FROM policies WHERE 1=1"
    args = []
    if kw:
        sql += " AND (title LIKE ? OR summary LIKE ?)"
        args += ["%%%s%%" % kw] * 2
    sql += " ORDER BY id DESC"
    return listwrap(db.rows(sql, tuple(args)))


def api_policy_get(u, b, q, pid):
    need(u, "edu.read")
    r = db.one("SELECT * FROM policies WHERE id=?", (intn(pid),))
    if not r:
        raise ApiError("政策不存在", 404)
    return r


def api_notices(u, b, q):
    return db.rows("SELECT id,title,body,author,top,created_at FROM notices "
                   "ORDER BY top DESC, id DESC")


def api_notice_save(u, b, q):
    need(u, "edu.write")
    b = b or {}
    title = (b.get("title") or "").strip()
    if not title:
        raise ApiError("标题必填")
    db.insert("notices", {"title": title, "body": b.get("body") or "",
                          "author": u["username"], "top": 1 if b.get("top") else 0,
                          "created_at": db.now()})
    log(u, "公告发布", title)
    return {"ok": True}


def api_users(u, b, q):
    need(u, "org.read")
    return listwrap(db.rows(
        "SELECT username,name,dept,title,role,phone,email,status,created_at "
        "FROM users ORDER BY username"))


def api_user_save(u, b, q):
    need(u, "org.read")
    b = b or {}
    un = (b.get("username") or "").strip()
    if not un:
        raise ApiError("用户名必填")
    if not db.one("SELECT 1 FROM users WHERE username=?", (un,)):
        raise ApiError("用户不存在（不开放自助建号）", 404)
    db.run("UPDATE users SET name=?,dept=?,title=?,role=?,phone=?,email=? WHERE username=?",
           (b.get("name") or "", b.get("dept") or "", b.get("title") or "",
            b.get("role") or "reader", b.get("phone") or "", b.get("email") or "", un))
    log(u, "用户保存", un)
    return {"username": un}


def api_roles(u, b, q):
    need(u, "org.read")
    return [{"role": k, "label": ROLE_LABELS.get(k, k), "perms": sorted(v)}
            for k, v in K.ROLE_PERMS.items()]


def api_depts(u, b, q):
    need(u, "org.read")
    return listwrap(db.rows("SELECT * FROM depts ORDER BY sort"))


def api_logs(u, b, q):
    need(u, "system.read")
    return listwrap(db.rows("SELECT * FROM logs ORDER BY id DESC LIMIT 300"))


def api_apikeys(u, b, q):
    need(u, "system.read")
    return listwrap(db.rows(
        "SELECT id,name,prefix,scope,owner,status,created_at,last_used FROM api_keys "
        "ORDER BY id DESC"))


def api_apikey_create(u, b, q):
    need(u, "system.read")
    b = b or {}
    name = (b.get("name") or "").strip()
    if not name:
        raise ApiError("密钥名称必填")
    raw = "fk_" + sha(name + str(time.time()))[:32]
    db.insert("api_keys", {
        "name": name, "key_hash": sha(raw),
        "prefix": raw[:8] + "...", "scope": b.get("scope") or "read",
        "owner": u["username"], "status": "启用", "created_at": db.now()})
    log(u, "创建密钥", name)
    return {"key": raw, "name": name, "scope": b.get("scope") or "read",
            "note": "密钥仅此一次展示，请妥善保存"}


def api_apidoc(u, b, q):
    return {
        "brand": BRAND, "version": VERSION, "count": len(ROUTES),
        "routes": [{"method": m, "path": p, "perm": perm or "-"}
                   for m, p, _, perm in ROUTES],
        "auth": ["Authorization: Bearer <token>", "X-Edu-Token: <token>",
                 "Cookie: edu_token=<token>", "?token=<token>", "X-Edu-Key: <apikey>"],
        "response": {"code": 0, "message": "ok", "data": {}},
        "idempotency": "写接口携带 Idempotency-Key 头，重复请求返回首次结果",
        "sync": "GET /api/sync?version=students:3&entities=students,scores",
    }


SYNC_ENTITIES = {"students": api_students, "scores": api_scores,
                 "fees": api_fees, "attendance": api_attendance}


def api_sync_version(u, b, q):
    need(u, "edu.read")
    return {e: db.version_of(e) for e in SYNC_ENTITIES}


def api_sync(u, b, q):
    need(u, "edu.read")
    ents = (q.get("entities") or [",".join(SYNC_ENTITIES.keys())])[0]
    want = (q.get("version") or ["0"])[0]
    want_map = {}
    for kv in str(want).split(","):
        if ":" in kv:
            k, v = kv.split(":", 1)
            want_map[k.strip()] = intn(v)
    out = {}
    for e in [x.strip() for x in ents.split(",") if x.strip()]:
        if e not in SYNC_ENTITIES:
            continue
        cur = db.version_of(e)
        item = {"version": cur}
        if cur != want_map.get(e):
            fake_u = {"perms": ["*"]}
            qq = dict(q)
            qq["term"] = [""]
            data = SYNC_ENTITIES[e](fake_u, {}, qq)
            item["data"] = data.get("list", data)
        out[e] = item
    return {"now": db.now(), "entities": out}


# ==================================================== 报表
def api_report_summary(u, b, q):
    """四合一总览：教学 / 成绩 / 出勤 / 缴费。"""
    need(u, "report.read")
    term = (q.get("term") or [""])[0] or CURRENT_TERM
    teaching = {
        "students": db.val("SELECT COUNT(*) FROM students WHERE status='在读'", (), 0),
        "teachers": db.val("SELECT COUNT(*) FROM teachers WHERE status='在职'", (), 0),
        "classes": db.val("SELECT COUNT(*) FROM classes WHERE status='在读'", (), 0),
        "courses": db.val("SELECT COUNT(*) FROM courses WHERE status='开课'", (), 0),
    }
    scores = db.rows("SELECT score FROM scores WHERE term=?", (term,))
    academic = K.grade_stats(scores)
    att = K.attendance_stats(db.rows(
        "SELECT status FROM attendance WHERE adate>=?",
        (time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * 30)),)))
    fees = api_fee_summary.__wrapped__(u, b, q) if hasattr(api_fee_summary, "__wrapped__") \
        else None
    fs = {"bills": 0, "total": 0, "paid": 0, "unpaid": 0, "rate": 0}
    rows_ = db.rows("SELECT * FROM fees WHERE term=?", (term,))
    total = sum(K.tuition_payable(r["amount"], r["discount"], 0) for r in rows_)
    paid = sum(num(r["paid_amount"]) for r in rows_)
    fs = {"bills": len(rows_), "total": K.money(total), "paid": K.money(paid),
          "unpaid": K.money(max(0, total - paid)),
          "rate": round(paid * 100.0 / total, 2) if total else 0.0}
    return {"term": term, "teaching": teaching, "academic": academic,
            "attendance": att, "fee": fs}


def api_report_trend(u, b, q):
    need(u, "report.read")
    class_no = (q.get("class_no") or [""])[0]
    course = (q.get("course") or [""])[0]
    out = []
    for term in [r["term"] for r in db.rows("SELECT DISTINCT term FROM scores ORDER BY term")]:
        for exam in ("期中", "期末"):
            sql = ("SELECT AVG(s.score) AS a FROM scores s JOIN students st "
                   "ON st.no=s.student_no WHERE s.term=? AND s.exam=?")
            args = [term, exam]
            if class_no:
                sql += " AND st.class_no=?"
                args.append(class_no)
            if course:
                sql += " AND s.course=?"
                args.append(course)
            a = num(db.val(sql, tuple(args), 0))
            if a:
                out.append({"term": term, "exam": exam, "avg": round(a, 1)})
    return listwrap(out)


def api_report_attendance(u, b, q):
    need(u, "report.read")
    return api_attendance_stats(u, b, q)


def api_report_fee(u, b, q):
    need(u, "report.read")
    return api_fee_summary(u, b, q)


def api_report_grade_dist(u, b, q):
    need(u, "report.read")
    term = (q.get("term") or [""])[0] or CURRENT_TERM
    exam = (q.get("exam") or [""])[0] or "期末"
    rows_ = db.rows("SELECT score, full_score FROM scores WHERE term=? AND exam=?",
                    (term, exam))
    dist = {"优": 0, "良": 0, "中": 0, "及格": 0, "不及格": 0}
    for r in rows_:
        dist[K.grade_level(r["score"], r["full_score"])] += 1
    return {"term": term, "exam": exam, "dist": dist, "count": len(rows_)}


def api_report_export(u, b, q):
    """CSV 导出（学生名单 + 当期成绩均分）。"""
    need(u, "report.read")
    lines = ["学号,姓名,班级,年级,状态,期末均分,GPA"]
    for st in db.rows("SELECT * FROM students ORDER BY no"):
        avg = db.val("SELECT AVG(score) FROM scores WHERE student_no=? AND exam='期末'",
                     (st["no"],), 0)
        gpa = db.val("SELECT AVG(score) FROM scores WHERE student_no=?", (st["no"],), 0)
        lines.append("%s,%s,%s,%s,%s,%s,%s" % (
            st["no"], st["name"], st["class_no"], st["grade"], st["status"],
            round(num(avg), 1), round(K.gpa_point(num(gpa)), 2)))
    body = ("﻿" + "\n".join(lines)).encode("utf-8-sig")
    return body


# ==================================================== 路由表
ROUTES = [
    ("GET", r"^/api/health$", api_health, None),
    ("GET", r"^/api/apidoc$", api_apidoc, None),
    ("POST", r"^/api/auth/login$", api_login, None),
    ("POST", r"^/api/auth/logout$", api_logout, None),
    ("GET", r"^/api/auth/me$", api_me, None),
    ("POST", r"^/api/auth/change-password$", api_change_pwd, None),

    ("GET", r"^/api/dashboard$", api_dashboard, "dashboard.read"),

    # 校区
    ("GET", r"^/api/schools$", api_schools, "edu.read"),
    ("GET", r"^/api/schools/([\w\-]+)$", api_school_get, "edu.read"),
    ("POST", r"^/api/schools/save$", api_school_save, "edu.write"),
    # 教师
    ("GET", r"^/api/teachers$", api_teachers, "edu.read"),
    ("GET", r"^/api/teachers/([\w\-]+)$", api_teacher_get, "edu.read"),
    ("POST", r"^/api/teachers/save$", api_teacher_save, "edu.write"),
    # 班级
    ("GET", r"^/api/classes$", api_classes, "edu.read"),
    ("GET", r"^/api/classes/([\w\-]+)$", api_class_get, "edu.read"),
    ("POST", r"^/api/classes/save$", api_class_save, "edu.write"),
    # 学生
    ("GET", r"^/api/students$", api_students, "edu.read"),
    ("GET", r"^/api/students/([\w\-]+)$", api_student_get, "edu.read"),
    ("POST", r"^/api/students/save$", api_student_save, "edu.write"),
    ("POST", r"^/api/students/status$", api_student_status, "edu.write"),
    # 课程
    ("GET", r"^/api/courses$", api_courses, "edu.read"),
    ("GET", r"^/api/courses/([\w\-]+)$", api_course_get, "edu.read"),
    ("POST", r"^/api/courses/save$", api_course_save, "edu.write"),
    # 排课
    ("GET", r"^/api/schedule$", api_schedule, "edu.read"),
    ("POST", r"^/api/schedule/save$", api_schedule_save, "edu.write"),
    ("GET", r"^/api/schedule/conflicts$", api_schedule_conflicts, "edu.read"),
    # 成绩
    ("GET", r"^/api/scores$", api_scores, "edu.read"),
    ("POST", r"^/api/scores/save$", api_scores_save, "score.write"),
    ("GET", r"^/api/scores/analysis$", api_scores_analysis, "edu.read"),
    ("GET", r"^/api/scores/rank$", api_scores_rank, "edu.read"),
    ("GET", r"^/api/scores/transcript/([\w\-]+)$", api_scores_transcript, "edu.read"),
    # 考勤
    ("GET", r"^/api/attendance$", api_attendance, "edu.read"),
    ("POST", r"^/api/attendance/save$", api_attendance_save, "edu.write"),
    ("GET", r"^/api/attendance/stats$", api_attendance_stats, "edu.read"),
    # 缴费
    ("GET", r"^/api/fees$", api_fees, "edu.read"),
    ("POST", r"^/api/fees/save$", api_fee_save, "fee.write"),
    ("POST", r"^/api/fees/pay$", api_fee_pay, "fee.write"),
    ("GET", r"^/api/fees/summary$", api_fee_summary, "edu.read"),
    # 学籍变动
    ("GET", r"^/api/transfers$", api_transfers, "edu.read"),
    ("POST", r"^/api/transfers/save$", api_transfer_save, "edu.write"),
    ("POST", r"^/api/transfers/approve$", api_transfer_approve, "edu.write"),
    # 风险
    ("GET", r"^/api/risks$", api_risks, "risk.read"),
    ("POST", r"^/api/risks/close$", api_risk_close, "risk.read"),
    ("POST", r"^/api/risks/scan$", api_risk_scan, "risk.read"),
    # 政策
    ("GET", r"^/api/policies$", api_policies, "edu.read"),
    ("GET", r"^/api/policies/(\d+)$", api_policy_get, "edu.read"),
    # 公告
    ("GET", r"^/api/notices$", api_notices, None),
    ("POST", r"^/api/notices/save$", api_notice_save, "edu.write"),
    # 报表
    ("GET", r"^/api/reports/summary$", api_report_summary, "report.read"),
    ("GET", r"^/api/reports/trend$", api_report_trend, "report.read"),
    ("GET", r"^/api/reports/attendance$", api_report_attendance, "report.read"),
    ("GET", r"^/api/reports/fee$", api_report_fee, "report.read"),
    ("GET", r"^/api/reports/grade-dist$", api_report_grade_dist, "report.read"),
    ("GET", r"^/api/reports/export$", api_report_export, "report.read"),
    # 平台
    ("GET", r"^/api/users$", api_users, "org.read"),
    ("POST", r"^/api/users/save$", api_user_save, "org.read"),
    ("GET", r"^/api/roles$", api_roles, "org.read"),
    ("GET", r"^/api/depts$", api_depts, "org.read"),
    ("GET", r"^/api/logs$", api_logs, "system.read"),
    ("GET", r"^/api/api-keys$", api_apikeys, "system.read"),
    ("POST", r"^/api/api-keys/create$", api_apikey_create, "system.read"),
    # 同步
    ("GET", r"^/api/sync/version$", api_sync_version, "edu.read"),
    ("GET", r"^/api/sync$", api_sync, "edu.read"),
]


# ==================================================== HTTP Handler
class Handler(BaseHTTPRequestHandler):
    server_version = "FeiYuEdu/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt_, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt_ % args))

    def _send(self, code, payload, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        elif isinstance(payload, bytes):
            body = payload
        else:
            body = str(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _auth_user(self, path, headers):
        val_ = headers.get("Authorization") or headers.get("X-Edu-Token") or ""
        if not val_:
            val_ = headers.get("X-Edu-Key") or ""
            if val_:
                return user_by_apikey(val_)
        m = re.search(r"[?&]token=([\w\-]+)", path)
        if not val_ and m:
            val_ = m.group(1)
        ck = headers.get("Cookie") or ""
        if not val_:
            mm = re.search(r"edu_token=([\w\-]+)", ck)
            if mm:
                val_ = mm.group(1)
        return user_by_token(val_)

    def _dispatch(self, method):
        try:
            path = urllib.parse.urlparse(self.path).path
            if PREFIX and path.startswith(PREFIX + "/"):
                path = path[len(PREFIX):]
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

            body = b""
            if method == "POST":
                ln = intn(self.headers.get("Content-Length"), 0)
                if ln:
                    body = self.rfile.read(ln)
                if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
                    chunks = []
                    while True:
                        sz_line = self.rfile.readline().strip()
                        sz = int(sz_line.split(b";")[0] or b"0", 16)
                        if not sz:
                            self.rfile.readline()
                            break
                        chunks.append(self.rfile.read(sz))
                        self.rfile.readline()
                    body = b"".join(chunks)

            if method == "GET" and not path.startswith("/api/"):
                return self._static(path)

            bjson = {}
            if body:
                try:
                    bjson = json.loads(body.decode("utf-8"))
                except Exception:                             # noqa: BLE001
                    bjson = dict(urllib.parse.parse_qsl(body.decode("utf-8", "ignore")))

            u = self._auth_user(self.path, self.headers)
            idem = self.headers.get("Idempotency-Key") or ""
            if idem and method == "POST":
                old = db.one("SELECT status,body FROM idem_keys WHERE key=?", (idem,))
                if old:
                    return self._send(old["status"], json.loads(old["body"]))

            for m, pat, fn, perm in ROUTES:
                if m != method:
                    continue
                mt = re.match(pat, path)
                if not mt:
                    continue
                if perm and (u is None):
                    raise ApiError("未登录或凭证无效", 401)
                if perm and not has_perm(u, perm):
                    raise ApiError("无权限：需要 %s" % perm, 403)
                args = mt.groups()
                try:
                    data = fn(u, bjson, query, *args)
                except TypeError:
                    data = fn(u, bjson, query)
                if isinstance(data, bytes):
                    return self._send(200, data, "text/csv; charset=utf-8",
                                      {"Content-Disposition":
                                       "attachment; filename=export.csv"})
                resp = {"code": 200, "message": "ok", "data": data}
                if idem and method == "POST":
                    if not db.one("SELECT 1 FROM idem_keys WHERE key=?", (idem,)):
                        db.run("INSERT INTO idem_keys (key,username,path,status,body,"
                               "created_at) VALUES (?,?,?,?,?,?)",
                               (idem, (u or {}).get("username", "-"), path, 200,
                                jdumps(resp), db.now()))
                return self._send(200, resp)

            if path.startswith("/api/"):
                raise ApiError("接口不存在：%s" % path, 404)
            return self._static(path)
        except ApiError as e:
            return self._send(e.code, {"code": e.code, "message": e.message, "data": None})
        except Exception as e:                                # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"code": 500, "message": "服务器内部错误：%s" % e,
                                    "data": None})

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        fp = os.path.normpath(os.path.join(FRONTEND, path.lstrip("/")))
        if not fp.startswith(FRONTEND) or not os.path.isfile(fp):
            fp = os.path.join(FRONTEND, "index.html")
        ctype = "text/html; charset=utf-8"
        if fp.endswith(".js"):
            ctype = "application/javascript; charset=utf-8"
        elif fp.endswith(".css"):
            ctype = "text/css; charset=utf-8"
        elif fp.endswith(".svg"):
            ctype = "image/svg+xml"
        elif fp.endswith((".png", ".jpg", ".ico")):
            ctype = "image/%s" % fp.rsplit(".", 1)[-1]
        with open(fp, "rb") as f:
            return self._send(200, f.read(), ctype, {"Cache-Control": "no-cache"})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_OPTIONS(self):
        self._send(200, b"", "text/plain", {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Edu-Token,"
                                            "X-Edu-Key,Idempotency-Key",
        })


def main():
    db.init()
    created = seedmod.seed()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("%s v%s 监听 :%d 前缀 %r 路由 %d 种子用户 %d" % (
        BRAND, VERSION, PORT, PREFIX or "/", len(ROUTES), created))
    srv.serve_forever()


if __name__ == "__main__":
    main()
