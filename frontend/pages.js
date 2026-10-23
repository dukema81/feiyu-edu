/* 飞育教育管理系统 · 页面层（12 页） */
var PAGES = {};

/* ---------- 工作台 ---------- */
PAGES.dash = function (el) {
  return GET('/api/dashboard').then(function (r) {
    var d = r.data || {};
    var k = d.kpi || {};
    el.innerHTML =
      '<div class="pagehead"><h2>工作台</h2><span class="sub">学期 ' + esc(d.term || '') +
      '</span><span class="flex"></span>' +
      (perm('risk.read') ? '<button class="btn sm" id="btn-scan">执行风险扫描</button>' : '') +
      '</div>' +
      '<div class="kpis">' +
      kpi(k.students || 0, '在读学生') + kpi(k.teachers || 0, '在职教师') +
      kpi(k.classes || 0, '班级') + kpi(k.courses || 0, '开课课程') +
      kpi(fmtPct(k.attendanceRate), '近30天出勤率') +
      kpi(k.riskOpen || 0, '待处理预警', (k.riskHigh || 0) > 0 ? 'hot' : '') +
      '</div>' +
      '<div class="grid2">' +
      '<div class="card"><h3>考试均分趋势</h3>' +
      barChart(d.trend || [], 'exam', [{key: 'avg', name: '均分'}]) + '</div>' +
      '<div class="card"><h3>学科均分排行</h3>' +
      rankList((d.byCourse || []).slice(0, 8), 'name', 'avg', false) + '</div>' +
      '</div>' +
      '<div class="grid2">' +
      '<div class="card"><h3>缴费情况</h3><div class="toolbar">' +
      kpi(fmtWan(k.feePaid), '已收') + kpi(fmtWan(k.feeAmount), '应收') +
      kpi(k.feeOverdue || 0, '逾期单') + '</div></div>' +
      '<div class="card"><h3>待办</h3>' +
      table(['类型', '单号', '学生', '状态', '日期'], (d.pendingFees || []).slice(0, 4)
        .map(function (f) { return f; }).concat((d.pendingTransfers || []).map(function (t) {
          return {no: t.no, student_no: t.student_no, status: t.status, due_date: t.effect_date};
        })), function (f) {
        return '<tr><td>' + (f.item ? '缴费' : '学籍变动') + '</td><td>' + esc(f.no) +
          '</td><td>' + esc(f.student_no) + '</td><td>' + statusTag(f.status) +
          '</td><td>' + fmtDate(f.due_date) + '</td></tr>';
      }) + '</div>' +
      '</div>' +
      '<div class="grid2">' +
      '<div class="card"><h3>公告</h3>' + (d.notices || []).map(function (n) {
        return '<div class="rowitem' + (n.top ? ' hot' : '') + '">' +
          (n.top ? '<b>[置顶]</b> ' : '') + esc(n.title) + '<i>' + fmtDate(n.created_at) +
          '</i></div>';
      }).join('') + '</div>' +
      '<div class="card"><h3>预警</h3>' +
      table(['级别', '标题', '状态'], d.risks || [], function (r) {
        return '<tr><td>' + levelTag(r.level) + '</td><td>' + esc(r.title) +
          '</td><td>' + statusTag(r.status) + '</td></tr>';
      }) + '</div></div>';
    var btn = document.getElementById('btn-scan');
    if (btn) btn.onclick = function () {
      btn.disabled = true;
      POST('/api/risks/scan', {}).then(function (r2) {
        toast('扫描完成，新增预警 ' + (r2.data.count || 0) + ' 条');
        go('dash');
      }).catch(function (e) { toast(e.message, true); btn.disabled = false; });
    };
  });
};

