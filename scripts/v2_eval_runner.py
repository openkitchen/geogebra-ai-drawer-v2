#!/usr/bin/env python3
"""
v2 Evaluation Runner (LLM-as-a-Judge)

Runs a set of test cases (golden set) against the API, verifies assertions (regex/logic),
and optionally uses a secondary LLM to judge the quality of the response.

Dependencies:
    Standard library only (uses threading for concurrency to avoid 3rd party deps).
    Optional: 'openai' package if using OpenAI-compatible judge (but we implement raw HTTP too).

Usage:
    # 1. Start API
    ./scripts/v2_dev.sh

    # 2. Run Evals (LLM judge uses the `fast` role from `.env.local`)
    python3 scripts/v2_eval_runner.py
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import re
import sys
import time
import urllib.request
import urllib.error
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# --- Configuration ---

@dataclass
class EvalConfig:
    base_url: str
    judge_api_key: str | None
    judge_base_url: str | None
    judge_model: str
    concurrency: int
    golden_set_path: str
    verbose: bool

_ENV_REF_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _strip_wrapping_quotes(raw: str) -> str:
    s = raw.strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    return s


def _expand_env_refs(raw: str, env_vars: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return env_vars.get(key) or ""

    out = raw
    for _ in range(6):
        expanded = _ENV_REF_RE.sub(repl, out)
        if expanded == out:
            break
        out = expanded
    return out


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env-style file (best-effort, supports multi-line quoted values)."""
    if not path.is_file():
        return {}

    out: dict[str, str] = {}
    lines = path.read_text("utf-8").splitlines()
    i = 0
    while i < len(lines):
        raw_line = lines[i]
        i += 1

        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].lstrip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.lstrip()

        if not value:
            out[key] = ""
            continue

        if value[0] in {"'", '"'}:
            quote = value[0]
            first = value[1:]
            parts: list[str] = []
            if first.rstrip().endswith(quote):
                parts.append(first.rstrip()[:-1])
            else:
                parts.append(first)
                while i < len(lines):
                    nxt = lines[i]
                    i += 1
                    if nxt.rstrip().endswith(quote):
                        parts.append(nxt.rstrip()[:-1])
                        break
                    parts.append(nxt)
            out[key] = "\n".join(parts)
            continue

        # Unquoted value. (We intentionally keep it simple; no inline comment stripping.)
        out[key] = value

    return out


def load_config(args: argparse.Namespace) -> EvalConfig:
    # Avoid proxy issues for localhost
    os.environ["no_proxy"] = "localhost,127.0.0.1"

    root = _repo_root()
    env_path = (os.getenv("V2_ENV_FILE") or "").strip() or ".env.local"
    env_file = Path(env_path)
    if not env_file.is_absolute():
        env_file = (root / env_file).resolve()

    env_vars = os.environ.copy()
    for k, v in _parse_env_file(env_file).items():
        env_vars.setdefault(k, v)

    # Resolve judge config.
    # Policy: Judge is always the project's `fast` role, same as other roles.
    # No EVAL_JUDGE_* overrides. No OPENAI_* fallback.
    judge_api_key: str | None = None
    judge_base_url: str | None = None
    judge_model: str = ""

    try:
        aliases_json = env_vars.get("LLM_MODEL_ALIASES_JSON")
        bindings_json = env_vars.get("LLM_ROLE_BINDINGS_JSON")

        if aliases_json and bindings_json:
            aliases = json.loads(_expand_env_refs(_strip_wrapping_quotes(aliases_json), env_vars))
            bindings = json.loads(_expand_env_refs(_strip_wrapping_quotes(bindings_json), env_vars))

            fast_alias_id = bindings.get("fast") if isinstance(bindings, dict) else None
            if isinstance(fast_alias_id, str) and fast_alias_id.strip() and isinstance(aliases, list):
                chosen = next((a for a in aliases if isinstance(a, dict) and a.get("id") == fast_alias_id), None)
                if isinstance(chosen, dict):
                    api_key = chosen.get("apiKey")
                    if isinstance(api_key, str) and api_key.strip():
                        judge_api_key = api_key.strip()

                    base = chosen.get("baseURL") or chosen.get("baseUrl") or chosen.get("base_url")
                    if isinstance(base, str) and base.strip():
                        judge_base_url = base.strip().rstrip("/")

                    model = chosen.get("modelId") or chosen.get("model")
                    if not model and isinstance(chosen.get("models"), dict):
                        model = chosen["models"].get("main")
                    if isinstance(model, str) and model.strip():
                        judge_model = model.strip()
    except Exception as e:
        if getattr(args, "verbose", False):
            print(f"Warning: Failed to parse project LLM config for judge (fast role): {e}")

    return EvalConfig(
        base_url=args.base_url.rstrip("/"),
        judge_api_key=judge_api_key,
        judge_base_url=judge_base_url,
        judge_model=judge_model,
        concurrency=args.concurrency,
        golden_set_path=args.dataset,
        verbose=args.verbose,
    )

