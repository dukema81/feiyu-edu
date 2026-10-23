# -*- coding: utf-8 -*-
"""飞育教育管理系统 · 数据层（sqlite3 + WAL）

约定与飞税/飞控同范式：
  - 每个请求独立连接（线程安全），只在 init 时设一次 journal_mode=WAL
  - 写经 run()，读经 rows()/one()/val()
  - 单号 gen_no()：MAX 尾号递增 + 空号优先复用
"""
import os
import re
import sqlite3
import threading
import time

DB_PATH = os.environ.get("EDU_DB") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "feiyu.db")
_LOCK = threading.RLock()
_INITED = False

SCHEMA = [
    # ---------------- 组织域
    """CREATE TABLE IF NOT EXISTS depts (
        code TEXT PRIMARY KEY, name TEXT NOT NULL, parent TEXT DEFAULT '',
        leader TEXT DEFAULT '', sort INTEGER DEFAULT 0, memo TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, name TEXT NOT NULL, dept TEXT DEFAULT '',
        title TEXT DEFAULT '', role TEXT DEFAULT 'reader', phone TEXT DEFAULT '',
        email TEXT DEFAULT '', pwd TEXT DEFAULT '', status TEXT DEFAULT '启用',
        created_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS tokens (
        token TEXT PRIMARY KEY, username TEXT NOT NULL, created_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        key_hash TEXT NOT NULL, prefix TEXT DEFAULT '', scope TEXT DEFAULT 'read',
        owner TEXT DEFAULT '', status TEXT DEFAULT '启用', created_at TEXT DEFAULT '',
        last_used TEXT DEFAULT '')""",

    # ---------------- 校区
    """CREATE TABLE IF NOT EXISTS schools (
        code TEXT PRIMARY KEY, name TEXT NOT NULL, city TEXT DEFAULT '',
        address TEXT DEFAULT '', principal TEXT DEFAULT '', contact TEXT DEFAULT '',
        phone TEXT DEFAULT '', opened_at TEXT DEFAULT '',
        status TEXT DEFAULT '启用', memo TEXT DEFAULT '', created_at TEXT DEFAULT '')""",

    # ---------------- 教师
    """CREATE TABLE IF NOT EXISTS teachers (
        no TEXT PRIMARY KEY, name TEXT NOT NULL, gender TEXT DEFAULT '男',
        school TEXT DEFAULT '', subject TEXT DEFAULT '', title TEXT DEFAULT '教师',
        phone TEXT DEFAULT '', email TEXT DEFAULT '', hire_date TEXT DEFAULT '',
        status TEXT DEFAULT '在职', memo TEXT DEFAULT '', created_at TEXT DEFAULT '')""",

    # ---------------- 班级
    """CREATE TABLE IF NOT EXISTS classes (
        no TEXT PRIMARY KEY, name TEXT NOT NULL, school TEXT DEFAULT '',
        grade TEXT DEFAULT '', head_teacher TEXT DEFAULT '', room TEXT DEFAULT '',
        capacity INTEGER DEFAULT 45, student_count INTEGER DEFAULT 0,
        term TEXT DEFAULT '', status TEXT DEFAULT '在读',
        memo TEXT DEFAULT '', created_at TEXT DEFAULT '')""",

    # ---------------- 学生
    """CREATE TABLE IF NOT EXISTS students (
        no TEXT PRIMARY KEY, name TEXT NOT NULL, gender TEXT DEFAULT '男',
        school TEXT DEFAULT '', grade TEXT DEFAULT '', class_no TEXT DEFAULT '',
        birth TEXT DEFAULT '', guardian TEXT DEFAULT '', relation TEXT DEFAULT '家长',
        guardian_phone TEXT DEFAULT '', address TEXT DEFAULT '',
        enroll_date TEXT DEFAULT '', status TEXT DEFAULT '在读',
        memo TEXT DEFAULT '', created_at TEXT DEFAULT '')""",

    # ---------------- 课程
    """CREATE TABLE IF NOT EXISTS courses (
        code TEXT PRIMARY KEY, name TEXT NOT NULL, subject TEXT DEFAULT '',
        school TEXT DEFAULT '', teacher TEXT DEFAULT '', grade TEXT DEFAULT '',
        hours_per_week INTEGER DEFAULT 4, credit REAL DEFAULT 2,
        status TEXT DEFAULT '开课', memo TEXT DEFAULT '', created_at TEXT DEFAULT '')""",

    # ---------------- 排课
    """CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT, class_no TEXT DEFAULT '',
        course TEXT DEFAULT '', teacher TEXT DEFAULT '', weekday INTEGER DEFAULT 1,
        slot INTEGER DEFAULT 1, room TEXT DEFAULT '', term TEXT DEFAULT '')""",

    # ---------------- 成绩
    """CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_no TEXT DEFAULT '',
        course TEXT DEFAULT '', exam TEXT DEFAULT '期末', term TEXT DEFAULT '',
        score REAL DEFAULT 0, full_score REAL DEFAULT 100,
        graded_by TEXT DEFAULT '', graded_at TEXT DEFAULT '',
        memo TEXT DEFAULT '')""",

    # ---------------- 考勤
    """CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_no TEXT DEFAULT '',
        adate TEXT DEFAULT '', status TEXT DEFAULT '出勤',
        slot TEXT DEFAULT '', memo TEXT DEFAULT '',
        recorded_by TEXT DEFAULT '', recorded_at TEXT DEFAULT '')""",

    # ---------------- 缴费
    """CREATE TABLE IF NOT EXISTS fees (
        no TEXT PRIMARY KEY, student_no TEXT DEFAULT '', item TEXT DEFAULT '学费',
        term TEXT DEFAULT '', amount REAL DEFAULT 0, discount REAL DEFAULT 0,
        paid_amount REAL DEFAULT 0, due_date TEXT DEFAULT '', paid_at TEXT DEFAULT '',
        pay_method TEXT DEFAULT '', status TEXT DEFAULT '待缴',
        memo TEXT DEFAULT '', created_by TEXT DEFAULT '', created_at TEXT DEFAULT '')""",

    # ---------------- 学籍变动
    """CREATE TABLE IF NOT EXISTS transfers (
        no TEXT PRIMARY KEY, student_no TEXT DEFAULT '', kind TEXT DEFAULT '转班',
        from_value TEXT DEFAULT '', to_value TEXT DEFAULT '', reason TEXT DEFAULT '',
        effect_date TEXT DEFAULT '', status TEXT DEFAULT '待审批',
        approver TEXT DEFAULT '', approved_at TEXT DEFAULT '',
        memo TEXT DEFAULT '', created_by TEXT DEFAULT '', created_at TEXT DEFAULT '')""",

    # ---------------- 预警/政策
    """CREATE TABLE IF NOT EXISTS risks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, school TEXT DEFAULT '',
        code TEXT DEFAULT '', level TEXT DEFAULT '提', title TEXT DEFAULT '',
        detail TEXT DEFAULT '', weight INTEGER DEFAULT 10,
        status TEXT DEFAULT '待处理', handler TEXT DEFAULT '',
        created_at TEXT DEFAULT '', closed_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS policies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        doc_no TEXT DEFAULT '', category TEXT DEFAULT '', effect_date TEXT DEFAULT '',
        expire_date TEXT DEFAULT '', summary TEXT DEFAULT '', content TEXT DEFAULT '',
        tags TEXT DEFAULT '', status TEXT DEFAULT '有效', created_at TEXT DEFAULT '')""",

    # ---------------- 平台域
    """CREATE TABLE IF NOT EXISTS notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        body TEXT DEFAULT '', author TEXT DEFAULT '', top INTEGER DEFAULT 0,
        created_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT DEFAULT '',
        username TEXT DEFAULT '', action TEXT DEFAULT '', target TEXT DEFAULT '',
        detail TEXT DEFAULT '', ip TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS idem_keys (
        key TEXT PRIMARY KEY, username TEXT DEFAULT '', path TEXT DEFAULT '',
        status INTEGER DEFAULT 200, body TEXT DEFAULT '', created_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS sync_state (
        entity TEXT PRIMARY KEY, version INTEGER DEFAULT 0, updated_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS edu_rules (
        key TEXT PRIMARY KEY, value TEXT DEFAULT '')""",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_stu_class ON students(class_no, status)",
    "CREATE INDEX IF NOT EXISTS idx_stu_school ON students(school, grade)",
    "CREATE INDEX IF NOT EXISTS idx_score_stu ON scores(student_no, term)",
    "CREATE INDEX IF NOT EXISTS idx_score_course ON scores(course, exam)",
    "CREATE INDEX IF NOT EXISTS idx_att_stu ON attendance(student_no, adate)",
    "CREATE INDEX IF NOT EXISTS idx_fee_stu ON fees(student_no, status)",
    "CREATE INDEX IF NOT EXISTS idx_sch_class ON schedule(class_no, term)",
    "CREATE INDEX IF NOT EXISTS idx_log_ts ON logs(ts)",
]


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def today():
    return time.strftime("%Y-%m-%d")