/* ---------- 学籍管理 ---------- */
PAGES.student = function (el) {
  function load(kw) {
    return GET('/api/students' + qs({kw: kw})).then(function (r) {
      var list = (r.data || {}).list || [];
      el.innerHTML =
        '<div class="pagehead"><h2>学籍管理</h2><span class="sub">' + list.length +
        ' 名学生</span><span class="flex"></span>' +
        '<input id="skw" placeholder="姓名/学号/家长" value="' + esc(kw || '') + '">' +
        (perm('edu.write') ? '<button class="btn" id="btn-add">+ 新增学生</button>' : '') +
        (perm('report.read') ? '<button class="btn ghost" id="btn-csv">导出名单</button>' : '') +
        '</div>' +
        table(['学号', '姓名', '性别', '班级', '年级', '监护人', '联系电话', '状态', ''],
          list, function (s) {
          return '<tr><td>' + esc(s.no) + '</td><td><b>' + esc(s.name) + '</b></td><td>' +
            esc(s.gender) + '</td><td>' + esc(s.class_no) + '</td><td>' + esc(s.grade) +
            '</td><td>' + esc(s.guardian) + '</td><td>' + esc(s.guardian_phone) +
            '</td><td>' + statusTag(s.status) + '</td>' +
            '<td><button class="btn sm ghost" data-no="' + esc(s.no) + '">档案</button></td></tr>';
        });
      el.querySelectorAll('button[data-no]').forEach(function (b) {
        b.onclick = function () { showProfile(b.getAttribute('data-no')); };
      });
      var i = document.getElementById('skw');
      i.onkeydown = function (e) { if (e.key === 'Enter') load(i.value.trim()); };
      var csv = document.getElementById('btn-csv');
      if (csv) csv.onclick = function () { dl('/api/reports/export', 'students.csv'); };
      var add = document.getElementById('btn-add');
      if (add) add.onclick = function () { editStudent(null); };
    });
  }
  function editStudent(no) {
    var p = no ? GET('/api/students/' + no) : Promise.resolve({data: {}});
    p.then(function (r) {
      var s = r.data || {};
      GET('/api/classes').then(function (rc) {
        var cls = ((rc.data || {}).list || []).map(function (c) {
          return '<option value="' + esc(c.no) + '"' + (c.no === s.class_no ? ' selected' : '') +
            '>' + esc(c.name) + '</option>';
        }).join('');
        modal('<h3>' + (no ? '编辑学生 ' + esc(no) : '新增学生') + '</h3>' +
          field('姓名', '<input id="f-name" value="' + esc(s.name || '') + '">') +
          field('性别', '<select id="f-g"><option>男</option><option>女</option></select>') +
          field('班级', '<select id="f-cls">' + cls + '</select>') +
          field('监护人', '<input id="f-gd" value="' + esc(s.guardian || '') + '">') +
          field('联系电话', '<input id="f-ph" value="' + esc(s.guardian_phone || '') + '">') +
          '<div class="toolbar right"><button class="btn ghost" onclick="closeModal()">取消</button>' +
          '<button class="btn" id="f-save">保存</button></div>');
        document.getElementById('f-g').value = s.gender || '男';
        document.getElementById('f-save').onclick = function () {
          var clsNo = document.getElementById('f-cls').value;
          var grade = '';
          (rc.data.list || []).forEach(function (c) {
            if (c.no === clsNo) grade = c.grade;
          });
          POST('/api/students/save', {
            no: no || '', name: document.getElementById('f-name').value.trim(),
            gender: document.getElementById('f-g').value, class_no: clsNo, grade: grade,
            guardian: document.getElementById('f-gd').value.trim(),
            guardian_phone: document.getElementById('f-ph').value.trim(),
            school: s.school || 'S01'
          }).then(function () {
            closeModal(); toast('已保存'); load('');
          }).catch(function (e) { toast(e.message, true); });
        };
      });
    });
  }
  function showProfile(no) {
    GET('/api/students/' + no).then(function (r) {
      var s = r.data || {};
      var att = s.attendance || {};
      modal('<h3>学生档案 · ' + esc(s.name) + '（' + esc(s.no) + '）</h3>' +
        '<div class="toolbar">' + tag((s.className || '') + ' · ' + (s.grade || '')) +
        statusTag(s.status) + tag('GPA ' + (s.gpa || 0)) +
        tag('出勤率 ' + fmtPct(att.rate)) + '</div>' +
        '<h4>近期成绩</h4>' +
        table(['课程', '考试', '成绩', '等级'], (s.scores || []).slice(-10), function (sc) {
          return '<tr><td>' + esc(sc.course) + '</td><td>' + esc(sc.exam) + '</td><td>' +
            sc.score + '</td><td>' + level2(levelText(sc.score)) + '</td></tr>';
        }) +
        '<h4>缴费记录</h4>' +
        table(['单号', '学期', '金额', '已缴', '状态'], s.fees || [], function (f) {
          return '<tr><td>' + esc(f.no) + '</td><td>' + esc(f.term) + '</td><td>' +
            fmtMoney(f.amount) + '</td><td>' + fmtMoney(f.paid_amount) + '</td><td>' +
            statusTag(f.status) + '</td></tr>';
        }) +
        '<div class="toolbar right"><button class="btn ghost" onclick="closeModal()">关闭</button></div>', true);
    });
  }
  function levelText(v) { return Number(v); }
  return load('');
};

