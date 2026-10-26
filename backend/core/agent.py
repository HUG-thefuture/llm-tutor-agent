"""开发工作流 Agent：思考(THINK) → 计划(PLAN) → 审查(REVIEW) → 开发(DEVELOP) → 测试(TEST)。

循环规则（与需求一一对应）：
- 审查不过 → 带着意见重做计划；重做次数用尽 → 回到最初“思考”阶段重新循环
- 开发产物静态检查不过 / 测试不过 / 代码审查发现逻辑错误或内存泄漏 → 带着问题清单回炉（回到思考）
- 整个大循环有硬上限，防无限循环；结束后落盘完整过程日志到 workspace/<project>/.agent_run.json
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Optional

from .config import DevAgentCfg
from .llm import LLMClient, LLMError
from .staticcheck import deep_scan

SYSTEM = (
    "你是一位资深全栈工程师与架构师，擅长 Python/JavaScript/Web 开发。"
    "回答务必使用中文，代码注释也用中文。输出严格遵循要求的 JSON 结构，不要输出多余文字。"
)

PLAN_SCHEMA = {
    "summary": "一句话概述方案",
    "files": [{"path": "相对路径", "purpose": "该文件职责"}],
    "steps": ["实现步骤1", "…"],
    "tests": ["要写的测试文件（tests/test_xxx.py），无则空数组"],
    "acceptance": ["验收标准1", "…"],
    "risks": ["风险与规避"],
}


def _safe_join(root: Path, relpath: str) -> Optional[Path]:
    relpath = (relpath or "").replace("\\", "/").lstrip("/")
    if ".." in relpath.split("/") or not relpath or re.match(r"^[a-zA-Z]:", relpath):
        return None
    p = (root / relpath).resolve()
    return p if str(p).startswith(str(root.resolve())) else None


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", text)[:32].strip("-") or "project"
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{s}"


def _files_block(plan: dict, files: dict[str, str], cap_per_file: int = 5000, cap_total: int = 22000) -> str:
    parts, total = [], 0
    for path in plan.get("files", []):
        p = path["path"] if isinstance(path, dict) else str(path)
        content = files.get(p, "")
        snippet = content[:cap_per_file]
        parts.append(f"### {p}\n```{'py' if p.endswith('.py') else ''}\n{snippet}\n```")
        total += len(snippet)
        if total > cap_total:
            parts.append("（其余文件已截断）")
            break
    return "\n".join(parts) or "（尚无代码）"


@dataclass
class DevAgent:
    llm: LLMClient
    workspace_root: Path
    cfg: DevAgentCfg
    node_available: bool = False

    async def run(self, goal: str, project: Optional[str] = None) -> AsyncIterator[dict]:
        events: list[dict] = []

        async def emit(ev: dict) -> dict:
            ev["ts"] = time.strftime("%H:%M:%S")
            events.append(ev)
            return ev

        slug = _slug(project or goal)
        root = self.workspace_root / slug
        root.mkdir(parents=True, exist_ok=True)

        feedback: list[str] = []          # 沉淀所有被驳回的问题，驱动每一轮回炉
        plan: dict = {}
        files: dict[str, str] = {}
        plan_cycles = dev_cycles = total_cycles = 0
        escalated = False                 # 回炉后自动升级到更强模型（模型协同）
        final_ok = False
        report: dict = {}

        def mo() -> Optional[str]:        # 当前轮次应使用的模型覆盖
            return (self.cfg.escalate_model or None) if escalated else None

        def escalate():
            nonlocal escalated
            if not escalated and self.cfg.escalate_model:
                escalated = True
                return True
            return False

        try:
            while True:
                total_cycles += 1
                if total_cycles > self.cfg.max_total_cycles:
                    yield await emit({"type": "log", "phase": "GLOBAL",
                                      "text": f"已达最大循环次数 {self.cfg.max_total_cycles}，按当前成果收尾"})
                    break

                # ============ 1. 思考 ============
                yield await emit({"type": "phase", "phase": "THINK", "status": "start",
                                  "cycle": total_cycles})
                think = await self.llm.chat(
                    [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content":
                      f"【开发目标】\n{goal}\n\n【历史遗留问题（必须在本轮解决）】\n"
                      + ("\n".join(f"- {x}" for x in feedback) if feedback else "（无，首轮）")
                      + "\n\n请思考：功能边界、模块拆分、关键技术选型、潜在风险与验证方式。"
                        "简洁列出要点（不超过 15 条）。"}],
                    temperature=0.3, model_override=mo())
                yield await emit({"type": "phase", "phase": "THINK", "status": "end",
                                  "note": think[:500]})

                # ============ 2. 计划 + 3. 审查（内循环） ============
                plan_passed = False
                for _ in range(self.cfg.max_plan_cycles):
                    plan_cycles += 1
                    yield await emit({"type": "phase", "phase": "PLAN", "status": "start",
                                      "cycle": total_cycles})
                    plan = await self.llm.chat_json(
                        [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content":
                          f"【目标】{goal}\n【思考结论】\n{think}\n【必须解决的问题】\n"
                          + ("\n".join(f"- {x}" for x in feedback[-8:]) if feedback else "（无）")
                          + f"\n\n产出开发计划，JSON 结构: {json.dumps(PLAN_SCHEMA, ensure_ascii=False)}"
                          + "\n要求：文件划分清晰；Python 只用标准库或 fastapi/uvicorn/httpx/pyyaml；"
                            "必须包含可运行的测试文件（pytest 风格）；每个 .py 文件语法完整可独立编译；"
                            "涉及网络/文件/线程的代码必须有超时与关闭逻辑，避免内存泄漏。"}],
                        temperature=0.3, model_override=mo())
                    if not isinstance(plan, dict) or not plan.get("files"):
                        feedback.append("计划 JSON 不合格或缺少 files 字段")
                        continue
                    yield await emit({"type": "phase", "phase": "PLAN", "status": "end",
                                      "note": plan.get("summary", ""), "files": plan.get("files", [])})

                    yield await emit({"type": "phase", "phase": "REVIEW", "status": "start",
                                      "cycle": total_cycles})
                    review = await self.llm.chat_json(
                        [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content":
                          f"你是严格的架构评审员。目标：{goal}\n计划：\n{json.dumps(plan, ensure_ascii=False)}\n\n"
                          "逐项审查：1) 功能完整性 2) 文件间接口一致性（导入/函数签名）"
                          " 3) 可行性与依赖合法性 4) 测试计划是否覆盖验收标准 "
                          "5) 资源管理（文件/连接/线程是否有关闭方案）6) 安全性。"
                          '\n输出 JSON: {"verdict": "pass" 或 "revise", "issues": ["具体问题..."], '
                          '"suggestions": ["建议..."]}。只有没有实质性缺陷才允许 pass。'}],
                        temperature=0.2,
                        prefer=self.cfg.review_provider or None, model_override=mo())
                    verdict = str(review.get("verdict", "revise")) if isinstance(review, dict) else "revise"
                    issues = [str(x) for x in review.get("issues", [])] if isinstance(review, dict) else ["审查输出格式错误"]
                    yield await emit({"type": "phase", "phase": "REVIEW", "status": "end",
                                      "verdict": verdict, "issues": issues})
                    if verdict == "pass":
                        plan_passed = True
                        break
                    feedback.extend(issues)           # 审查不过 → 带意见重做计划
                if not plan_passed:
                    yield await emit({"type": "log", "phase": "REVIEW",
                                      "text": "计划审查多轮未通过，回到最初“思考”阶段重新循环"})
                    continue                          # ← 回到最初步骤

                # ============ 4. 开发 ============
                dev_passed = True
                files = {}
                for spec in plan.get("files", []):
                    path = spec["path"] if isinstance(spec, dict) else str(spec)
                    purpose = spec.get("purpose", "") if isinstance(spec, dict) else ""
                    ok_file, content = False, ""
                    for _try in range(2):
                        yield await emit({"type": "log", "phase": "DEVELOP", "text": f"生成文件 {path}（第{_try+1}次）"})
                        try:
                            out = await self.llm.chat_json(
                                [{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content":
                                  f"【计划】\n{json.dumps(plan, ensure_ascii=False)}\n"
                                  f"【现在只写这一个文件】路径: {path}\n职责: {purpose}\n"
                                  f"【已知问题，务必规避】\n" + ("\n".join(f"- {x}" for x in feedback[-6:]) if feedback else "（无）")
                                  + '\n\n输出 JSON: {"path": "' + path + '", "content": "完整文件内容"}。'
                                    "content 必须是完整可运行文件，不要省略、不要占位符。"}],
                                temperature=0.2)
                            content = str(out.get("content", "")) if isinstance(out, dict) else ""
                        except LLMError as e:
                            feedback.append(f"生成 {path} 失败: {e}")
                            continue
                        probs = deep_scan({path: content})
                        if not probs:
                            ok_file = True
                            break
                        for p_ in probs:
                            if isinstance(p_, dict):
                                file_, text_ = p_.get("file", path), str(p_.get("text", ""))
                            else:
                                file_, text_ = path, str(p_)
                            yield await emit({"type": "issue", "source": "static", "severity": "high",
                                              "file": file_, "text": text_})
                            feedback.append(text_)
                    target = _safe_join(root, path)
                    if not ok_file or target is None:
                        dev_passed = False
                        yield await emit({"type": "issue", "source": "static", "severity": "high",
                                          "file": path, "text": "文件多轮生成仍无法通过静态检查，需重新规划"})
                        break
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")
                    files[path] = content
                    yield await emit({"type": "file", "phase": "DEVELOP", "path": path, "bytes": len(content.encode("utf-8"))})
                if not dev_passed:
                    dev_cycles += 1
                    if dev_cycles > self.cfg.max_dev_cycles:
                        yield await emit({"type": "log", "phase": "DEVELOP", "text": "开发多轮回炉仍未通过，收尾并输出报告"})
                        break
                    continue                          # ← 回到最初步骤循环

                # ============ 5. 测试 ============
                yield await emit({"type": "phase", "phase": "TEST", "status": "start", "cycle": total_cycles})
                test_ok, test_summary, test_detail = True, "无测试文件", ""
                test_files = [f for f in files if re.match(r"tests[/\\]test_", f.replace("\\", "/"))]
                if test_files:
                    test_ok, test_summary, test_detail = self._run_pytest(root)
                yield await emit({"type": "tests", "ok": test_ok, "summary": test_summary,
                                  "output_tail": test_detail[-1500:]})
                # 静态深扫（逻辑错误/内存泄漏启发式）
                static_issues = [i for i in deep_scan(files) if isinstance(i, dict)]
                for i in static_issues:
                    yield await emit({"type": "issue", "source": "static", "severity": i.get("severity", "low"),
                                      "file": i.get("file", ""), "text": f"第{i.get('line','?')}行 {i.get('text','')}"})
                # AI 代码审查
                ai_review = await self.llm.chat_json(
                    [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content":
                      f"你是代码评审员。目标：{goal}\n\n完整代码：\n{_files_block(plan, files)}\n\n"
                      "重点检查：1) 明显逻辑错误与边界条件 2) 内存泄漏（容器无限增长/缓存无上限/闭包持有大对象）"
                      " 3) 资源未关闭（文件/连接/线程）4) 异常处理缺失导致崩溃 5) 安全问题。\n"
                      '输出 JSON: {"verdict": "pass" 或 "fix", '
                      '"issues": [{"severity": "high|medium|low", "kind": "logic|memory|security|style", '
                      '"file": "路径", "detail": "问题描述", "fix_hint": "修复建议"}]}。'
                      "只有 high 问题才判 fix；medium/low 随报告提示。"}],
                    temperature=0.2,
                    prefer=self.cfg.review_provider or None)
                ai_issues = ai_review.get("issues", []) if isinstance(ai_review, dict) else []
                high_issues = [i for i in ai_issues if isinstance(i, dict) and i.get("severity") == "high"]
                for i in ai_issues:
                    if isinstance(i, dict):
                        yield await emit({"type": "issue", "source": "code_review", "severity": i.get("severity", "low"),
                                          "file": i.get("file", ""), "text": f"[{i.get('kind','')}] {i.get('detail','')}"})
                yield await emit({"type": "phase", "phase": "TEST", "status": "end",
                                  "verdict": "pass" if (test_ok and not high_issues) else "fix"})
                if test_ok and not high_issues:
                    final_ok = True
                    break
                # 测试/审查不过 → 收集问题回炉
                dev_cycles += 1
                if test_ok is False:
                    feedback.append(
                        f"测试未通过: {test_summary}\n测试输出（据此修复）:\n{test_detail[-900:]}")
                feedback.extend(f"{i.get('file','')}: {i.get('detail','')}（提示: {i.get('fix_hint','')}）" for i in high_issues)
                if dev_cycles > self.cfg.max_dev_cycles:
                    yield await emit({"type": "log", "phase": "TEST", "text": "多轮回炉仍有问题，按当前成果收尾"})
                    break
                yield await emit({"type": "log", "phase": "TEST", "text": "存在问题，回到最初“思考”阶段重新循环"})

        except LLMError as e:
            yield await emit({"type": "error", "text": str(e)})
        finally:
            report = {
                "ok": final_ok,
                "project": slug,
                "goal": goal,
                "cycles": total_cycles,
                "plan_cycles": plan_cycles + 0,
                "dev_cycles": dev_cycles,
                "files": list(files.keys()),
                "open_feedback": feedback[-10:],
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            (root / ".agent_run.json").write_text(
                json.dumps({"report": report, "events": events}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            # ============ S6 复盘 ============
            retro = {}
            try:
                retro = await self.llm.chat_json(
                    [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content":
                      f"目标：{goal}\n结果：{'达标' if final_ok else '未完全达标'}\n"
                      f"循环次数：{total_cycles}；生成的文件：{json.dumps(list(files.keys()), ensure_ascii=False)}\n"
                      f"遗留问题：{json.dumps(feedback[-8:], ensure_ascii=False)}\n\n"
                      '输出 JSON: {"summary": "本次任务复盘（3-4句：做法/结果/主要问题）", '
                      '"knowledge_points": ["本次用到的关键知识点"], '
                      '"next_steps": ["建议的下一步行动"]}。'}],
                    temperature=0.3, prefer=self.cfg.review_provider or None, timeout=90)
            except Exception:
                retro = {"summary": "复盘生成失败（模型不可用），以报告数据为准。",
                         "knowledge_points": [], "next_steps": feedback[-3:]}
            try:
                yield await emit({"type": "retro", "retro": retro})
            except GeneratorExit:
                return
            # 运行日志（logs/runs.log 追加一行）
            try:
                logs_dir = self.workspace_root.parent / "logs"
                logs_dir.mkdir(exist_ok=True)
                with (logs_dir / "runs.log").open("a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{slug}\t"
                            f"{'OK' if final_ok else 'PARTIAL'}\tcycles={total_cycles}\t"
                            f"files={len(files)}\t{goal[:80]}\n")
            except Exception:
                pass
            yield await emit({"type": "done", "ok": final_ok, "project": slug, "report": report})

    # ---------- pytest 子进程 ----------
    def _run_pytest(self, root: Path) -> tuple[bool, str, str]:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            r = subprocess.run(
                [sys.executable, "-X", "utf8", "-m", "pytest", "-x", "-q", "--tb=short"],
                cwd=str(root), capture_output=True, text=True, timeout=self.cfg.cmd_timeout,
                encoding="utf-8", errors="ignore", env=env,
            )
            out = (r.stdout or "") + (r.stderr or "")
            ok = r.returncode == 0
            tail = out.strip().splitlines()[-12:] if out.strip() else []
            return ok, ("全部通过" if ok else "存在失败用例"), "\n".join(tail)
        except subprocess.TimeoutExpired:
            return False, f"测试超时(>{self.cfg.cmd_timeout}s)，疑似死循环", ""
        except Exception as e:
            return False, f"测试执行异常: {e}", ""
