/* LLM 学习助手前端逻辑（零依赖） */
"use strict";
const $ = (id) => document.getElementById(id);
const API = "";

/* ---------------- 极简 Markdown 渲染 ---------------- */
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function mdLite(md) {
  if (!md) return "";
  const parts = String(md).split(/```[ \t]*([\w+-]*)[ \t]*\n?/); // 文本与代码交替
  let out = "";
  for (let i = 0; i < parts.length; i++) {
    const seg = parts[i];
    if (i % 2 === 1) { // seg 是语言名，下一块是代码
      const code = (parts[i + 1] || "").replace(/\n$/, "");
      out += `<pre><code>${escapeHtml(code)}</code></pre>`;
      i++;
    } else {
      out += mdInline(seg);
    }
  }
  return out;
}
function mdInline(text) {
  const lines = escapeHtml(text).split("\n");
  let html = "", inCode = false, inList = false;
  for (const raw of lines) {
    let line = raw;
    line = line.replace(/`([^`]+)`/g, "<code>$1</code>")
               .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
    if (/^#{1,4}\s/.test(line)) {
      const lv = line.match(/^#+/)[0].length;
      closeList();
      html += `<h${lv + 1}>${line.replace(/^#+\s*/, "")}</h${lv + 1}>`;
      continue;
    }
    if (/^\s*[-*]\s/.test(line)) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${line.replace(/^\s*[-*]\s/, "")}</li>`;
      continue;
    }
    if (/^\s*\d+\.\s/.test(line)) {
      if (!inList) { html += "<ol>"; inList = true; }
      html += `<li>${line.replace(/^\s*\d+\.\s/, "")}</li>`;
      continue;
    }
    closeList();
    if (line.trim() === "") { html += "<p style='margin:4px 0'></p>"; }
    else { html += `<p style='margin:6px 0'>${line}</p>`; }
  }
  function closeList() { if (inList) { html += "</ul>"; inList = false; } }
  return html;
}

/* ---------------- 通用请求 ---------------- */
async function api(path, opts) {
  const r = await fetch(API + path, opts);
  if (!r.ok) {
    let msg = r.status + " " + r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return r.json();
}
const post = (path, body) => api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});

/* ---------------- 页签 ---------------- */
for (const btn of document.querySelectorAll("#tabs button")) {
  btn.onclick = () => {
    document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b === btn));
    document.querySelectorAll(".panel").forEach(p => p.classList.toggle("on", p.id === "tab-" + btn.dataset.tab));
    if (btn.dataset.tab === "cfg") loadCfg();
    if (btn.dataset.tab === "dev") loadProjects();
  };
}

/* ---------------- 健康状态 ---------------- */
async function loadHealth() {
  try {
    const h = await api("/api/health");
    const okCount = h.llm.filter(p => p.ok).length;
    const el = $("health");
    el.textContent = `模型 ${okCount}/${h.llm.length} · 课程 ${h.lessons} 讲 · 题库 ${h.problems} 题 · 知识块 ${h.kb.chunks}`;
    el.className = "health " + (okCount ? "ok" : "bad");
  } catch (e) { $("health").textContent = "后端未连接"; $("health").className = "health bad"; }
}

/* ---------------- 对话 ---------------- */
function addMsg(role, html) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.innerHTML = role === "user" ? escapeHtml(html) : `<div class="md">${mdLite(html)}</div>`;
  $("chat-log").appendChild(div);
  $("chat-log").scrollTop = 1e9;
  return div;
}
async function sendChat() {
  const text = $("chat-input").value.trim();
  if (!text) return;
  $("chat-input").value = "";
  addMsg("user", text);
  const bubble = addMsg("bot", "…思考中");
  try {
    const r = await post("/api/chat", {message: text, use_web: $("chat-web").checked});
    bubble.innerHTML = `<div class="md">${mdLite(r.reply)}${r.web_used ? '<p class="muted">🌐 已结合网络检索</p>' : ""}</div>`;
  } catch (e) { bubble.innerHTML = `<div class="md grade-bad">出错了：${escapeHtml(e.message)}</div>`; }
  $("chat-log").scrollTop = 1e9;
}
$("chat-send").onclick = sendChat;
$("chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
});
$("chat-clear").onclick = () => { $("chat-log").innerHTML = ""; };

/* ---------------- 学习路径 ---------------- */
let lessonsCache = [];
async function loadLessons() {
  lessonsCache = await api("/api/lessons");
  $("lesson-count").textContent = `(${lessonsCache.length} 讲)`;
  renderLessonList();
  const prog = await api("/api/progress/default");
  renderPath(prog);
}
function renderLessonList(selId) {
  const ul = $("lesson-list"); ul.innerHTML = "";
  const byTrack = {};
  for (const l of lessonsCache) (byTrack[l.track] = byTrack[l.track] || []).push(l);
  for (const [track, ls] of Object.entries(byTrack)) {
    const head = document.createElement("li");
    head.className = "muted"; head.style.cursor = "default";
    head.innerHTML = `<b>${track}</b>`;
    ul.appendChild(head);
    for (const l of ls) {
      const li = document.createElement("li");
      if (l.id === selId) li.className = "on";
      li.innerHTML = `<span>${escapeHtml(l.title)}</span><span class="tag">${l.level}·${l.est_minutes}min</span>`;
      li.onclick = () => openLesson(l.id);
      ul.appendChild(li);
    }
  }
}
async function renderPath(prog) {
  const ol = $("path-steps"); ol.innerHTML = "";
  const p = prog.path || {};
  if (!p.steps || !p.steps.length) { ol.innerHTML = "<li class='muted'>还没有计划——先在上方生成学习计划</li>"; return; }
  ol.innerHTML = `<li class="muted" style="cursor:default">目标：${escapeHtml(p.goal || "")}</li>`;
  for (const s of p.steps) {
    const li = document.createElement("li");
    li.className = s.status === "done" ? "done" : (s.status === "blocked" ? "blocked" : "");
    li.innerHTML = `<span>${escapeHtml(s.title || s.lesson_id)}</span><span class="tag">${escapeHtml(s.focus || "")}</span>`;
    li.onclick = () => openLesson(s.lesson_id);
    ol.appendChild(li);
  }
  $("path-project").textContent = p.project ? "🎯 毕业项目：" + p.project : "";
}
$("goal-plan").onclick = async () => {
  const goal = $("goal-input").value.trim();
  if (!goal) return alert("先写一句学习目标");
  $("goal-plan").disabled = true; $("goal-plan").textContent = "规划中…";
  try {
    await post("/api/learn/path", {goal});
    await renderPath(await api("/api/progress/default"));
  } catch (e) { alert("规划失败：" + e.message); }
  $("goal-plan").disabled = false; $("goal-plan").textContent = "生成学习计划";
};
let currentLesson = null;
async function openLesson(lessonId) {
  renderLessonList(lessonId);
  $("teach-empty").classList.add("hidden");
  $("teach-view").classList.remove("hidden");
  $("teach-title").textContent = lessonsCache.find(l => l.id === lessonId)?.title || lessonId;
  $("teach-body").innerHTML = "<p class='muted'>导师备课中…</p>";
  $("grade-result").innerHTML = ""; $("ex-input").value = "";
  try {
    const r = await post("/api/learn/teach", {lesson_id: lessonId});
    currentLesson = r.lesson;
    const ex = (r.lesson.exercises || [])[0];
    $("teach-body").innerHTML = mdLite(r.teaching);
    $("ex-prompt").innerHTML = ex ? mdLite(ex.prompt) : "<p class='muted'>本讲练习见讲义</p>";
  } catch (e) {
    $("teach-body").innerHTML = mdLite("加载失败：" + e.message);
  }
}
$("ex-submit").onclick = async () => {
  if (!currentLesson) return;
  const content = $("ex-input").value.trim();
  if (!content) return alert("先写点什么再提交");
  $("ex-submit").disabled = true;
  $("grade-result").innerHTML = "<p class='muted'>批改中…</p>";
  try {
    const g = await post("/api/learn/submit", {
      lesson_id: currentLesson.id,
      exercise_id: (currentLesson.exercises[0] || {}).id || "",
      code: content,
    });
    const cls = g.passed ? "grade-ok" : "grade-bad";
    $("grade-result").innerHTML = mdLite(
      `**得分 ${g.score} ${g.passed ? "✅ 通过" : "❌ 未通过"}**\n\n` +
      (g.strengths || []).map(s => "- 💪 " + s).join("\n") + "\n" +
      (g.problems || []).map(p => `- ⚠️ [${p.level}] ${p.text}`).join("\n") + "\n" +
      (g.suggestions || []).map(s => "- 👉 " + s).join("\n") + "\n\n" +
      (g.coach || ""));
    $("grade-result").querySelectorAll("b").forEach(b => b.classList.add(cls));
  } catch (e) { $("grade-result").innerHTML = mdLite("批改失败：" + e.message); }
  $("ex-submit").disabled = false;
};

/* ---------------- LeetCode ---------------- */
let problemsCache = [], currentProblem = null, hintLevel = 0;
async function loadProblems() {
  problemsCache = await api("/api/leetcode/problems");
  const ul = $("lc-list"); ul.innerHTML = "";
  for (const p of problemsCache) {
    const li = document.createElement("li");
    li.innerHTML = `<span>${p.solved ? "✅ " : ""}${escapeHtml(p.title)}</span>
      <span class="tag">${p.difficulty}</span>`;
    li.onclick = () => openProblem(p.id);
    ul.appendChild(li);
  }
}
async function openProblem(pid) {
  const p = problemsCache.find(x => x.id === pid);
  document.querySelectorAll("#lc-list li").forEach(() => {});
  currentProblem = p; hintLevel = 0; $("lc-hint-level").textContent = "";
  $("lc-view").classList.remove("hidden"); $("lc-empty").classList.add("hidden");
  const d = await api("/api/leetcode/problems/" + pid);
  $("lc-title").textContent = d.title;
  const diff = $("lc-diff"); diff.textContent = d.difficulty + (p && p.solved ? " ·已解出" : "");
  diff.className = "badge " + d.difficulty;
  $("lc-desc").innerHTML = mdLite(d.description);
  $("lc-code").value = d.starter || "";
  $("lc-results").innerHTML = "";
}
function renderJudge(j) {
  let out = `**判题：${j.verdict}**（通过 ${j.passed}/${j.total}，${j.duration_ms}ms）\n`;
  if (j.violations) out += j.violations.map(v => "- 🚫 " + v).join("\n") + "\n";
  for (const r of (j.results || [])) {
    out += r.pass ? `- 用例${r.i + 1} ✅\n`
      : `- 用例${r.i + 1} ❌ ${r.error || ""} 输入→期望 \`${r.expected}\` 实际 \`${r.got ?? r.error}\`\n`;
  }
  if (j.stderr_tail) out += `\n\`\`\`\n${j.stderr_tail}\n\`\`\`\n`;
  return out;
}
$("lc-run").onclick = async () => {
  if (!currentProblem) return;
  $("lc-run").disabled = true;
  $("lc-results").innerHTML = mdLite("判题中…");
  try {
    const j = await post("/api/leetcode/run", {problem_id: currentProblem.id, code: $("lc-code").value});
    $("lc-results").innerHTML = mdLite(renderJudge(j));
    if (j.solved) { currentProblem.solved = true; loadProblems(); }
  } catch (e) { $("lc-results").innerHTML = mdLite("评测失败：" + e.message); }
  $("lc-run").disabled = false;
};
$("lc-hint").onclick = async () => {
  if (!currentProblem) return;
  hintLevel += 1;
  try {
    const h = await post("/api/leetcode/hint", {problem_id: currentProblem.id, level: hintLevel, code: $("lc-code").value});
    $("lc-results").innerHTML = mdLite(`**💡 提示（第 ${h.level} 级${h.has_more ? "，还有更深的" : "，已是最后一层"}）**\n\n${h.text}`);
    $("lc-hint-level").textContent = h.level;
  } catch (e) { $("lc-results").innerHTML = mdLite("提示失败：" + e.message); }
};
$("lc-review").onclick = async () => {
  if (!currentProblem) return;
  $("lc-results").innerHTML = mdLite("AI 点评中…");
  try {
    const r = await post("/api/leetcode/review", {problem_id: currentProblem.id, code: $("lc-code").value});
    const c = r.coach || {};
    $("lc-results").innerHTML = mdLite(renderJudge(r.judge) +
      `\n**AI 点评**${c.score >= 0 ? "（" + c.score + " 分）" : ""}\n` +
      `- 时间复杂度：${c.complexity?.time || "—"}\n- 空间复杂度：${c.complexity?.space || "—"}\n` +
      (c.issues || []).map(i => "- ⚠️ " + i).join("\n") +
      (c.edge_cases || []).map(i => "- 🔸 未考虑边界：" + i).join("\n") +
      (c.style_tips || []).map(i => "- ✍️ " + i).join("\n") +
      `\n\n${c.summary || ""}`);
  } catch (e) { $("lc-results").innerHTML = mdLite("点评失败：" + e.message); }
};
$("lc-explain").onclick = async () => {
  if (!currentProblem) return;
  $("lc-results").innerHTML = mdLite("精讲生成中…");
  try {
    const r = await post("/api/leetcode/explain", {problem_id: currentProblem.id, code: $("lc-code").value});
    $("lc-results").innerHTML = mdLite(r.text);
  } catch (e) { $("lc-results").innerHTML = mdLite("精讲失败：" + e.message); }
};
$("lc-next").onclick = async () => {
  const todo = problemsCache.find(p => !p.solved);
  if (todo) openProblem(todo.id);
};

/* ---------------- 开发工作流（SSE） ---------------- */
let devAbort = null;
function devLog(ev) {
  const log = $("dev-log");
  const div = document.createElement("div");
  div.className = "ev";
  const t = ev.ts || "";
  if (ev.type === "phase") {
    div.innerHTML = `<span class="muted">[${t}]</span> <span class="ph ${ev.phase}">${ev.phase}</span> ${ev.status}${ev.note ? " — " + escapeHtml(ev.note) : ""}${ev.verdict ? " 裁决: " + ev.verdict : ""}`;
    if (ev.issues && ev.issues.length) div.innerHTML += ev.issues.map(i => `<div class="muted">　└ ⚠️ ${escapeHtml(i)}</div>`).join("");
  } else if (ev.type === "file") {
    div.innerHTML = `<span class="muted">[${t}]</span> 📄 生成文件 <b>${escapeHtml(ev.path)}</b>（${ev.bytes} 字节）`;
  } else if (ev.type === "issue") {
    div.innerHTML = `<span class="muted">[${t}]</span> ⚠️ [${ev.severity}] ${escapeHtml(ev.file)} ${escapeHtml(ev.text)}`;
  } else if (ev.type === "tests") {
    div.innerHTML = `<span class="muted">[${t}]</span> 🧪 ${ev.ok ? "✅ 测试通过" : "❌ 测试失败"} — ${escapeHtml(ev.summary)}${ev.output_tail ? `<pre style="margin:4px 0 0 20px">${escapeHtml(ev.output_tail)}</pre>` : ""}`;
  } else if (ev.type === "log") {
    div.innerHTML = `<span class="muted">[${t}]</span> ${escapeHtml(ev.text)}`;
  } else if (ev.type === "retro") {
    const r = ev.retro || {};
    div.innerHTML = `<span class="muted">[${t}]</span> 📋 复盘：${escapeHtml(r.summary || "")}<div class="muted">　知识点：${escapeHtml((r.knowledge_points || []).join("、"))}</div><div class="muted">　下一步：${escapeHtml((r.next_steps || []).join("；"))}</div>`;
  } else if (ev.type === "done") {
    div.innerHTML = `<span class="muted">[${t}]</span> ${ev.ok ? "🎉 工作流达标完成" : "⚠️ 工作流收尾（仍有遗留问题）"} — 项目 <b>${escapeHtml(ev.project)}</b>，共 ${ev.report.cycles} 轮循环`;
    showReport(ev.report);
    loadProjects();
  } else if (ev.type === "error") {
    div.innerHTML = `<span class="muted">[${t}]</span> ❌ ${escapeHtml(ev.text)}`;
  }
  log.appendChild(div);
  log.scrollTop = 1e9;
}
function showReport(report) {
  $("dev-report").innerHTML = mdLite(
    `## 工作流报告\n- 结果：${report.ok ? "✅ 达标" : "⚠️ 部分 完成（遗留问题见上）"}\n` +
    `- 循环：${report.cycles} 大轮 / ${report.plan_cycles} 次计划 / ${report.dev_cycles} 次回炉\n` +
    `- 产物：workspace/${report.project}/ → ${report.files.join("、")}\n` +
    (report.open_feedback?.length ? `- 遗留：${report.open_feedback.join("；")}` : ""));
}
$("dev-run").onclick = async () => {
  const goal = $("dev-goal").value.trim();
  if (!goal) return alert("先写开发目标");
  $("dev-log").innerHTML = ""; $("dev-report").innerHTML = "";
  $("dev-run").disabled = true; $("dev-stop").classList.remove("hidden");
  devAbort = new AbortController();
  try {
    const resp = await fetch(API + "/api/dev/run", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({goal, project: $("dev-project").value.trim()}),
      signal: devAbort.signal,
    });
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream: true});
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, i); buf = buf.slice(i + 2);
        if (frame.startsWith("data: ")) {
          try { devLog(JSON.parse(frame.slice(6))); } catch (e) {}
        }
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") devLog({type: "error", text: e.message});
  }
  $("dev-run").disabled = false; $("dev-stop").classList.add("hidden");
};
$("dev-stop").onclick = () => devAbort && devAbort.abort();

