---
id: frontend-basics
title: 前端基础：聊天界面与流式渲染
level: beginner
track: fullstack
prereq: [fastapi-backend]
est_minutes: 60
tags: [html, javascript, fetch, sse, 聊天界面]
---

# 前端基础（面向 LLM 应用）

## 三件套够用了
不装框架，HTML/CSS/JS 写出能用的聊天界面——**先懂原理，再上 Vue/React 事半功倍**。

## 页面骨架
```html
<div id="app">
  <div id="chat"></div>
  <div class="bar">
    <input id="msg" placeholder="输入消息…" />
    <button id="send">发送</button>
  </div>
</div>
```

## 发消息与渲染 Markdown 风格文本
```javascript
function escapeHtml(s) {           // 安全第一：任何后端内容都要转义
  return s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",
    '"':"&quot;","'":"&#39;"}[c]));
}
function mdLite(md) {              // 极简渲染：代码块 + 行内代码 + 粗体
  const parts = md.split(/```(?:\w*)\n?/);        // 偶数=文本，奇数=代码
  return parts.map((p, i) => i % 2
    ? `<pre><code>${escapeHtml(p.trim())}</code></pre>`
    : escapeHtml(p).replace(/`([^`]+)`/g, "<code>$1</code>")
                   .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
  ).join("");
}
```
**永远不要 innerHTML 未转义的后端内容** —— XSS 就从这里来。

## 消费流式接口（fetch + ReadableStream）
```javascript
async function ask(text) {
  const resp = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({message: text}),
  });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    buf += decoder.decode(value, {stream: true});
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {     // SSE 帧以空行分隔
      const frame = buf.slice(0, idx); buf = buf.slice(idx + 2);
      if (!frame.startsWith("data: ")) continue;
      const payload = frame.slice(6);
      if (payload === "[DONE]") return;
      appendDelta(JSON.parse(payload).delta);      // 逐块追加到气泡
    }
  }
}
```

## 体验细节（面试加分项）
1. 打字机效果：流式 delta 直接 append，天然打字机；
2. 请求中禁用发送按钮 + 显示 loading；
3. 出错在气泡内红字提示，别 alert；
4. Enter 发送 / Shift+Enter 换行。

## 常见坑
1. `decoder.decode(value)` 忘加 `{stream: true}` → 中文多字节被截断成乱码；
2. 粘包：SSE 帧可能一次到达多个，必须按 `\n\n` 切帧（见 buf 处理）；
3. CORS：前后端分离时后端要加 `CORSMiddleware`。

## 自测
1. 为什么必须按空行切 SSE 帧？
2. escapeHtml 防的是什么攻击？

## 练习
```yaml
- id: fe-1
  type: code
  prompt: |
    写一个 askStream(url, body, onDelta, onDone) 工具函数：封装 fetch 流式读取，
    正确处理 SSE 帧切分与 UTF-8 流式解码，onDelta(text) 逐块回调。
  starter: |
    async function askStream(url, body, onDelta, onDone) {
      // TODO: 参考讲义 buf + indexOf('\\n\\n') 模式
    }
  hints:
    - "read 循环里 buf += decoder.decode(value, {stream: true})"
    - "最后剩余 buf 里可能还有完整帧，循环结束后再处理一次"
- id: fe-2
  type: quiz
  prompt: |
    直接把 LLM 返回的 Markdown 用 innerHTML 渲染，攻击者可通过什么注入？
    至少举一个payload例子。
  hints:
    - "<img src=x onerror=alert(1)> —— XSS。模型可能被提示注入诱导输出恶意 HTML，所以必须转义"
```