/* ---------- 班级管理 ---------- */
PAGES.clazz = function (el) {
  return GET('/api/classes').then(function (r) {
    var list = (r.data || {}).list || [];
    el.innerHTML =
      '<div class="pagehead"><h2>班级管理</h2><span class="sub">' + list.length + ' 个班级</span></div>' +
      table(['班号', '名称', '年级', '班主任', '教室', '~人数', '学期', '状态', ''], list, function (c) {
        return '<tr><td>' + esc(c.no) + '</td><td><b>' + esc(c.name) + '</b></td><td>' +
          esc(c.grade) + '</td><td>' + esc(c.head_teacher) + '</td><td>' + esc(c.room) +
          '</td><td class="num">' + c.student_count + '/' + c.capacity + '</td><td>' +
          esc(c.term) + '</td><td>' + statusTag(c.status) + '</td>' +
          '<td><button class="btn sm ghost" data-no="' + esc(c.no) + '">详情</button></td></tr>';
      });
    el.querySelectorAll('button[data-no]').forEach(function (b) {
      b.onclick = function () {
        GET('/api/classes/' + b.getAttribute('data-no')).then(function (rc) {
          var c = rc.data || {};
          modal('<h3>' + esc(c.name) + ' · ' + esc(c.head_teacher || '') + '</h3>' +
            '<h4>周课表</h4>' + weekGrid(c.schedule || []) +
            '<h4>学生名单（' + ((c.students || []).length) + '）</h4>' +
            table(['学号', '姓名', '性别', '监护人', '电话', '状态'], c.students || [], function (s) {
              return '<tr><td>' + esc(s.no) + '</td><td>' + esc(s.name) + '</td><td>' +
                esc(s.gender) + '</td><td>' + esc(s.guardian) + '</td><td>' +
                esc(s.guardian_phone) + '</td><td>' + statusTag(s.status) + '</td></tr>';
            }) +
            '<div class="toolbar right"><button class="btn ghost" onclick="closeModal()">关闭</button></div>', true);
        });
      };
    });
  });
};

/* ---------- 教师管理 ---------- */
PAGES.teacher = function (el) {
  return GET('/api/teachers').then(function (r) {
    var list = (r.data || {}).list || [];
    el.innerHTML =
      '<div class="pagehead"><h2>教师管理</h2><span class="sub">' + list.length + ' 名教师</span></div>' +
      table(['工号', '姓名', '性别', '学科', '职称', '校区', '电话', '状态'], list, function (t) {
        return '<tr><td>' + esc(t.no) + '</td><td><b>' + esc(t.name) + '</b></td><td>' +
          esc(t.gender) + '</td><td>' + esc(t.subject) + '</td><td>' + esc(t.title) +
          '</td><td>' + esc(t.school) + '</td><td>' + esc(t.phone) + '</td><td>' +
          statusTag(t.status) + '</td></tr>';
      });
  });
};

