"""全局配置加载：config.yaml + 环境变量 + 可选 .env 文件。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]          # D:\llm-tutor-agent
DATA_DIR = ROOT / "data"
CURRICULUM_DIR = DATA_DIR / "curriculum"
USERDOCS_DIR = DATA_DIR / "userdocs"
LEETCODE_FILE = DATA_DIR / "leetcode" / "problems.json"
KB_INDEX_DIR = DATA_DIR / "kb_index"
PROGRESS_DIR = DATA_DIR / "progress"
WORKSPACE_DIR = ROOT / "workspace"
FRONTEND_DIR = ROOT / "frontend"


def _load_dotenv() -> None:
    """极简 .env 读取（key=value 行），不覆盖已存在的环境变量。"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


@dataclass
class ProviderCfg:
    name: str
    kind: str                     # ollama | openai
    base_url: str
    model: str = ""
    api_key_env: str = ""
    enabled: str = "auto"         # true | false | auto(有 key 才启用)

    def resolved_enabled(self) -> bool:
        if self.enabled == "false":
            return False
        if self.enabled == "true":
            return True
        return bool(self.api_key())  # auto

    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "") if self.api_key_env else ""


@dataclass
class DevAgentCfg:
    max_plan_cycles: int = 2
    max_dev_cycles: int = 2
    max_total_cycles: int = 6
    cmd_timeout: int = 120
    review_provider: str = ""   # 审查/复盘优先用哪个 provider（如外部强模型），留空按全局策略
    escalate_model: str = ""    # 回炉时自动升级到的模型名（如 qwen3:14b 或外部模型），留空不升级


@dataclass
class RagCfg:
    chunk_size: int = 700
    chunk_overlap: int = 120
    top_k: int = 5
    use_ollama_embeddings: bool = True
    embed_candidates: list[str] = field(
        default_factory=lambda: ["nomic-embed-text", "bge-m3", "mxbai-embed-large"]
    )


@dataclass
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8787
    strategy: str = "local_first"          # local_first | external_first | only
    strategy_only: str = ""
    providers: list[ProviderCfg] = field(default_factory=list)
    dev_agent: DevAgentCfg = field(default_factory=DevAgentCfg)
    rag: RagCfg = field(default_factory=RagCfg)
    leetcode_timeout: int = 10
    web_search_enabled: bool = True


def _build_dataclass(cls, data: dict[str, Any]):
    if not isinstance(data, dict):
        return cls()
    known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
    return cls(**{k: v for k, v in data.items() if k in known})


def load_config(path: Path | None = None) -> AppConfig:
    _load_dotenv()
    cfg_path = path or (ROOT / "config.yaml")
    raw: dict[str, Any] = {}
    if cfg_path.exists():
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    app = raw.get("app", {}) or {}
    llm = raw.get("llm", {}) or {}
    providers = [
        _build_dataclass(ProviderCfg, p or {})
        for p in (llm.get("providers") or [])
    ]
    dev = _build_dataclass(DevAgentCfg, raw.get("dev_agent") or {})
    rag = _build_dataclass(RagCfg, raw.get("rag") or {})
    lc = raw.get("leetcode") or {}
    web = raw.get("web") or {}

    return AppConfig(
        host=str(app.get("host", "127.0.0.1")),
        port=int(app.get("port", 8787)),
        strategy=str(llm.get("strategy", "local_first")),
        strategy_only=str(llm.get("strategy_only", "")),
        providers=providers,
        dev_agent=dev,
        rag=rag,
        leetcode_timeout=int(lc.get("timeout_sec", 10)),
        web_search_enabled=bool(web.get("search_enabled", True)),
    )
