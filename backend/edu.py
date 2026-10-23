# -*- coding: utf-8 -*-
"""飞育教育管理系统 · 业务计算内核（纯函数，不碰 DB、无 IO）

涵盖：GPA 换算、成绩统计与排名、优良中差等级、学业预警评分、
     学费应收计算（折扣/减免）、出勤率与考勤统计、课表冲突检测、
     实体校验。金额类计算使用 Decimal 精确到分。
"""
import math
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def dec(x, default=None):
    try:
        return Decimal(str(x))
    except Exception:                                    # noqa: BLE001
        return default


def money(x):
    """金额精确到分（四舍五入）。"""
    d = dec(x, Decimal("0")) or Decimal("0")
    return float(d.quantize(CENT, rounding=ROUND_HALF_UP))


# ==================================================== GPA / 等级
GPA_SCALE = [
    (90, 4.0, "A"), (85, 3.7, "A-"), (82, 3.3, "B+"), (78, 3.0, "B"),
    (75, 2.7, "B-"), (72, 2.3, "C+"), (68, 2.0, "C"), (64, 1.5, "C-"),
    (60, 1.0, "D"), (0, 0.0, "F"),
]


def gpa_point(score, full=100):
    """百分制 → GPA 绩点（4.0 制）。支持满分非 100（按比例折算）。"""
    s = float(score or 0)
    if full and full != 100:
        s = s * 100.0 / float(full)
    for lo, pt, _ in GPA_SCALE:
        if s >= lo:
            return pt
    return 0.0


def grade_level(score, full=100):
    """百分制 → 等级：优(≥90) 良(≥80) 中(≥70) 及格(≥60) 不及格(<60)。"""
    s = float(score or 0)
    if full and full != 100:
        s = s * 100.0 / float(full)
    if s >= 90:
        return "优"
    if s >= 80:
        return "良"
    if s >= 70:
        return "中"
    if s >= 60:
        return "及格"
    return "不及格"