/* ---------- 课程排课 ---------- */
PAGES.course = function (el) {
  return GET('/api/courses').then(function (r) {
    var courses = (r.data || {}).list || [];
    return GET('/api/schedule?with_conflicts=1').then(function (rs) {
      var sch = (rs.data || {}).list || [];
      var conflicts = (rs.data || {}).conflicts || [];
      var selCls = [];
      sch.forEach(function (s) { if (selCls.indexOf(s.class_no) < 0) selCls.push(s.class_no); });
      el.innerHTML =
        '<div class="pagehead"><h2>课程排课</h2><span class="sub">' + courses.length +
        ' 门课程 · ' + sch.length + ' 节排课</span></div>' +
        (conflicts.length ? '<div class="card hot"><h3>⚠ 排课冲突 ' + conflicts.length +
          ' 处</h3>' + table(['类型', 'A', 'B'], conflicts, function (c) {
          return '<tr><td>' + esc(c.type) + '</td><td>' + esc(c.a.class_no + ' ' + c.a.course +
            ' 周' + c.a.weekday + '第' + c.a.slot + '节') + '</td><td>' +
            esc(c.b.class_no + ' ' + c.b.course + ' 周' + c.b.weekday + '第' + c.b.slot + '节') +
            '</td></tr>';
        }) + '</div>' : '') +
        '<div class="card"><h3>课程列表</h3>' +
        table(['代码', '课程名', '学科', '教师', '年级', '~周课时', '~学分', '状态'], courses, function (c) {
          return '<tr><td>' + esc(c.code) + '</td><td><b>' + esc(c.name) + '</b></td><td>' +
            esc(c.subject) + '</td><td>' + esc(c.teacher) + '</td><td>' + esc(c.grade) +
            '</td><td class="num">' + c.hours_per_week + '</td><td class="num">' + c.credit +
            '</td><td>' + statusTag(c.status) + '</td></tr>';
        }) + '</div>' +
        '<div class="card"><h3>周课表</h3><select id="cls-sel">' +
        selCls.map(function (c) { return '<option>' + esc(c) + '</option>'; }).join('') +
        '</select><div id="grid"></div></div>';
      function draw() {
        var c = document.getElementById('cls-sel').value;
        var items = sch.filter(function (s) { return s.class_no === c; });
        document.getElementById('grid').innerHTML = weekGrid(items);
      }
      document.getElementById('cls-sel').onchange = draw;
      draw();
    });
  });
};

/* ---------- 成绩管理 ---------- */
PAGES.score = function (el) {
  var term = TERM, exam = '期末', cls = '';
  function load() {
    var p1 = GET('/api/scores/analysis' + qs({term: term, exam: exam, class_no: cls}));
    var p2 = cls ? GET('/api/scores/rank' + qs({term: term, exam: exam, class_no: cls}))
                 : Promise.resolve(null);
    return Promise.all([p1, p2]).then(function (arr) {
      var ana = arr[0].data || {};
      var rank = arr[1] ? (arr[1].data || {}).list || [] : [];
      var ov = ana.overall || {};
      el.innerHTML =
        '<div class="pagehead"><h2>成绩管理</h2><span class="flex"></span>' +
        '<select id="s-term">' + termOptions(term) + '</select>' +
        '<select id="s-exam">' + examOptions(exam) + '</select>' +
        '<select id="s-cls"><option value="">全部班级</option>' +
        ['CLS001', 'CLS002', 'CLS003', 'CLS004', 'CLS005', 'CLS006', 'CLS007', 'CLS008']
          .map(function (c) { return '<option' + (c === cls ? ' selected' : '') + '>' + c + '</option>'; }).join('') +
        '</select>' +
        (perm('score.write') ? '<button class="btn" id="btn-in">+ 录入成绩</button>' : '') + '</div>' +
        '<div class="kpis">' +
        kpi(ov.count || 0, '成绩条数') + kpi(ov.avg || 0, '总体均分') +
        kpi(fmtPct(ov.pass_rate), '及格率') + kpi(fmtPct(ov.excellent_rate), '优秀率') +
        kpi(ov.gpa || 0, '平均GPA') + '</div>' +
        '<div class="grid2">' +
        '<div class="card"><h3>学科统计</h3>' +
        table(['课程', '~人数', '~均分', '~最高', '~最低', '~及格率', '~优秀率', '~标准差'],
          ana.list || [], function (a) {
          return '<tr><td><b>' + esc(a.course_name || a.course) + '</b></td><td class="num">' +
            a.count + '</td><td class="num">' + a.avg + '</td><td class="num">' + a.max +
            '</td><td class="num">' + a.min + '</td><td class="num">' + fmtPct(a.pass_rate) +
            '</td><td class="num">' + fmtPct(a.excellent_rate) + '</td><td class="num">' +
            a.stdev + '</td></tr>';
        }) + '</div>' +
        '<div class="card"><h3>' + (cls ? cls + ' ' : '') + '总分排名 TOP10</h3>' +
        table(['名次', '学号', '姓名', '~总分', '~均分', '等级'], rank.slice(0, 10), function (r) {
          return '<tr><td><b>' + r.rank + '</b></td><td>' + esc(r.student_no) + '</td><td>' +
            esc(r.name) + '</td><td class="num">' + r.score + '</td><td class="num">' +
            r.avg + '</td><td>' + level2(r.level) + '</td></tr>';
        }) + '</div></div>';
      ['s-term', 's-exam', 's-cls'].forEach(function (id) {
        document.getElementById(id).onchange = function () {
          term = document.getElementById('s-term').value;
          exam = document.getElementById('s-exam').value;
          cls = document.getElementById('s-cls').value;
          load();
        };
      });
      var btn = document.getElementById('btn-in');
      if (btn) btn.onclick = function () {
        modal('<h3>录入成绩</h3>' +
          field('学号', '<input id="g-no" placeholder="ST0001">') +
          field('课程代码', '<input id="g-course" value="KC001">') +
          field('考试', '<select id="g-exam">' + examOptions('期末') + '</select>') +
          field('成绩', '<input id="g-score" type="number" min="0" max="100">') +
          '<div class="toolbar right"><button class="btn ghost" onclick="closeModal()">取消</button>' +
          '<button class="btn" id="g-save">保存</button></div>');
        document.getElementById('g-save').onclick = function () {
          POST('/api/scores/save', {items: [{
            student_no: document.getElementById('g-no').value.trim(),
            course: document.getElementById('g-course').value.trim(),
            exam: document.getElementById('g-exam').value,
            score: Number(document.getElementById('g-score').value)
          }]}).then(function () { closeModal(); toast('已录入'); load(); })
            .catch(function (e) { toast(e.message, true); });
        };
      };
    });
  }
  return load();
};