# --- Fake Canvas (Ported from smoke_test) ---

_POINT_RE = re.compile(
    r"\(\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*\)"
)

_ROTATE_RE = re.compile(
    r"rotate\(\s*([A-Za-z][A-Za-z0-9_]*)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*°\s*,\s*([A-Za-z][A-Za-z0-9_]*)\s*\)",
    re.IGNORECASE,
)


def _extract_assignment_label(command: str) -> str | None:
    if "=" not in command:
        return None
    left, _ = command.split("=", 1)
    label = left.strip()
    if not label:
        return None
    # Avoid returning "Circle(A,1)" etc.
    if any(ch in label for ch in " ()"):
        return None
    return label


def _infer_object_type(command: str) -> str | None:
    t = command.strip()
    rhs = t.split("=", 1)[1].strip() if "=" in t else t
    low = rhs.lower()
    if low.startswith("(") and "," in low and ")" in low:
        return "point"
    if low.startswith("rotate(") or "rotate(" in low:
        return "point"
    if low.startswith("midpoint(") or "midpoint(" in low or "中点(" in rhs:
        return "point"
    if "circle(" in low or low.startswith("circle("):
        return "circle"
    if "polygon(" in low or low.startswith("polygon("):
        return "polygon"
    if "segment(" in low or low.startswith("segment("):
        return "segment"
    if "line(" in low or low.startswith("line("):
        return "line"
    return None


def _parse_point_coords(command: str) -> tuple[float, float] | None:
    m = _POINT_RE.search(command)
    if not m:
        return None
    try:
        return (float(m.group(1)), float(m.group(2)))
    except Exception:
        return None


def _polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    s = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _try_eval_point(rhs: str, known: dict[str, tuple[float, float]]) -> tuple[float, float] | None:
    m = _ROTATE_RE.search(rhs)
    if m:
        src = m.group(1)
        deg = float(m.group(2))
        center = m.group(3)
        if src in known and center in known:
            x, y = known[src]
            cx, cy = known[center]
            dx = x - cx
            dy = y - cy
            rad = math.radians(deg)
            rx = dx * math.cos(rad) - dy * math.sin(rad) + cx
            ry = dx * math.sin(rad) + dy * math.cos(rad) + cy
            return (rx, ry)

    # Midpoint(A, B) / 中点(A, B)
    if "midpoint" in rhs.lower() or "中点" in rhs:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]*", rhs)
        if len(tokens) >= 3:
            a = tokens[1]
            b = tokens[2]
            if a in known and b in known:
                ax, ay = known[a]
                bx, by = known[b]
                return ((ax + bx) / 2.0, (ay + by) / 2.0)

    return None


