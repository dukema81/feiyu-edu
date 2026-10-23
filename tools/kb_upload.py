# -*- coding: utf-8 -*-
"""飞育教育管理系统 · 文档与DEMO批量上传知识库（分类 33 企业管理系统）"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = r"C:/Users/maxl/WorkBuddy/Claw/feiyu-edu"
BASE = "http://42.193.158.63"
CAT = 33
PASSWORD = "YCSpyVwt@J2UByom3#n6gb"
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOKEN = None
REPLACE = "--replace" in sys.argv

DOCS = [
    ("docs/feiyu_design_v1.docx", "飞育教育管理系统建设方案",
     "「飞育教育管理系统」完整建设方案 V1.0：双校区教育管理痛点与建设目标、"
     "业务口径（学籍五状态闭环、成绩等级与 GPA 4.0 制换算、学分绩加权、同分并列排名、"
     "考勤五状态与出勤率口径、学费 Decimal 精确到分、学业风险评分 0~100 分档、"
     "排课冲突双规则）、总体架构与零依赖技术选型（Python 标准库 http.server + SQLite WAL）、"
     "21 表数据模型、6 角色权限矩阵、12 页面功能清单、对外集成方案、6 阶段实施里程碑。",
     "飞育,教育管理,学籍管理,成绩管理,建设方案"),
    ("docs/feiyu_api_v1.docx", "飞育教育管理系统 REST 接口契约",
     "63 端点分组契约：统一响应包 {code,message,data} 与 HTTP 状态一致、鉴权五通道"
     "（Bearer / X-Edu-Token / Cookie / ?token= / X-Edu-Key，SHA-256 存储）、"
     "Idempotency-Key 幂等、增量同步协议（版本号 + 实体过滤）、列表统一 {list,total}、"
     "校区/教师/班级/学生/课程/排课/成绩/考勤/缴费/学籍变动/风险/政策/公告/报表/平台 全量接口表、"
     "校验规则与错误码表、Python 对接三示例（招生拉学生增量/教务录成绩/报表拉取）。",
     "飞育,API,接口契约,REST,幂等,增量同步,教育系统对接"),
    ("docs/feiyu_test_v1.docx", "飞育教育管理系统测试报告",
     "三道质量门禁全部通过：pytest 49 条（内核 20 例：GPA/等级/统计/排名/学分绩/风险评分/"
     "学费 Decimal/逾期/考勤/排课冲突/校验/权限；API 集成 29 例：认证/RBAC/学生流/排课/成绩流/"
     "考勤流/缴费流含精确金额断言/学籍变动/风险/报表/同步/幂等/静态页）；"
     "UI 巡检 Playwright 12 页面 0 控制台异常；冒烟 27 项全通过。"
     "测试中发现并修复 10 项缺陷（time.strftime 误传、traceback 缺失、密钥编码、URL 中文、"
     "GPA 折算预期、排名等级断言、风险分档、HALF_UP 进位、残缺库、代理直连）。",
     "飞育,测试报告,pytest,Playwright,质量门禁"),
    ("docs/feiyu_manual_v1.docx", "飞育教育管理系统使用手册",
     "面向全部 6 角色的操作手册：系统定位与账号表（admin/123456）、12 页面逐页说明"
     "（工作台 KPI 与趋势、学籍管理与档案、班级周课表、教师台账、课程排课与冲突高亮、"
     "成绩管理学科统计与排名、考勤统计与登记、缴费核销与新建、统计报表四合一与 CSV、"
     "预警中心一键扫描、政策公告、系统管理与接口密钥）、常用操作五节、FAQ 六条、操作技巧。",
     "飞育,使用手册,操作指南,教育管理"),
    ("demo/feiyu-edu-demo.zip", "飞育教育管理系统离线演示（DEMO）",
     "单文件离线演示：解压后双击 HTML 即可用浏览器打开，无需服务与网络。"
     "数据取自演示实例真实快照：2 校区 / 12 用户 / 10 教师 / 12 班级 / 60 学生 /"
     " 10 课程 / 285 条成绩 / 近 30 天考勤 / 120 张缴费单。"
     "12 个页签覆盖工作台、学籍管理、班级管理、教师管理、课程排课、成绩管理、"
     "考勤管理、缴费管理、统计报表、预警中心、政策公告、系统管理。"
     "支持顶部切换 4 个真实视角（管理员 / 教务主任 / 财务 / 只读）。只读快照，写操作不会真正执行。",
     "飞育,DEMO,离线演示,教育管理,学籍"),
]


def req(path, method="GET", data=None, token=None):
    r = urllib.request.Request(BASE + path, method=method)
    if data is not None:
        r.data = json.dumps(data).encode("utf-8")
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with OP.open(r, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:                                     # noqa: BLE001
            return e.code, {}


def curl_upload(path, title, desc, tags):
    full = os.path.join(ROOT, path)
    mime = "application/zip" if full.endswith(".zip") else \
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    cmd = ["curl", "-s", "--noproxy", "*",
           "-H", "Authorization: Bearer " + TOKEN,
           "-F", "file=@%s;type=%s" % (full, mime),
           "-F", "title=" + title,
           "-F", "description=" + desc,
           "-F", "categoryId=%d" % CAT,
           "-F", "tags=" + tags,
           BASE + "/api/documents/upload"]
    out = subprocess.run(cmd, capture_output=True, timeout=300)
    try:
        return json.loads(out.stdout.decode("utf-8", "ignore"))
    except Exception:                                         # noqa: BLE001
        return {"code": -1, "raw": out.stdout.decode("utf-8", "ignore")[:400],
                "err": out.stderr.decode("utf-8", "ignore")[:200]}


def existing(cat=CAT):
    st, j = req("/api/documents?categoryId=%d&pageNum=1&pageSize=200" % cat, token=TOKEN)
    data = j.get("data") or {}
    if isinstance(data, list):
        return data
    return data.get("records") or data.get("list") or []


def delete_doc(doc_id):
    return req("/api/documents/%s" % doc_id, "DELETE", token=TOKEN)


def main():
    global TOKEN
    st, j = req("/api/auth/login", "POST", {"username": "admin", "password": PASSWORD})
    assert j.get("code") == 200, j
    TOKEN = j["data"]["token"]
    print("login ok")

    if REPLACE:
        want = {t for _, t, _, _ in DOCS}
        for r in existing():
            if r.get("title") in want:
                st, j = delete_doc(r.get("id"))
                print("删除旧文档 %s id=%s -> %s" % (r.get("title"), r.get("id"), st))
                time.sleep(0.4)

    results = []
    for path, title, desc, tags in DOCS:
        j = curl_upload(path, title, desc, tags)
        code = j.get("code")
        doc_id = (j.get("data") or {}).get("id") if isinstance(j.get("data"), dict) else j.get("data")
        size = os.path.getsize(os.path.join(ROOT, path))
        print("%-28s code=%s id=%s %.1fKB" % (os.path.basename(path), code, doc_id, size / 1024.0))
        if code != 200:
            print("   !!", str(j)[:300])
        results.append((path, title, code, doc_id))
        time.sleep(1.2)

    ok = [r for r in results if r[2] == 200]
    print("\n上传成功 %d / %d" % (len(ok), len(results)))
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", "kb_upload_result.json"), "w", encoding="utf-8") as f:
        json.dump([{"file": r[0], "title": r[1], "code": r[2], "id": r[3]} for r in results],
                  f, ensure_ascii=False, indent=2)
    return results


if __name__ == "__main__":
    main()
