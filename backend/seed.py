# -*- coding: utf-8 -*-
"""飞育教育管理系统 · 种子数据

首次启动（库为空）时写入：2 校区 / 6 部门 / 12 用户 / 10 教师 /
8 班级 / 60 学生 / 10 课程 / 排课 / 3 次考试成绩 / 近 30 天考勤 /
缴费台账 / 学籍变动 / 预警 / 政策 / 公告。幂等：已有用户则跳过。
"""
import hashlib
import json
import random
import time

import db


def sha(s):
    return hashlib.sha256(str(s).encode()).hexdigest()


DEPTS = [
    ("D001", "校长办公室", "", "王校长", 1),
    ("D002", "教务处", "", "李主任", 2),
    ("D003", "学生处", "", "张主任", 3),
    ("D004", "财务处", "", "陈会计", 4),
    ("D005", "后勤保障部", "", "刘主管", 5),
    ("D006", "招生办", "", "赵主管", 6),
]

USERS = [
    ("admin", "系统管理员", "D001", "管理员", "admin"),
    ("wangzx", "王志远", "D001", "校长", "principal"),
    ("lijw", "李静雯", "D002", "教务主任", "dean"),
    ("zhanghf", "张慧芳", "D003", "学生处主任", "dean"),
    ("chenmm", "陈美美", "D004", "财务会计", "finance"),
    ("liuyg", "刘永刚", "D005", "后勤主管", "reader"),
    ("zhaolx", "赵凌雪", "D006", "招生主管", "reader"),
    ("t01", "孙国栋", "D002", "数学教师/班主任", "teacher"),
    ("t02", "周雅琴", "D002", "语文教师/班主任", "teacher"),
    ("t03", "吴天宇", "D002", "英语教师", "teacher"),
    ("t04", "郑晓岚", "D002", "物理教师", "teacher"),
    ("reader01", "何访客", "D006", "只读用户", "reader"),
]
DEFAULT_PWD = "123456"

SCHOOLS = [
    ("S01", "飞育实验中学", "杭州", "西湖区文三路 128 号", "王志远", "钱老师", "13900000001", "2012-09-01"),
    ("S02", "飞育滨江分校", "杭州", "滨江区江南大道 88 号", "张慧芳", "沈老师", "13900000002", "2018-09-01"),
]