@dataclass
class FakeCanvas:
    objects_by_name: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    point_coords: Dict[str, tuple[float, float]] = field(default_factory=dict)
    auto_counters: Dict[str, int] = field(default_factory=dict)

    def snapshot_objects(self) -> List[Dict[str, Any]]:
        # Preserve insertion order (dicts are ordered in Python 3.7+).
        return list(self.objects_by_name.values())

    def _next_auto_label(self, kind: str) -> str:
        n = int(self.auto_counters.get(kind, 0)) + 1
        self.auto_counters[kind] = n
        prefix = {
            "point": "P",
            "circle": "c",
            "polygon": "poly",
            "segment": "s",
            "line": "l",
        }.get(kind, "obj")
        return f"{prefix}{n}"

    def _upsert_object(self, obj: Dict[str, Any]) -> None:
        name = obj.get("name")
        if not isinstance(name, str) or not name.strip():
            return
        self.objects_by_name[name] = obj

    def _delete_object(self, name: str) -> bool:
        if name in self.objects_by_name:
            self.objects_by_name.pop(name, None)
            self.point_coords.pop(name, None)
            return True
        return False

    def apply_command(self, command: str) -> Tuple[Dict[str, Any], List[str], List[str]]:
        cmd = command.strip()
        created: List[str] = []
        deleted: List[str] = []

        # Delete(Object) / Delete[Object]
        low = cmd.lower()
        if low.startswith("delete(") or low.startswith("delete["):
            close = ")" if low.startswith("delete(") else "]"
            inside = cmd[cmd.find("(" if close == ")" else "[") + 1 : cmd.rfind(close)]
            for part in inside.split(","):
                name = part.strip()
                if name and self._delete_object(name):
                    deleted.append(name)
            return ({"command": command, "ok": True, "labels": None, "error": None}, created, deleted)

        label = _extract_assignment_label(cmd)
        rhs = cmd.split("=", 1)[1].strip() if "=" in cmd else cmd
        obj_type = _infer_object_type(cmd)

        if not label and obj_type:
            label = self._next_auto_label(obj_type)

        labels: List[str] | None = None
        if label and obj_type:
            visible = True
            value_string: str | None = None

            if obj_type == "point":
                coords = _parse_point_coords(rhs)
                if coords is None:
                    coords = _try_eval_point(rhs, self.point_coords)
                if coords is not None:
                    self.point_coords[label] = coords
                    x, y = coords
                    value_string = f"{label} = ({x:.1f}, {y:.1f})"

            if obj_type == "polygon":
                tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]*", rhs)
                verts = [t for t in tokens[1:]] if tokens else []
                pts: list[tuple[float, float]] = []
                for v in verts[:12]:
                    if v in self.point_coords:
                        pts.append(self.point_coords[v])
                if len(pts) >= 3:
                    area = _polygon_area(pts)
                    value_string = f"{label} = {area:.1f}"

            self._upsert_object(
                {
                    "name": label,
                    "type": obj_type,
                    "visible": visible,
                    "valueString": value_string,
                    "definitionString": cmd,
                    "commandString": cmd,
                }
            )
            created.append(label)
            labels = [label]

        return ({"command": command, "ok": True, "labels": labels, "error": None}, created, deleted)

    def exec_commands(self, commands: List[str]) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        created_all: List[str] = []
        deleted_all: List[str] = []

        for cmd in commands:
            res, created, deleted = self.apply_command(cmd)
            results.append(res)
            created_all.extend(created)
            deleted_all.extend(deleted)

        return {
            "results": results,
            "created_objects": created_all,
            "deleted_objects": deleted_all,
            "rolled_back_objects": None,
            "rollback_errors": None,
            "dialogs": None,
            "preset_applied": "geometry",
            "quality_warnings": None,
        }

# --- API Client ---

