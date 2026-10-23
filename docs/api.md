# 飞育教育管理系统 · API 接口契约

**版本**：v1.0　**日期**：2026-10　**路由总数**：63

---

## 1. 通用约定

### 1.1 响应包

```json
{ "code": 200, "message": "ok", "data": { } }
```

`code` 与 HTTP 状态码一致：200 成功；400 参数错误；401 未登录；403 无权限；404 不存在；500 内部错误。

### 1.2 鉴权（五通道，任选其一）

| 方式 | 示例 |
| --- | --- |
| Bearer | `Authorization: Bearer <token>` |
| 自定义头 | `X-Edu-Token: <token>` |
| Cookie | `edu_token=<token>` |
| URL 参数 | `GET /api/students?token=<token>` |
| 接口密钥 | `X-Edu-Key: fk_xxx`（服务端存 SHA-256） |

### 1.3 幂等

写接口可携带 `Idempotency-Key: <uuid>`；重复请求直接返回首次结果（存 `idem_keys` 表）。

### 1.4 增量同步

```
GET /api/sync/version                          → {students: 12, scores: 5, ...}
GET /api/sync?version=students:3&entities=students,scores
```

版本号变化才返回 `data`，未变化只返回 `version`。

### 1.5 列表返回

列表型接口统一返回 `{list: [...], total: n}`。

---

## 2. 认证与平台

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/health | - | 健康检查（品牌/版本/路由数/计数） |
| GET | /api/apidoc | - | 全量路由清单 + 对接说明 |
| POST | /api/auth/login | - | 登录 `{username, password}` → `{token, name, role}` |
| POST | /api/auth/logout | - | 注销 `{token}` |
| GET | /api/auth/me | 登录 | 当前用户信息 + 权限点 |
| POST | /api/auth/change-password | 登录 | 改密 `{old_password, new_password}` |

## 3. 工作台

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/dashboard?term= | dashboard.read | KPI + 趋势 + 学科均分 + 待办 + 公告 + 预警 |

## 4. 校区

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/schools?kw= | edu.read | 校区列表 |
| GET | /api/schools/{code} | edu.read | 校区详情 + 统计 |
| POST | /api/schools/save | edu.write | 新建/更新 `{code?, name, city...}` |

## 5. 教师

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/teachers?kw=&school= | edu.read | 教师列表 |
| GET | /api/teachers/{no} | edu.read | 教师详情（课程/排课/带班统计） |
| POST | /api/teachers/save | edu.write | 新建/更新 `{no?, name, subject...}` |

## 6. 班级

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/classes?kw=&grade= | edu.read | 班级列表 |
| GET | /api/classes/{no} | edu.read | 班级详情（students + schedule） |
| POST | /api/classes/save | edu.write | 新建/更新，自动重算人数 |

## 7. 学生

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/students?kw=&class_no=&grade=&status= | edu.read | 学生列表 |
| GET | /api/students/{no} | edu.read | 学生档案（成绩/成绩单/GPA/考勤/缴费/变动） |
| POST | /api/students/save | edu.write | 新建/更新 `{no?, name, class_no, grade, guardian_phone...}` |
| POST | /api/students/status | edu.write | 学籍状态变更 `{no, status∈在读/休学/转出/毕业/退学}` |

校验规则：姓名必填；性别只能男/女；监护人手机号须为数字。

## 8. 课程与排课

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/courses?kw= | edu.read | 课程列表 |
| GET | /api/courses/{code} | edu.read | 课程详情 + 统计 |
| POST | /api/courses/save | edu.write | 新建/更新 `{code?, name, subject, teacher, credit...}` |
| GET | /api/schedule?class_no=&term=&with_conflicts=1 | edu.read | 课表（可带冲突检测） |
| POST | /api/schedule/save | edu.write | 批量排课 `{items:[{class_no, course, weekday, slot...}]}` |
| GET | /api/schedule/conflicts?term= | edu.read | 冲突清单（班级冲突/教师冲突） |

weekday 1~7（周一~周日），slot 1~12。

## 9. 成绩

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/scores?student_no=&course=&exam=&term= | edu.read | 成绩明细 |
| POST | /api/scores/save | score.write | 批量录入/覆盖 `{items:[{student_no, course, exam, score}]}` |
| GET | /api/scores/analysis?term=&exam=&class_no=&course= | edu.read | 学科统计 + TOP10 |
| GET | /api/scores/rank?class_no=&term=&exam= | edu.read | 班级总分排名（同分并列） |
| GET | /api/scores/transcript/{no} | edu.read | 成绩单（等级/GPA/学分绩/班级排名） |