async function loadProjects() {
  const list = await api("/api/dev/projects");
  const ul = $("dev-projects"); ul.innerHTML = "";
  for (const p of list.slice().reverse()) {
    const li = document.createElement("li");
    const ok = p.report.ok;
    li.innerHTML = `<span>${escapeHtml(p.project)}</span>
      <span class="tag">${ok === true ? "✅" : ok === false ? "⚠️" : ""} ${p.files.length} 文件</span>`;
    li.onclick = () => {
      $("dev-file").textContent = p.files.length
        ? p.files.map(f => "• " + f).join("\n") + "\n\n（README/代码可通过 report 与 workspace 目录查看）"
        : "（无文件）";
      $("dev-file-title").textContent = "产物文件 — " + p.project;
    };
    ul.appendChild(li);
  }
  if (!list.length) ul.innerHTML = "<li class='muted'>还没有项目，跑一次工作流试试</li>";
}
$("dev-refresh").onclick = loadProjects;

/* ---------------- 设置 ---------------- */
async function loadCfg() {
  try {
    const h = await api("/api/health");
    const tbl = $("cfg-providers");
    tbl.innerHTML = "<tr><th>状态</th><th>名称</th><th>类型</th><th>模型</th><th>详情</th></tr>" +
      h.llm.map(p => `<tr><td><span class="dot ${p.ok ? "ok" : "bad"}"></span></td>
        <td>${escapeHtml(p.name)}</td><td>${p.kind}</td><td>${escapeHtml(p.model)}</td>
        <td class="muted">${escapeHtml(p.detail)}</td></tr>`).join("");
    $("kb-stats").textContent = `知识块 ${h.kb.chunks} · 来源 ${h.kb.sources} · 向量 ${h.kb.embeddings ? "已建(" + h.kb.embed_model + ")" : "未建(BM25 模式)"}`;
    const prog = await api("/api/progress/default");
    const sm = prog.skill_matrix || {};
    $("profile").innerHTML = mdLite(
      `已完成课程 ${Object.keys(prog.lessons).length} 讲；力扣 ${prog.leetcode.solved.length} 题。\n` +
      Object.entries(sm).map(([t, v]) => `- **${t}**：L${v.level}（通过 ${v.passed} 讲）`).join("\n") +
      (prog.wrong_book?.length ? `\n\n错题本最近 ${Math.min(prog.wrong_book.length, 5)} 条：\n` + prog.wrong_book.slice(-5).map(w => `- ${w.lesson}：${w.text}`).join("\n") : ""));
  } catch (e) {}
}
$("cfg-test").onclick = async () => {
  $("cfg-test").disabled = true; $("cfg-test-result").textContent = "逐个测试中…（约需数秒）";
  try {
    const r = await post("/api/config/test-llm", {});
    $("cfg-test-result").innerHTML = r.results.map(x =>
      `${x.ok ? "✅" : "❌"} <b>${x.name}</b> — ${escapeHtml(x.detail)}`).join("<br>");
  } catch (e) { $("cfg-test-result").textContent = e.message; }
  $("cfg-test").disabled = false;
};
$("kb-reindex").onclick = async () => {
  $("kb-reindex").disabled = true; $("kb-stats").textContent = "重建中…";
  try { const r = await post("/api/kb/reindex", {}); await loadHealth(); await loadCfg(); }
  catch (e) { $("kb-stats").textContent = "失败：" + e.message; }
  $("kb-reindex").disabled = false;
};

/* ---------------- 启动 ---------------- */
loadHealth();
loadLessons();
loadProblems();
