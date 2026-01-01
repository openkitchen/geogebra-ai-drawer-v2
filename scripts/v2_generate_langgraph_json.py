#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_URL = "https://langgra.ph/schema.json"
DEFAULT_GRAPH_NAME = "geogebra_v2"
DEFAULT_GRAPH_ENTRYPOINT = "app.runtime_graph:graph"


def _repo_root() -> Path:
    # scripts/v2_generate_langgraph_json.py -> repo root
    return Path(__file__).resolve().parents[1]


def _ensure_runtime_graph_exists(api_dir: Path) -> None:
    runtime_graph = api_dir / "app" / "runtime_graph.py"
    if not runtime_graph.is_file():
        raise FileNotFoundError(f"Missing runtime graph module: {runtime_graph}")
    text = runtime_graph.read_text(encoding="utf-8")
    if not re.search(r"^\s*graph\s*=", text, flags=re.MULTILINE):
        raise RuntimeError(f"`graph = ...` not found in: {runtime_graph}")


def _build_config(*, repo_root: Path, api_dir: Path, graph_name: str, entrypoint: str) -> dict[str, Any]:
    env_path = repo_root / ".env.local"
    env_rel = os.path.relpath(env_path, api_dir)
    return {
        "$schema": SCHEMA_URL,
        "dependencies": ["."],
        "graphs": {graph_name: entrypoint},
        "env": env_rel,
        "image_distro": "wolfi",
    }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate apps/api/langgraph.json for LangGraph Studio.")
    parser.add_argument("--graph-name", default=DEFAULT_GRAPH_NAME)
    parser.add_argument("--entrypoint", default=DEFAULT_GRAPH_ENTRYPOINT)
    parser.add_argument("--stdout", action="store_true", help="Print JSON to stdout instead of writing file.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the existing file differs from the expected config.",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    api_dir = root / "apps" / "api"
    out_path = api_dir / "langgraph.json"

    _ensure_runtime_graph_exists(api_dir)
    cfg = _build_config(repo_root=root, api_dir=api_dir, graph_name=args.graph_name, entrypoint=args.entrypoint)

    if args.check:
        if not out_path.is_file():
            print(f"[langgraph.json] missing: {out_path}", file=sys.stderr)
            return 2
        current = _read_json(out_path)
        if current != cfg:
            print(f"[langgraph.json] differs: {out_path}", file=sys.stderr)
            return 3
        print(f"[langgraph.json] OK: {out_path}")
        return 0

    payload = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    if args.stdout:
        sys.stdout.write(payload)
        return 0

    out_path.write_text(payload, encoding="utf-8")
    print(f"[langgraph.json] wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