/* ---------- 考勤管理 ---------- */
PAGES.attend = function (el) {
  function load(cls) {
    return GET('/api/attendance/stats' + qs({days: 30, class_no: cls})).then(function (r) {
      var d = r.data || {};
      var ov = d.overall || {};
      el.innerHTML =
        '<div class="pagehead"><h2>考勤管理</h2><span class="sub">近 30 天</span><span class="flex"></span>' +
        '<select id="a-cls"><option value="">全部班级</option>' +
        ['CLS001', 'CLS002', 'CLS003', 'CLS004', 'CLS005', 'CLS006', 'CLS007', 'CLS008']
          .map(function (c) { return '<option' + (c === cls ? ' selected' : '') + '>' + c + '</option>'; }).join('') +
        '</select>' +
        (perm('edu.write') ? '<button class="btn" id="btn-att">+ 登记考勤</button>' : '') + '</div>' +
        '<div class="kpis">' +
        kpi(ov.total || 0, '记录数') + kpi(fmtPct(ov.rate), '出勤率') +
        kpi(ov.late || 0, '迟到') + kpi(ov.sick || 0, '病假') +
        kpi(ov.personal || 0, '事假') + kpi(ov.absent_days || 0, '旷课') + '</div>' +
        '<div class="card"><h3>出勤率最低学生</h3>' +
        table(['学号', '姓名', '~出勤率', '~出勤', '~迟到', '~病假', '~事假', '~旷课'],
          (d.byStudent || []).slice(0, 15), function (s) {
          return '<tr><td>' + esc(s.student_no) + '</td><td><b>' + esc(s.name) + '</b></td>' +
            '<td class="num">' + fmtPct(s.rate) + '</td><td class="num">' + s.present +
            '</td><td class="num">' + s.late + '</td><td class="num">' + s.sick +
            '</td><td class="num">' + s.personal + '</td><td class="num">' + s.absent_days +
            '</td></tr>';
        }) + '</div>';
      document.getElementById('a-cls').onchange = function () {
        load(document.getElementById('a-cls').value);
      };
      var btn = document.getElementById('btn-att');
      if (btn) btn.onclick = function () {
        modal('<h3>登记考勤</h3>' +
          field('学号', '<input id="at-no" placeholder="ST0001">') +
          field('状态', '<select id="at-st"><option>出勤</option><option>迟到</option>' +
            '<option>病假</option><option>事假</option><option>旷课</option></select>') +
          '<div class="toolbar right"><button class="btn ghost" onclick="closeModal()">取消</button>' +
          '<button class="btn" id="at-save">保存</button></div>');
        document.getElementById('at-save').onclick = function () {
          POST('/api/attendance/save', {items: [{
            student_no: document.getElementById('at-no').value.trim(),
            status: document.getElementById('at-st').value
          }]}).then(function () { closeModal(); toast('已登记'); load(cls); })
            .catch(function (e) { toast(e.message, true); });
        };
      };
    });
  }
  return load('');
};