def http_post_sse(url: str, body: Dict[str, Any], timeout: float = 30.0) -> List[Dict[str, Any]]:
    """Simulates an SSE client using standard urllib, returning a list of parsed events."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, 
        data=data, 
        headers={"Content-Type": "application/json", "Accept": "text/event-stream", "Accept-Encoding": "identity"},
        method="POST"
    )
    
    events = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Robust SSE parser
            data_lines = []
            current_event = "message"
            
            for line_bytes in resp:
                line = line_bytes.decode("utf-8").rstrip("\n")
                if line.endswith("\r"):
                    line = line[:-1]

                if not line:
                    # End of event
                    if data_lines:
                        data_raw = "\n".join(data_lines)
                        try:
                            payload = json.loads(data_raw)
                        except:
                            payload = data_raw
                        events.append({"event": current_event, "data": payload})
                    
                    data_lines = []
                    current_event = "message"
                    continue
                
                if line.startswith("event:"):
                    current_event = line[6:].strip()
                elif line.startswith("data:"):
                    # data: <content>
                    # Preserves leading space if any, but spec says "remove one space"
                    content = line[5:]
                    if content.startswith(" "):
                        content = content[1:]
                    data_lines.append(content)
                elif line.startswith(":"):
                    pass # comment
            
            # Flush last
            if data_lines:
                data_raw = "\n".join(data_lines)
                try:
                    payload = json.loads(data_raw)
                except:
                    payload = data_raw
                events.append({"event": current_event, "data": payload})
                
    except Exception as e:
        print(f"Error reading SSE stream from {url}: {e}", file=sys.stderr)
        # Don't raise, return what we got
        return events
        
    return events

# --- Judge Client ---

def call_llm_judge(config: EvalConfig, prompt: str) -> Dict[str, Any]:
    """Calls an OpenAI-compatible LLM to judge the output."""
    if not config.judge_api_key or not config.judge_base_url or not config.judge_model:
        return {
            "pass": False,
            "reason": "Judge not configured. Set LLM_MODEL_ALIASES_JSON + LLM_ROLE_BINDINGS_JSON in .env.local and bind role 'fast' to an alias with apiKey/baseURL/modelId.",
        }

    url = f"{config.judge_base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.judge_api_key}"
    }
    
    payload = {
        "model": config.judge_model,
        "messages": [
            {"role": "system", "content": "You are an impartial judge for an AI geometry tutor. Output JSON only: {\"pass\": boolean, \"reason\": string}."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }
    
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:
        return {"pass": False, "reason": f"Judge LLM call failed: {str(e)}"}

# --- Assertion Logic ---

def check_assertion(assertion: Dict[str, Any], trace: Dict[str, Any], config: EvalConfig) -> Dict[str, Any]:
    """
    trace: {
      "tool_calls": [{"name": "...", "input": ...}],
      "final_text": "...",
      "user_prompt": "..."
    }
    """
    a_type = assertion["type"]
    
    if a_type == "tool_called":
        target_tool = assertion["tool_name"]
        required = assertion.get("required", True)
        
        found = any(tc["name"] == target_tool for tc in trace["tool_calls"])
        if required and not found:
            return {"pass": False, "reason": f"Tool '{target_tool}' was NOT called."}
        if not required and found:
            return {"pass": False, "reason": f"Tool '{target_tool}' SHOULD NOT be called."}
        return {"pass": True, "reason": f"Tool usage check passed for '{target_tool}'."}

    elif a_type == "regex":
        pattern = assertion["pattern"]
        target = assertion.get("target", "final_text")
        
        text_to_search = ""
        if target == "final_text":
            text_to_search = trace["final_text"]
        elif target == "tool_input":
            # Search in ALL tool inputs
            text_to_search = json.dumps([tc["input"] for tc in trace["tool_calls"]])
            
        if re.search(pattern, text_to_search):
            return {"pass": True, "reason": f"Regex '{pattern}' found in {target}."}
        else:
            return {"pass": False, "reason": f"Regex '{pattern}' NOT found in {target}."}

    elif a_type == "llm_judge":
        rubric = assertion["rubric"]
        judge_prompt = f"""
User Request: {trace['user_prompt']}

AI Tool Calls:
{json.dumps(trace['tool_calls'], ensure_ascii=False, indent=2)}

AI Explanation:
{trace['final_text']}

Rubric: {rubric}

