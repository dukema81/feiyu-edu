# -*- coding: utf-8 -*-
"""飞育业务内核单元测试（edu.py 纯函数）。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "backend"))
import edu as K  # noqa: E402


# ---------------- GPA / 等级 ----------------
def test_gpa_scale():
    assert K.gpa_point(95) == 4.0
    assert K.gpa_point(90) == 4.0
    assert K.gpa_point(85) == 3.7
    assert K.gpa_point(78) == 3.0
    assert K.gpa_point(60) == 1.0
    assert K.gpa_point(30) == 0.0


def test_gpa_full_score_conversion():
    # 满分 150 折算百分制
    assert K.gpa_point(135, 150) == 4.0
    assert K.gpa_point(90, 150) == 1.0


def test_grade_level():
    assert K.grade_level(92) == "优"
    assert K.grade_level(85) == "良"
    assert K.grade_level(75) == "中"
    assert K.grade_level(65) == "及格"
    assert K.grade_level(40) == "不及格"
    assert K.grade_level(135, 150) == "优"


# ---------------- 成绩统计 ----------------
def test_grade_stats_basic():
    s = K.grade_stats([100, 90, 80, 70, 60, 50])
    assert s["count"] == 6
    assert s["avg"] == 75.0
    assert s["max"] == 100 and s["min"] == 50
    assert s["median"] == 75.0
    assert s["pass_rate"] == round(5 / 6 * 100, 2)
    assert s["excellent_rate"] == round(2 / 6 * 100, 2)
    assert s["stdev"] > 0


def test_grade_stats_empty():
    s = K.grade_stats([])
    assert s["count"] == 0 and s["avg"] == 0 and s["gpa"] == 0


def test_grade_stats_dicts():
    s = K.grade_stats([{"score": 90}, {"score": 60}])
    assert s["avg"] == 75.0 and s["pass_rate"] == 100.0


def test_rank_scores():
    rows = K.rank_scores([
        {"student_no": "A", "name": "甲", "score": 90},
        {"student_no": "B", "name": "乙", "score": 95},
        {"student_no": "C", "name": "丙", "score": 90},
        {"student_no": "D", "name": "丁", "score": 60},
    ])
    assert [r["rank"] for r in rows] == [1, 2, 2, 4]
    assert rows[0]["student_no"] == "B"
    assert rows[3]["level"] == "及格"


def test_weighted_avg():
    assert K.weighted_avg([{"score": 90, "credit": 3}, {"score": 70, "credit": 1}]) == 85.0
    assert K.weighted_avg([]) == 0.0
    assert K.weighted_avg([{"score": 80, "credit": 0}]) == 0.0


# ---------------- 风险评分 ----------------
def test_student_risk_levels():
    assert K.student_risk(3.5, 0, 0, 0) == {"score": 0, "grade": "正常"}
    assert K.student_risk(1.8, 0, 0, 0)["grade"] == "提"     # 30 分
    assert K.student_risk(1.8, 4, 0, 0)["grade"] == "险"   # 62 分
    assert K.student_risk(2.8, 4, 2, 0)["score"] == 40     # 32+8


def test_student_risk_capped():
    s = K.student_risk(1.5, 10, 10, 5000)
    assert s["score"] == 100 and s["grade"] == "险"


def test_student_risk_fee_signal():
    assert K.student_risk(3.0, 0, 0, 2000)["score"] == 14
    assert K.student_risk(3.0, 0, 0, 500)["score"] == 0


# ---------------- 学费 ----------------
def test_tuition_payable():
    assert K.tuition_payable(6000, 0, 0) == 6000.0
    assert K.tuition_payable(6000, 10, 0) == 5400.0
    assert K.tuition_payable(6000, 10, 400) == 5000.0
    assert K.tuition_payable(1000, 100, 0) == 0.0
    assert K.tuition_payable(-5, 0, 0) == 0.0


def test_tuition_money_rounding():
    assert K.tuition_payable("100.005", 0, 0) == 100.01   # HALF_UP 到分
    assert K.tuition_payable("0.125", 0, 0) == 0.13


def test_fee_overdue():
    assert K.fee_overdue({"status": "待缴", "due_date": "2026-01-01"}, "2026-10-01") is True
    assert K.fee_overdue({"status": "已缴清", "due_date": "2026-01-01"}, "2026-10-01") is False
    assert K.fee_overdue({"status": "待缴", "due_date": ""}, "2026-10-01") is False


# ---------------- 考勤 ----------------
def test_attendance_stats():
    recs = [{"status": "出勤"}] * 8 + [{"status": "迟到"}] * 2 + [{"status": "旷课"}]
    s = K.attendance_stats(recs)
    assert s["total"] == 11
    assert s["present"] == 10
    assert s["rate"] == round(10 / 11 * 100, 2)
    assert s["absent_days"] == 1


def test_attendance_stats_empty():
    assert K.attendance_stats([])["rate"] == 0.0


# ---------------- 排课冲突 ----------------
def test_schedule_conflicts_class():
    items = [
        {"class_no": "C1", "term": "T", "weekday": 1, "slot": 1, "course": "语文", "teacher": "甲"},
        {"class_no": "C1", "term": "T", "weekday": 1, "slot": 1, "course": "数学", "teacher": "乙"},
    ]
    cf = K.schedule_conflicts(items)
    assert len(cf) == 1 and cf[0]["type"] == "班级冲突"


def test_schedule_conflicts_teacher():
    items = [
        {"class_no": "C1", "term": "T", "weekday": 2, "slot": 3, "course": "物理", "teacher": "王"},
        {"class_no": "C2", "term": "T", "weekday": 2, "slot": 3, "course": "化学", "teacher": "王"},
    ]
    cf = K.schedule_conflicts(items)
    assert len(cf) == 1 and cf[0]["type"] == "教师冲突"


def test_schedule_no_conflict():
    items = [
        {"class_no": "C1", "term": "T", "weekday": 1, "slot": 1, "course": "语文", "teacher": "甲"},
        {"class_no": "C1", "term": "T", "weekday": 1, "slot": 2, "course": "数学", "teacher": "甲"},
    ]
    assert K.schedule_conflicts(items) == []


# ---------------- 校验 ----------------
def test_validate_student():
    assert K.validate_student({"name": "张三"}) == []
    assert "学生姓名必填" in K.validate_student({"name": ""})[0]
    assert "性别" in K.validate_student({"name": "张三", "gender": "X"})[0]
    assert "手机号" in K.validate_student({"name": "张三", "guardian_phone": "abc"})[0]


def test_validate_fee():
    assert K.validate_fee({"student_no": "ST0001", "amount": 100}) == []
    assert len(K.validate_fee({"student_no": "", "amount": 0})) == 2
    assert "折扣" in K.validate_fee({"student_no": "S", "amount": 100, "discount": 150})[0]


# ---------------- 权限 ----------------
def test_has_perm():
    assert K.has_perm(["*"], "anything")
    assert K.has_perm(["edu.read"], "edu.read")
    assert K.has_perm(["edu.*"], "edu.read")
    assert K.has_perm(["score.write"], "score.read")   # 写含读
    assert not K.has_perm(["score.read"], "score.write")
    assert not K.has_perm([], "edu.read")