/* ---------- 缴费管理 ---------- */
PAGES.fee = function (el) {
  function load() {
    return Promise.all([
      GET('/api/fees/summary'),
      GET('/api/fees?term=2026-2027-1')
    ]).then(function (arr) {
      var s = arr[0].data || {};
      var list = (arr[1].data || {}).list || [];
      el.innerHTML =
        '<div class="pagehead"><h2>缴费管理</h2><span class="sub">学期 ' + esc(s.term || '') +
        '</span><span class="flex"></span>' +
        (perm('fee.write') ? '<button class="btn" id="btn-fee">+ 新建缴费单</button>' : '') +
        (perm('report.read') ? '<button class="btn ghost" id="btn-csv">导出名单</button>' : '') + '</div>' +
        '<div class="kpis">' +
        kpi(s.bills || 0, '缴费单') + kpi(fmtWan(s.total), '应收') +
        kpi(fmtWan(s.paid), '已收') + kpi(fmtWan(s.unpaid), '未收') +
        kpi(fmtPct(s.rate), '收缴率') + kpi(s.overdueCount || 0, '逾期单',
          (s.overdueCount || 0) > 0 ? 'hot' : '') + '</div>' +
        '<div class="card"><h3>缴费明细（' + list.length + '）</h3>' +
        table(['单号', '学号', '学生', '项目', '学期', '~应收', '~已缴', '状态', ''], list.slice(0, 80), function (f) {
          return '<tr><td>' + esc(f.no) + '</td><td>' + esc(f.student_no) + '</td><td>' +
            esc(f.student_name || '') + '</td><td>' + esc(f.item) + '</td><td>' + esc(f.term) +
            '</td><td class="num">' + fmtMoney(f.amount) + '</td><td class="num">' +
            fmtMoney(f.paid_amount) + '</td><td>' + statusTag(f.status) + '</td>' +
            (perm('fee.write') && f.status !== '已缴清'
              ? '<td><button class="btn sm" data-pay="' + esc(f.no) + '">核销</button></td>'
              : '<td></td>') + '</tr>';
        }) + '</div>';
      el.querySelectorAll('button[data-pay]').forEach(function (b) {
        b.onclick = function () {
          POST('/api/fees/pay', {no: b.getAttribute('data-pay'), amount: -1,
            pay_method: '银行转账'}).then(function (r2) {
            toast('核销成功：' + (r2.data || {}).status);
            load();
          }).catch(function (e) { toast(e.message, true); });
        };
      });
      var csv = document.getElementById('btn-csv');
      if (csv) csv.onclick = function () { dl('/api/reports/export', 'students.csv'); };
      var add = document.getElementById('btn-fee');
      if (add) add.onclick = function () {
        modal('<h3>新建缴费单</h3>' +
          field('学号', '<input id="fb-no" placeholder="ST0001">') +
          field('项目', '<input id="fb-item" value="学费">') +
          field('金额', '<input id="fb-amt" type="number" value="6200">') +
          field('折扣(%)', '<input id="fb-dis" type="number" value="0">') +
          '<div class="toolbar right"><button class="btn ghost" onclick="closeModal()">取消</button>' +
          '<button class="btn" id="fb-save">保存</button></div>');
        document.getElementById('fb-save').onclick = function () {
          POST('/api/fees/save', {
            student_no: document.getElementById('fb-no').value.trim(),
            item: document.getElementById('fb-item').value.trim(),
            amount: Number(document.getElementById('fb-amt').value),
            discount: Number(document.getElementById('fb-dis').value),
            term: TERM, due_date: '2026-09-15'
          }).then(function () { closeModal(); toast('已创建'); load(); })
            .catch(function (e) { toast(e.message, true); });
        };
      };
    });
  }
  return load();
};