SUBJECTS = ["语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "体育"]
SUBJ_TEACHERS = {"语文": "周雅琴", "数学": "孙国栋", "英语": "吴天宇", "物理": "郑晓岚"}

FIRST = ["陈", "林", "黄", "徐", "杨", "何", "高", "罗", "宋", "唐", "许", "韩", "冯", "邓", "曹", "彭"]
SECOND = ["子轩", "雨桐", "浩然", "欣怡", "宇轩", "诗涵", "梓豪", "可欣", "俊杰", "梦琪",
          "一鸣", "思远", "佳琪", "博文", "嘉懿", "若曦"]
GRADES = [("高一", "C1"), ("高二", "C2"), ("高三", "C3")]


def seed():
    if db.val("SELECT COUNT(*) FROM users", (), 0):
        return 0
    rnd = random.Random(20261023)
    ts = db.now()

    for code, name, parent, leader, sort in DEPTS:
        db.insert("depts", {"code": code, "name": name, "parent": parent,
                            "leader": leader, "sort": sort})
    for un, name, dept, title, role in USERS:
        db.insert("users", {
            "username": un, "name": name, "dept": dept, "title": title,
            "role": role, "phone": "138%08d" % rnd.randint(1, 99999999),
            "email": "%s@feiyu.cn" % un, "pwd": sha(DEFAULT_PWD),
            "status": "启用", "created_at": ts})

    for row in SCHOOLS:
        db.insert("schools", dict(zip(
            ["code", "name", "city", "address", "principal", "contact", "phone",
             "opened_at"], row), ) | {"status": "启用", "created_at": ts})

    # 教师 10 名
    teacher_names = ["孙国栋", "周雅琴", "吴天宇", "郑晓岚", "马春华",
                     "冯秋实", "褚文澜", "卫青禾", "蒋月明", "沈星河"]
    subj_cycle = ["数学", "语文", "英语", "物理", "化学", "生物", "历史", "地理", "体育", "信息"]
    for i, nm in enumerate(teacher_names, 1):
        db.insert("teachers", {
            "no": "T%04d" % i, "name": nm, "gender": "女" if i % 3 == 0 else "男",
            "school": "S01" if i <= 7 else "S02", "subject": subj_cycle[i - 1],
            "title": rnd.choice(["教师", "高级教师", "一级教师"]),
            "phone": "137%08d" % rnd.randint(1, 99999999),
            "email": "t%02d@feiyu.cn" % i, "hire_date": "20%02d-08-15" % rnd.randint(10, 24),
            "status": "在职", "created_at": ts})

    # 班级 8 个：三校区 × 年级
    class_list = []
    ci = 0
    for grade, _ in GRADES:
        for s in ("S01", "S02"):
            for k in (1, 2):
                ci += 1
                no = "CLS%03d" % ci
                name = "%s(%d)班" % (grade, k)
                ht = teacher_names[(ci - 1) % len(teacher_names)]
                db.insert("classes", {
                    "no": no, "name": name, "school": s, "grade": grade,
                    "head_teacher": ht, "room": "教学楼%s-%d" % (grade[:1], k),
                    "capacity": 45, "student_count": 0, "term": "2026-2027-1",
                    "status": "在读", "created_at": ts})
                class_list.append((no, grade, s))

    # 学生 60 名
    used_names = set()
    for i in range(1, 61):
        cls = class_list[(i - 1) % len(class_list)]
        while True:
            nm = rnd.choice(FIRST) + rnd.choice(SECOND)
            if nm not in used_names:
                used_names.add(nm)
                break
        g = "男" if i % 2 else "女"
        db.insert("students", {
            "no": "ST%04d" % i, "name": nm, "gender": g,
            "school": cls[2], "grade": cls[1], "class_no": cls[0],
            "birth": "20%02d-%02d-%02d" % (rnd.randint(8, 10), rnd.randint(1, 12), rnd.randint(1, 28)),
            "guardian": rnd.choice(FIRST) + "家长", "relation": rnd.choice(["父亲", "母亲"]),
            "guardian_phone": "135%08d" % rnd.randint(1, 99999999),
            "address": "杭州市%02d 小区 %d 幢" % (rnd.randint(1, 30), rnd.randint(1, 20)),
            "enroll_date": "2024-09-01", "status": "在读", "created_at": ts})

    for cls in class_list:
        db.run("UPDATE classes SET student_count=(SELECT COUNT(*) FROM students "
               "WHERE class_no=? AND status='在读') WHERE no=?", (cls[0], cls[0]))

    # 课程 10 门
    course_rows = []
    for i, (nm, sub) in enumerate(zip(
            ["语文必修", "数学必修", "英语必修", "物理必修", "化学选修",
             "生物选修", "历史必修", "地理选修", "体育", "信息素养"],
            subj_cycle), 1):
        code = "KC%03d" % i
        teacher = SUBJ_TEACHERS.get(sub) or teacher_names[i - 1]
        db.insert("courses", {
            "code": code, "name": nm, "subject": sub, "school": "S01",
            "teacher": teacher, "grade": "高一",
            "hours_per_week": rnd.choice([2, 3, 4, 5]),
            "credit": rnd.choice([1, 2, 3]), "status": "开课", "created_at": ts})
        course_rows.append((code, teacher))

    # 排课：每班每周 5×4 格，填 12 门课/班
    for cls in class_list:
        n = 0
        for wd in range(1, 6):
            for slot in range(1, 5):
                if n >= 14:
                    break
                code, teacher = course_rows[(hash(cls[0]) + n) % len(course_rows)]
                db.insert("schedule", {
                    "class_no": cls[0], "course": code, "teacher": teacher,
                    "weekday": wd, "slot": slot,
                    "room": "教室%d%02d" % (wd, slot), "term": "2026-2027-1"})
                n += 1

    # 成绩：期中+期末，各班三门主课
    terms = ["2026-2027-1"]
    for stu in db.rows("SELECT no, class_no FROM students"):
        base = rnd.randint(55, 95)
        for exam in ("期中", "期末"):
            base += rnd.randint(-5, 5)
            for code, _ in course_rows[:3]:
                db.insert("scores", {
                    "student_no": stu["no"], "course": code, "exam": exam,
                    "term": terms[0], "score": max(20, min(100, base + rnd.randint(-12, 12))),
                    "full_score": 100, "graded_by": "lijw", "graded_at": ts})

    # 考勤：近 30 天
    today = time.strftime("%Y-%m-%d")
    for i in range(30, 0, -1):
        d = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * i))
        if time.strptime(d, "%Y-%m-%d").tm_wday >= 5:
            continue
        for stu in db.rows("SELECT no FROM students"):
            r = rnd.random()
            st = "出勤" if r < 0.92 else ("迟到" if r < 0.95 else
                                          "病假" if r < 0.97 else "事假" if r < 0.99 else "旷课")
            db.insert("attendance", {
                "student_no": stu["no"], "adate": d, "status": st, "slot": "上午",
                "recorded_by": "t01", "recorded_at": ts})

    # 缴费台账
    for stu in db.rows("SELECT no FROM students"):
        for term, amt in [("2025-2026-2", 6000), ("2026-2027-1", 6200)]:
            r = rnd.random()
            paid = amt if r < 0.7 else (amt / 2 if r < 0.9 else 0)
            status = "已缴清" if paid >= amt else ("部分缴费" if paid > 0 else "待缴")
            due = "2026-09-15" if term == "2026-2027-1" else "2026-03-01"
            db.insert("fees", {
                "no": db.gen_no("fees", "F"), "student_no": stu["no"],
                "item": "学费", "term": term, "amount": amt, "discount": 0,
                "paid_amount": paid, "due_date": due,
                "paid_at": ts if paid >= amt else "",
                "pay_method": rnd.choice(["银行转账", "扫码", "现金"]) if paid else "",
                "status": status, "created_by": "chenmm", "created_at": ts})

    # 学籍变动
    for i, stu in enumerate(db.rows("SELECT no, class_no FROM students LIMIT 6"), 1):
        kind = ["转班", "转入", "转出", "休学", "复学", "退学"][i - 1]
        db.insert("transfers", {
            "no": "TR%03d" % i, "student_no": stu["no"], "kind": kind,
            "from_value": stu["class_no"] if kind == "转班" else "",
            "to_value": class_list[i % len(class_list)][0] if kind == "转班" else "",
            "reason": rnd.choice(["家庭搬迁", "个人发展", "健康原因", "学籍调整"]),
            "effect_date": "2026-0%d-01" % rnd.randint(1, 9),
            "status": rnd.choice(["待审批", "已审批", "已驳回"]),
            "approver": "lijw" if i % 2 else "", "created_by": "zhanghf", "created_at": ts})

    # 预警示例
    db.insert("risks", {"school": "S01", "code": "R-SCORE", "level": "警",
                        "title": "2 名学生期末成绩明显下滑",
                        "detail": "ST0007、ST0023 数学成绩环比下降 15 分以上，建议班主任面谈",
                        "weight": 60, "status": "待处理", "created_at": ts})
    db.insert("risks", {"school": "S01", "code": "R-FEE", "level": "险",
                        "title": "4 名学生学费逾期未缴",
                        "detail": "2025-2026-2 学期学费到期未缴清，请财务跟进",
                        "weight": 75, "status": "待处理", "created_at": ts})
    db.insert("risks", {"school": "S02", "code": "R-ATT", "level": "提",
                        "title": "滨江分校 10 月旷课人次环比上升",
                        "detail": "旷课 5 人次（上月 2 人次），建议学生处关注",
                        "weight": 40, "status": "待处理", "created_at": ts})

    # 政策
    for t, cat, summ in [
        ("教育部关于加强中小学生学籍管理的指导意见", "学籍管理",
         "规范学籍建立、变动、毕业各环节流程，一人一籍、籍随人走"),
        ("双减政策下的课程与作业管理规定", "课程管理",
         "控制作业总量，初中每天不超过 90 分钟；丰富课后服务供给"),
        ("学校收费管理与退费办法", "财务管理",
         "学费按学期收取，退学按月折算退费，严禁跨学期预收"),
        ("学生体质健康监测实施办法", "学生管理",
         "每学年开展体质健康测试并建档，测试结果纳入综合素质评价"),
    ]:
        db.insert("policies", {"title": t, "doc_no": "教基〔2026〕第%d号" % (len(t) % 9 + 1),
                               "category": cat, "effect_date": "2026-01-01",
                               "expire_date": "2028-12-31", "summary": summ,
                               "tags": "教育,规范", "status": "有效", "created_at": ts})

    # 公告
    for title, body, top in [
        ("2026-2027-1 学期期中考试安排发布", "期中考试定于 11 月 4-6 日进行，请各班教务提前排布考场", 1),
        ("学费缴纳通道已开启", "本学期学费可通过线上缴费通道办理，截止 9 月 15 日", 1),
        ("新学期教研活动通知", "每周三下午各学科组集中教研，地点：行政楼 302", 0),
        ("校园运动会报名开始", "10 月 28-29 日举行秋季运动会，各班即日起报名", 0),
    ]:
        db.insert("notices", {"title": title, "body": body, "author": "admin",
                              "top": top, "created_at": ts})

    # 参数规则
    db.set_rule("warn_gpa", "2.0")
    db.set_rule("fee_due", "2026-09-15")
    db.set_rule("absent_warn_days", "3")
    db.set_rule("excellent_line", "90")

    for e in ("students", "scores", "fees", "attendance", "classes", "courses"):
        db.bumpsync(e)
    return len(USERS)
