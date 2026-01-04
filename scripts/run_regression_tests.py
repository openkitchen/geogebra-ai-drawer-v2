#!/usr/bin/env python3
"""
Regression Test Runner (v2)

This script runs the v2 "golden set" against the local API and writes a JSON report
for CI/regression tracking.

By default it runs deterministic assertions only (tool_called/regex). Use
--with-llm-judge to enable LLM-based judging (requires EVAL_JUDGE_API_KEY or an
equivalent project LLM role binding).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import v2_eval_runner


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _try_git_head(root: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except Exception:
        return None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(str(path))

    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSONL at {path}:{lineno}: {e}") from e
            if not isinstance(item, dict):
                raise ValueError(f"Invalid JSONL at {path}:{lineno}: expected object")
            cases.append(item)
    return cases


def _prepare_case(
    case: dict[str, Any],
    *,
    with_llm_judge: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    assertions = case.get("assertions") or []
    if not isinstance(assertions, list):
        assertions = []

    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for a in assertions:
        if not isinstance(a, dict):
            continue
        if a.get("type") == "llm_judge" and not with_llm_judge:
            skipped.append(a)
            continue
        kept.append(a)

    prepared = dict(case)
    prepared["assertions"] = kept
    return prepared, skipped


def _default_report_path(*, root: Path, prompt_version: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in prompt_version.strip())
    if not safe:
        safe = "dev"
    return root / "logs" / "regression" / f"regression-{safe}.json"


def main() -> int:
    root = _repo_root()
    default_dataset = root / "docs" / "evals" / "golden_set.jsonl"

    parser = argparse.ArgumentParser(description="Run v2 regression tests (golden set)")
    parser.add_argument("--prompt-version", required=True, help="Prompt version label (e.g. v2.1.0)")
    parser.add_argument("--base-url", default="http://127.0.0.1:3002", help="API base URL")
    parser.add_argument("--dataset", default=str(default_dataset), help="Path to golden set jsonl")
    parser.add_argument("--concurrency", type=int, default=5, help="Parallel requests")
    parser.add_argument("--max-cases", type=int, default=0, help="If set, run only first N cases")
    parser.add_argument(
        "--with-llm-judge",
        action="store_true",
        help="Enable LLM-based assertions (llm_judge). Requires judge API key configuration.",
    )
    parser.add_argument("--output", default="", help="Report JSON path (default: logs/regression/...)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = (root / dataset_path).resolve()

    report_path = Path(args.output) if args.output else _default_report_path(root=root, prompt_version=args.prompt_version)
    if not report_path.is_absolute():
        report_path = (root / report_path).resolve()

    cases = _load_jsonl(dataset_path)
    if args.max_cases and args.max_cases > 0:
        cases = cases[: args.max_cases]

    started_at = datetime.now(timezone.utc)
    started_at_iso = started_at.isoformat()

    # Reuse v2_eval_runner configuration logic (env + .env.local parsing).
    config_args = argparse.Namespace(
        base_url=args.base_url,
        dataset=str(dataset_path),
        concurrency=args.concurrency,
        verbose=args.verbose,
    )
    config = v2_eval_runner.load_config(config_args)

    if args.with_llm_judge and not config.judge_api_key:
        print("ERR: --with-llm-judge requires a judge API key (EVAL_JUDGE_API_KEY).", file=sys.stderr)
        return 2

    print(f"Loaded {len(cases)} cases from {dataset_path}")
    print(f"Base URL: {config.base_url}")
    print(f"Prompt Version: {args.prompt_version}")
    print(f"Concurrency: {config.concurrency}")
    print(f"LLM Judge Enabled: {'Yes' if args.with_llm_judge else 'No (deterministic only)'}")

    results: list[dict[str, Any]] = []
    passed = failed = errors = 0
    skipped_assertions = 0

    def run_case(case: dict[str, Any]) -> dict[str, Any]:
        prepared, skipped = _prepare_case(case, with_llm_judge=args.with_llm_judge)
        res = v2_eval_runner.run_single_eval(prepared, config)

        # Enrich report with a stable subset of the input (avoid leaking secrets).
        res["prompt"] = case.get("prompt")
        res["skipped_assertions"] = len(skipped)

        if skipped:
            res.setdefault("results", [])
            for a in skipped:
                res["results"].append(
                    {
                        "pass": True,
                        "skipped": True,
                        "reason": "Skipped (llm_judge disabled). Re-run with --with-llm-judge to enable.",
                        "assertion": a,
                    }
                )
        return res

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.concurrency) as executor:
        future_to_case = {executor.submit(run_case, case): case for case in cases}
        for future in concurrent.futures.as_completed(future_to_case):
            try:
                data = future.result()
            except Exception as e:
                errors += 1
                print(f"E (exception: {type(e).__name__}: {e})", file=sys.stderr)
                continue

            results.append(data)
            skipped_assertions += int(data.get("skipped_assertions") or 0)

            status = data.get("status")
            if status == "pass":
                passed += 1
                print(".", end="", flush=True)
            elif status == "fail":
                failed += 1
                print("F", end="", flush=True)
            else:
                errors += 1
                print("E", end="", flush=True)

    duration_s = time.time() - t0
    print()

    report = {
        "meta": {
            "prompt_version": args.prompt_version,
            "git_commit": _try_git_head(root),
            "started_at": started_at_iso,
            "duration_s": duration_s,
            "base_url": config.base_url,
            "dataset_path": str(dataset_path),
            "case_count": len(cases),
            "concurrency": config.concurrency,
            "with_llm_judge": bool(args.with_llm_judge),
            "judge_model": config.judge_model,
            "judge_base_url": config.judge_base_url,
            "judge_api_key_configured": bool(config.judge_api_key),
            "runner": "scripts/run_regression_tests.py",
        },
        "summary": {
            "total": len(cases),
            "pass": passed,
            "fail": failed,
            "error": errors,
            "skipped_assertions": skipped_assertions,
        },
        "results": sorted(results, key=lambda r: str(r.get("id") or "")),
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(
        f"Done in {duration_s:.2f}s | Total: {len(cases)} | Pass: {passed} | Fail: {failed} | Error: {errors} | Skipped assertions: {skipped_assertions}"
    )
    print(f"Report: {report_path}")

    return 0 if failed == 0 and errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