/* ---------- 统计报表 ---------- */
PAGES.reports = function (el) {
  return GET('/api/reports/summary').then(function (r) {
    var d = r.data || {};
    var ac = d.academic || {};
    var att = d.attendance || {};
    var fee = d.fee || {};
    var t = d.teaching || {};
    el.innerHTML =
      '<div class="pagehead"><h2>统计报表</h2><span class="sub">学期 ' + esc(d.term || '') +
      '</span><span class="flex"></span>' +
      '<button class="btn ghost" id="btn-csv">导出学生 CSV</button></div>' +
      '<div class="grid2">' +
      '<div class="card"><h3>教学规模</h3><div class="toolbar">' +
      kpi(t.students || 0, '学生') + kpi(t.teachers || 0, '教师') +
      kpi(t.classes || 0, '班级') + kpi(t.courses || 0, '课程') + '</div></div>' +
      '<div class="card"><h3>学业概况</h3><div class="toolbar">' +
      kpi(ac.avg || 0, '均分') + kpi(fmtPct(ac.pass_rate), '及格率') +
      kpi(fmtPct(ac.excellent_rate), '优秀率') + kpi(ac.gpa || 0, 'GPA') + '</div></div>' +
      '</div>' +
      '<div class="grid2">' +
      '<div class="card"><h3>考勤概况（近30天）</h3><div class="toolbar">' +
      kpi(fmtPct(att.rate), '出勤率') + kpi(att.late || 0, '迟到') +
      kpi(att.sick || 0, '病假') + kpi(att.absent_days || 0, '旷课') + '</div></div>' +
      '<div class="card"><h3>收费概况</h3><div class="toolbar">' +
      kpi(fmtWan(fee.total), '应收') + kpi(fmtWan(fee.paid), '已收') +
      kpi(fmtWan(fee.unpaid), '未收') + kpi(fmtPct(fee.rate), '收缴率') + '</div></div>' +
      '</div>';
    var csv = document.getElementById('btn-csv');
    if (csv) csv.onclick = function () { dl('/api/reports/export', 'students.csv'); };
  });
};

/* ---------- 预警中心 ---------- */
PAGES.risk = function (el) {
  function load() {
    return GET('/api/risks?status=待处理').then(function (r) {
      var list = (r.data || {}).list || [];
      el.innerHTML =
        '<div class="pagehead"><h2>预警中心</h2><span class="sub">' + list.length +
        ' 条待处理</span><span class="flex"></span>' +
        (perm('risk.read') ? '<button class="btn" id="btn-scan">执行扫描</button>' : '') + '</div>' +
        table(['ID', '校区', '级别', '标题', '详情', '时间', ''], list, function (x) {
          return '<tr><td>' + x.id + '</td><td>' + esc(x.school) + '</td><td>' +
            levelTag(x.level) + '</td><td><b>' + esc(x.title) + '</b></td><td class="sub-cell">' +
            esc(x.detail) + '</td><td>' + fmtDate(x.created_at) + '</td>' +
            '<td><button class="btn sm" data-id="' + x.id + '">处理</button></td></tr>';
        });
      el.querySelectorAll('button[data-id]').forEach(function (b) {
        b.onclick = function () {
          POST('/api/risks/close', {id: Number(b.getAttribute('data-id'))}).then(function () {
            toast('已处理'); load();
          }).catch(function (e) { toast(e.message, true); });
        };
      });
      var scan = document.getElementById('btn-scan');
      if (scan) scan.onclick = function () {
        scan.disabled = true;
        POST('/api/risks/scan', {}).then(function (r2) {
          toast('新增 ' + (r2.data.count || 0) + ' 条'); load();
        }).catch(function (e) { toast(e.message, true); scan.disabled = false; });
      };
    });
  }
  return load();
};