Evaluate if the AI followed the rubric.
"""
        return call_llm_judge(config, judge_prompt)

    return {"pass": False, "reason": f"Unknown assertion type: {a_type}"}

# --- Runner Logic ---

def extract_final_explanation(data: Any) -> str:
    """Extract assistant explanation text from a v2 SSE 'final' payload.

    Current v2 shape:
      {"answer": {"explanation": "...", "overlay_text": ...}}
    """

    if isinstance(data, str):
        return data.strip()

    if not isinstance(data, dict):
        return ""

    answer = data.get("answer")
    if isinstance(answer, dict):
        explanation = answer.get("explanation")
        if isinstance(explanation, str) and explanation.strip():
            return explanation.strip()
        content = answer.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

    # Legacy / experimental shapes.
    output = data.get("output")
    if isinstance(output, str) and output.strip():
        return output.strip()
    if isinstance(output, dict):
        for k in ("content", "explanation", "text"):
            v = output.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    text = data.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    return ""


def run_single_eval(case: Dict[str, Any], config: EvalConfig) -> Dict[str, Any]:
    """Runs a single test case through the API and asserts results."""
    
    # 1. Setup
    try:
        thread_res = json.loads(urllib.request.urlopen(f"{config.base_url}/api/threads", data=b"", timeout=5).read())
        thread_id = thread_res["thread_id"]
    except Exception as e:
         return {
            "id": case.get("id", "unknown"),
            "status": "error",
            "error": f"Failed to create thread: {e}"
        }
    
    # 2. Run interaction loop (simplified smoke test logic)
    trace = {
        "user_prompt": case["prompt"],
        "tool_calls": [],
        "final_text": ""
    }
    
    # Initial Run
    body = {"input": {"user_text": case["prompt"]}, "ui_context": {"debug": True}}
    run_url = f"{config.base_url}/api/threads/{thread_id}/runs/stream"
    
    # Loop for interrupts
    max_turns = 5
    current_url = run_url
    current_body = body
    
    # We need a shared canvas for this session
    canvas = FakeCanvas()
    run_id = None
    
    try:
        for _ in range(max_turns):
            events = http_post_sse(current_url, current_body)
            
            interrupt = None
            
            for ev in events:
                if ev["event"] == "interrupt":
                    interrupt = ev["data"]
                elif ev["event"] == "run_start":
                    run_id = ev["data"].get("run_id")
                elif ev["event"] == "final":
                    extracted = extract_final_explanation(ev["data"])
                    if extracted:
                        trace["final_text"] = extracted
                elif ev["event"] == "run_end":
                    pass

            if not interrupt:
                break # Run finished
                
            # Handle Tool
            tool_name = interrupt["tool_name"]
            tool_input = interrupt["input"]
            tool_call_id = interrupt["tool_call_id"]
            
            trace["tool_calls"].append({"name": tool_name, "input": tool_input})
            
            # Exec logic (Fake)
            output = {"stub": True}
            if tool_name == "exec_geogebra_commands":
                cmds = tool_input.get("commands", [])
                cmd_list = [c for c in cmds if isinstance(c, str)] if isinstance(cmds, list) else []
                output = canvas.exec_commands(cmd_list)
            elif tool_name == "get_canvas_state":
                output = {"objects": canvas.snapshot_objects()}
                
            # Resume
            current_url = f"{config.base_url}/api/threads/{thread_id}/runs/{run_id}/resume"
            current_body = {
                "command": {
                    "resume": {
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "ok": True,
                        "output": output
                    }
                }
            }
            
    except Exception as e:
        return {
            "id": case.get("id", "unknown"),
            "status": "error",
            "error": str(e)
        }

    # 3. Verify Assertions
    results = []
    overall_pass = True
    
    for assertion in case.get("assertions", []):
        res = check_assertion(assertion, trace, config)
        res["assertion"] = assertion
        results.append(res)
        if not res["pass"]:
            overall_pass = False
            
    return {
        "id": case.get("id"),
        "status": "pass" if overall_pass else "fail",
        "results": results,
        "trace_summary": {
            "tool_count": len(trace["tool_calls"]),
            "text_len": len(trace["final_text"])
        }
    }

# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Run v2 Evals")
    parser.add_argument("--base-url", default="http://127.0.0.1:3002", help="API Base URL")
    parser.add_argument("--dataset", default="docs/evals/golden_set.jsonl", help="Path to golden set jsonl")
    parser.add_argument("--concurrency", type=int, default=5, help="Parallel requests")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    config = load_config(args)
    
    if not os.path.exists(config.golden_set_path):
        print(f"Dataset not found: {config.golden_set_path}")
        sys.exit(1)

    cases = []
    with open(config.golden_set_path, "r") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))
                
    print(f"Loaded {len(cases)} test cases.")
    print(f"Judge Model: {config.judge_model} (API Key Configured: {'Yes' if config.judge_api_key else 'NO'})")
    print(f"Running with concurrency {config.concurrency}...")
    
    start_time = time.time()
    passed = 0
    failed = 0
    errors = 0
    
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=config.concurrency) as executor:
        future_to_case = {executor.submit(run_single_eval, case, config): case for case in cases}
        
        for future in concurrent.futures.as_completed(future_to_case):
            case = future_to_case[future]
            try:
                data = future.result()
                results.append(data)
                
                status = data["status"]
                if status == "pass":
                    passed += 1
                    print(".", end="", flush=True)
                elif status == "fail":
                    failed += 1
                    print("F", end="", flush=True)
                else:
                    errors += 1
                    print("E", end="", flush=True)
                    
            except Exception as exc:
                print(f"\nCase {case.get('id')} generated an exception: {exc}")
                errors += 1

    duration = time.time() - start_time
    print(f"\n\nDone in {duration:.2f}s")
    print(f"Total: {len(cases)} | Pass: {passed} | Fail: {failed} | Error: {errors}")
    
    if failed > 0 or errors > 0:
        print("\n=== Failures ===")
        for r in results:
            if r["status"] != "pass":
                print(f"\nID: {r.get('id')}")
                if r.get("error"):
                    print(f"  System Error: {r['error']}")
                else:
                    for res in r.get("results", []):
                        if not res["pass"]:
                            print(f"  [FAIL] {res['reason']}")
                            if config.verbose and "assertion" in res:
                                print(f"         Trace Tool Input: {json.dumps(res.get('assertion', {}), indent=2)}")

    sys.exit(1 if failed + errors > 0 else 0)

if __name__ == "__main__":
    main()