# ==================================================== 成绩统计
def grade_stats(scores, full=100):
    """成绩序列统计：均分/最高/最低/及格率/优秀率/标准差/中位数/GPA 均值。"""
    vals = [float(s.get("score", 0) if isinstance(s, dict) else s) for s in (scores or [])]
    n = len(vals)
    if not n:
        return {"count": 0, "avg": 0.0, "max": 0.0, "min": 0.0,
                "pass_rate": 0.0, "excellent_rate": 0.0, "stdev": 0.0,
                "median": 0.0, "gpa": 0.0}
    avg = sum(vals) / n
    passes = sum(1 for v in vals if v >= (60 if full == 100 else full * 0.6))
    excellents = sum(1 for v in vals if v >= (90 if full == 100 else full * 0.9))
    sv = sorted(vals)
    median = sv[n // 2] if n % 2 else (sv[n // 2 - 1] + sv[n // 2]) / 2
    stdev = math.sqrt(sum((v - avg) ** 2 for v in vals) / n)
    gpas = [gpa_point(v, full) for v in vals]
    return {
        "count": n, "avg": round(avg, 2), "max": round(max(vals), 2),
        "min": round(min(vals), 2),
        "pass_rate": round(passes * 100.0 / n, 2),
        "excellent_rate": round(excellents * 100.0 / n, 2),
        "stdev": round(stdev, 2), "median": round(median, 2),
        "gpa": round(sum(gpas) / n, 2),
    }


def rank_scores(scores, full=100):
    """按成绩排名（同分并列）。输入 [{student_no,name,score,...}]，输出补 rank 字段，降序。"""
    arr = sorted((scores or []), key=lambda x: -float(x.get("score", 0) or 0))
    prev, rank = None, 0
    out = []
    for i, r in enumerate(arr, 1):
        s = float(r.get("score", 0) or 0)
        if prev is None or s != prev:
            rank = i
            prev = s
        o = dict(r)
        o["rank"] = rank
        o["level"] = grade_level(s, full)
        o["gpa"] = gpa_point(s, full)
        out.append(o)
    return out


def weighted_avg(items):
    """学分绩：sum(score*credit)/sum(credit)。items: [{score, credit}]"""
    num_ = 0.0
    den = 0.0
    for it in (items or []):
        c = float(it.get("credit", 0) or 0)
        num_ += float(it.get("score", 0) or 0) * c
        den += c
    return round(num_ / den, 2) if den else 0.0


# ==================================================== 学业预警
def student_risk(gpa, fail_count, absent_days, overdue_amount=0.0):
    """学生风险评分（0~100，越高越险）：
       GPA<2 占 30 分档；挂科数 8 分/门（≤32）；旷课 4 分/天（≤24）；
       欠费 >1000 元记 14 分。"""
    sc = 0
    if gpa < 2.0:
        sc += 30
    elif gpa < 2.5:
        sc += 15
    sc += min(32, int(fail_count or 0) * 8)
    sc += min(24, int(absent_days or 0) * 4)
    if float(overdue_amount or 0) > 1000:
        sc += 14
    sc = min(100, sc)
    if sc >= 60:
        grade = "险"
    elif sc >= 35:
        grade = "警"
    elif sc > 0:
        grade = "提"
    else:
        grade = "正常"
    return {"score": sc, "grade": grade}


# ==================================================== 学费
def tuition_payable(amount, discount=0, waived=0):
    """应收 = 金额 × (1 - 折扣%) − 减免；精确到分，不为负。"""
    amt = dec(amount, Decimal("0")) or Decimal("0")
    dis = dec(discount, Decimal("0")) or Decimal("0")
    wv = dec(waived, Decimal("0")) or Decimal("0")
    payable = amt * (Decimal("100") - dis) / Decimal("100") - wv
    return money(max(Decimal("0"), payable))


def fee_overdue(fee, today_str):
    """缴费是否逾期：状态非已缴清且到期日 < today。"""
    if (fee.get("status") or "") == "已缴清":
        return False
    due = fee.get("due_date") or ""
    return bool(due and due < today_str)


# ==================================================== 考勤
ATT_STATUSES = ("出勤", "迟到", "病假", "事假", "旷课")


def attendance_stats(records):
    """考勤统计：出勤率 = (出勤+迟到)/总数；返回各状态计数。"""
    cnt = {s: 0 for s in ATT_STATUSES}
    other = 0
    for r in (records or []):
        st = (r.get("status") if isinstance(r, dict) else r) or ""
        if st in cnt:
            cnt[st] += 1
        else:
            other += 1
    total = sum(cnt.values()) + other
    present = cnt["出勤"] + cnt["迟到"]
    return {
        "total": total, "present": present, "absent_days": cnt["旷课"],
        "late": cnt["迟到"], "sick": cnt["病假"], "personal": cnt["事假"],
        "rate": round(present * 100.0 / total, 2) if total else 0.0,
    }


# ==================================================== 课表冲突
def schedule_conflicts(items):
    """检测排课冲突：同班级同学期同一 (weekday,slot) 只能一门课；
       同教师同学期同一 (weekday,slot) 只能上一个班。
       返回冲突列表 [{type, a, b}]。"""
    seen_cls, seen_tea, conflicts = {}, {}, []
    for it in (items or []):
        k_cls = (it.get("class_no"), it.get("term"), it.get("weekday"), it.get("slot"))
        k_tea = (it.get("teacher"), it.get("term"), it.get("weekday"), it.get("slot"))
        if k_cls in seen_cls:
            conflicts.append({"type": "班级冲突", "a": seen_cls[k_cls], "b": it})
        else:
            seen_cls[k_cls] = it
        if it.get("teacher") and k_tea in seen_tea:
            conflicts.append({"type": "教师冲突", "a": seen_tea[k_tea], "b": it})
        else:
            seen_tea[k_tea] = it
    return conflicts


# ==================================================== 校验
def validate_student(b):
    errs = []
    if not (b.get("name") or "").strip():
        errs.append("学生姓名必填")
    ph = (b.get("guardian_phone") or "").strip()
    if ph and not ph.isdigit():
        errs.append("监护人手机号须为数字")
    if b.get("gender") not in ("男", "女", None, ""):
        errs.append("性别只能为男/女")
    return errs


def validate_fee(b):
    errs = []
    if not (b.get("student_no") or "").strip():
        errs.append("学生必填")
    if dec(b.get("amount"), Decimal("0")) is None or float(b.get("amount") or 0) <= 0:
        errs.append("费用金额必须大于 0")
    dis = float(b.get("discount") or 0)
    if dis < 0 or dis > 100:
        errs.append("折扣须在 0~100 之间")
    return errs


# ==================================================== 权限
ROLE_PERMS = {
    "admin": ["*"],
    "principal": ["edu.read", "report.read", "risk.read", "org.read",
                  "policy.read", "dashboard.read"],
    "dean": ["edu.read", "edu.write", "score.write", "report.read",
             "risk.read", "policy.read", "dashboard.read"],
    "teacher": ["edu.read", "score.write", "dashboard.read", "report.read"],
    "finance": ["edu.read", "fee.write", "fee.read", "report.read", "dashboard.read"],
    "reader": ["dashboard.read", "edu.read", "report.read"],
}


def has_perm(perms, need):
    pl = perms or []
    if "*" in pl or need in pl:
        return True
    if "." in need:
        prefix = need.split(".")[0] + ".*"
        if prefix in pl:
            return True
        if need.endswith(".read"):
            base = need.split(".")[0] + ".write"
            if base in pl:
                return True
    return False