/* ---------- 政策公告 ---------- */
PAGES.policy = function (el) {
  return Promise.all([GET('/api/policies'), GET('/api/notices')]).then(function (arr) {
    var pol = (arr[0].data || {}).list || [];
    var not = arr[1].data || [];
    el.innerHTML =
      '<div class="grid2">' +
      '<div class="card"><h3>政策法规</h3>' +
      table(['标题', '分类', '文号', '生效', '状态'], pol, function (p) {
        return '<tr><td><b>' + esc(p.title) + '</b><div class="sub-cell">' + esc(p.summary) +
          '</div></td><td>' + esc(p.category) + '</td><td>' + esc(p.doc_no) + '</td><td>' +
          fmtDate(p.effect_date) + '</td><td>' + statusTag(p.status) + '</td></tr>';
      }) + '</div>' +
      '<div class="card"><h3>校园公告</h3>' + not.map(function (n) {
        return '<div class="rowitem' + (n.top ? ' hot' : '') + '"><b>' +
          (n.top ? '[置顶] ' : '') + esc(n.title) + '</b><p>' + esc(n.body) +
          '</p><i>' + esc(n.author) + ' · ' + fmtDate(n.created_at) + '</i></div>';
      }).join('') + '</div></div>';
  });
};

/* ---------- 系统管理 ---------- */
PAGES.system = function (el) {
  return Promise.all([
    GET('/api/users'), GET('/api/roles'), GET('/api/api-keys'), GET('/api/sync/version')
  ]).then(function (arr) {
    var users = (arr[0].data || {}).list || [];
    var roles = arr[1].data || [];
    var keys = (arr[2].data || {}).list || [];
    var sync = arr[3].data || {};
    el.innerHTML =
      '<div class="grid2">' +
      '<div class="card"><h3>用户与角色</h3>' +
      table(['账号', '姓名', '角色', '部门', '状态'], users, function (u) {
        return '<tr><td>' + esc(u.username) + '</td><td><b>' + esc(u.name) + '</b></td><td>' +
          esc(u.role) + '</td><td>' + esc(u.dept) + '</td><td>' + statusTag(u.status) + '</td></tr>';
      }) + '</div>' +
      '<div class="card"><h3>权限矩阵</h3>' +
      table(['角色', '权限'], roles, function (ro) {
        return '<tr><td><b>' + esc(ro.label) + '</b></td><td>' + ro.perms.map(function (p) {
          return tag(p, p === '*' ? 'err' : 'pri');
        }).join(' ') + '</td></tr>';
      }) + '</div>' +
      '</div>' +
      '<div class="grid2">' +
      '<div class="card"><h3>接口密钥</h3>' +
      table(['名称', '前缀', '权限域', '创建', '状态'], keys, function (k) {
        return '<tr><td>' + esc(k.name) + '</td><td>' + esc(k.prefix) + '</td><td>' +
          esc(k.scope) + '</td><td>' + fmtDate(k.created_at) + '</td><td>' +
          statusTag(k.status) + '</td></tr>';
      }) +
      (perm('system.read') ? '<div class="toolbar right"><button class="btn" id="btn-key">+ 生成密钥</button></div>' : '') +
      '</div>' +
      '<div class="card"><h3>增量同步版本</h3>' +
      table(['实体', '~版本'], Object.keys(sync).map(function (k) {
        return {k: k, v: sync[k]};
      }), function (x) {
        return '<tr><td>' + esc(x.k) + '</td><td class="num">' + x.v + '</td></tr>';
      }) +
      '<div class="toolbar">对接文档：<a href="' + esc(PREFIX) +
      '/api/apidoc" target="_blank">/api/apidoc</a></div></div>' +
      '</div>';
    var bk = document.getElementById('btn-key');
    if (bk) bk.onclick = function () {
      var nm = '对接密钥' + (keys.length + 1);
      POST('/api/api-keys/create', {name: nm, scope: 'read'}).then(function (r) {
        modal('<h3>密钥已生成（仅展示一次）</h3><pre style="white-space:pre-wrap">' +
          esc((r.data || {}).key || '') + '</pre>' +
          '<div class="toolbar right"><button class="btn" onclick="closeModal()">我已保存</button></div>');
      }).catch(function (e) { toast(e.message, true); });
    };
  });
};