def connect():
    d = os.path.dirname(DB_PATH)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=15000")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init():
    global _INITED
    with _LOCK:
        c = connect()
        if not _INITED:
            c.execute("PRAGMA journal_mode=WAL")
            _INITED = True
        for sql in SCHEMA:
            c.execute(sql)
        for sql in INDEXES:
            c.execute(sql)
        c.commit()
        c.close()


def rows(sql, args=()):
    with _LOCK:
        c = connect()
        try:
            return [dict(r) for r in c.execute(sql, args).fetchall()]
        finally:
            c.close()


def one(sql, args=()):
    with _LOCK:
        c = connect()
        try:
            r = c.execute(sql, args).fetchone()
            return dict(r) if r else None
        finally:
            c.close()


def val(sql, args=(), default=None):
    r = one(sql, args)
    if r is None:
        return default
    v = list(r.values())[0]
    return default if v is None else v


def run(sql, args=()):
    with _LOCK:
        c = connect()
        try:
            cur = c.execute(sql, args)
            c.commit()
            return cur.rowcount
        finally:
            c.close()


def insert(table, data):
    keys = list(data.keys())
    sql = "INSERT INTO %s (%s) VALUES (%s)" % (
        table, ",".join(keys), ",".join("?" * len(keys)))
    run(sql, tuple(data[k] for k in keys))
    return data


def gen_no(table, prefix, col="no"):
    pat = re.compile(r"^%s(\d+)$" % re.escape(prefix))
    used = set()
    for r in rows("SELECT %s AS c FROM %s" % (col, table)):
        m = pat.match(str(r["c"] or ""))
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return "%s%04d" % (prefix, n)


def bumpsync(*entities):
    ts = now()
    for e in entities:
        if val("SELECT 1 FROM sync_state WHERE entity=?", (e,)):
            run("UPDATE sync_state SET version=version+1, updated_at=? WHERE entity=?", (ts, e))
        else:
            run("INSERT INTO sync_state (entity,version,updated_at) VALUES (?,1,?)", (e, ts))


def version_of(entity):
    return int(val("SELECT version FROM sync_state WHERE entity=?", (entity,), 0) or 0)


def rule(key, default=""):
    v = val("SELECT value FROM edu_rules WHERE key=?", (key,), None)
    return default if v is None else v


def set_rule(key, value):
    if val("SELECT 1 FROM edu_rules WHERE key=?", (key,)):
        run("UPDATE edu_rules SET value=? WHERE key=?", (str(value), key))
    else:
        run("INSERT INTO edu_rules (key,value) VALUES (?,?)", (key, str(value)))