同一学生×课程×考试×学期重复录入为覆盖更新。成绩须 0 ≤ score ≤ full_score。

## 10. 考勤

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/attendance?student_no=&class_no=&adate= | edu.read | 考勤明细 |
| POST | /api/attendance/save | edu.write | 批量登记 `{items:[{student_no, status}]}` |
| GET | /api/attendance/stats?days=30&class_no= | edu.read | 出勤统计（总体 + 按学生） |

status ∈ 出勤/迟到/病假/事假/旷课。

## 11. 缴费

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/fees?student_no=&term=&status= | edu.read | 缴费单列表 |
| POST | /api/fees/save | fee.write | 新建/更新（自动算应收与状态） |
| POST | /api/fees/pay | fee.write | 核销 `{no, amount, pay_method}`，满额自动缴清，幂等 |
| GET | /api/fees/summary?term= | edu.read | 收缴汇总（应收/已收/收缴率/逾期单） |

应收 = 金额 × (1−折扣%) − 减免，Decimal 精确到分。折扣 0~100。

## 12. 学籍变动

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/transfers?student_no=&status= | edu.read | 变动单列表 |
| POST | /api/transfers/save | edu.write | 申请 `{student_no, kind, to_value, reason}` |
| POST | /api/transfers/approve | edu.write | 审批 `{no, action: approve/reject}` |

kind ∈ 转班/转入/转出/休学/复学/退学/毕业。转班审批通过自动迁移班级并重算人数。

## 13. 风险预警

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/risks?status= | risk.read | 预警列表 |
| POST | /api/risks/scan | risk.read | 执行扫描（欠费逾期/学业/旷课三类），返回新增清单 |
| POST | /api/risks/close | risk.read | 处理 `{id}` |

## 14. 政策 / 公告

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/policies?kw= | edu.read | 政策列表 |
| GET | /api/policies/{id} | edu.read | 政策详情 |
| GET | /api/notices | - | 公告列表 |
| POST | /api/notices/save | edu.write | 发布公告 `{title, body, top}` |

## 15. 报表

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/reports/summary | report.read | 四合一总览（教学/学业/考勤/收费） |
| GET | /api/reports/trend?class_no=&course= | report.read | 考试均分趋势 |
| GET | /api/reports/attendance?days=&class_no= | report.read | 考勤报表 |
| GET | /api/reports/fee?term= | report.read | 收费报表 |
| GET | /api/reports/grade-dist?term=&exam= | report.read | 等级分布 |
| GET | /api/reports/export | report.read | 学生名单 CSV（UTF-8 BOM） |

## 16. 平台管理

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/users | org.read | 用户列表 |
| POST | /api/users/save | org.read | 用户信息维护（不开放自助建号） |
| GET | /api/roles | org.read | 角色 + 权限点矩阵 |
| GET | /api/depts | org.read | 部门列表 |
| GET | /api/logs | system.read | 操作日志（最近 300 条） |
| GET | /api/api-keys | system.read | 密钥列表 |
| POST | /api/api-keys/create | system.read | 生成密钥（明文仅展示一次） |
| GET | /api/sync/version | edu.read | 各实体同步版本 |
| GET | /api/sync | edu.read | 增量同步 |

## 17. 错误码

| code | 含义 |
| --- | --- |
| 200 | 成功 |
| 400 | 参数错误（message 带原因） |
| 401 | 未登录 / 凭证无效 |
| 403 | 无权限（message 带 `需要 xxx`） |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

## 18. 对接示例（Python）

```python
import requests
BASE = "http://42.193.158.63/edu"

# 1. 密钥方式拉取学生（增量）
r = requests.get(BASE + "/api/sync",
    params={"version": "students:0", "entities": "students"},
    headers={"X-Edu-Key": "fk_xxx"}).json()
students = r["data"]["entities"]["students"]["data"]

# 2. Token 方式批量录入成绩
token = requests.post(BASE + "/api/auth/login",
    json={"username": "lijw", "password": "***"}).json()["data"]["token"]
requests.post(BASE + "/api/scores/save",
    json={"items": [{"student_no": "ST0001", "course": "KC001",
                     "exam": "期末", "score": 92}]},
    headers={"Authorization": "Bearer " + token,
             "Idempotency-Key": "score-2026-final-001"})

# 3. 报表
r = requests.get(BASE + "/api/reports/summary",
                 headers={"Authorization": "Bearer " + token}).json()
```
