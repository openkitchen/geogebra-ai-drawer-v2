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

    # 2. Run Evals
    export EVAL_JUDGE_API_KEY="sk-..."  # or use .env
    python3 scripts/v2_eval_runner.py
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
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

def load_config(args: argparse.Namespace) -> EvalConfig:
    # Avoid proxy issues for localhost
    os.environ["no_proxy"] = "localhost,127.0.0.1"

    # Try loading .env with python-dotenv first for robust parsing
    try:
        from dotenv import load_dotenv
        load_dotenv(".env.local")
        load_dotenv(".env")
        env_vars = os.environ.copy()
    except ImportError:
        # Fallback to manual parsing
        env_files = [Path(".env.local"), Path(".env")]
        env_vars = os.environ.copy()
        
        for p in env_files:
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"): continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            # strip quotes
                            v = v.strip()
                            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                                v = v[1:-1]
                            if k not in env_vars: # Don't override existing env
                                env_vars[k] = v

    # Resolve Judge Config
    # Priority: 1. EVAL_JUDGE_* vars 2. "fast" role from project config
    
    judge_api_key = env_vars.get("EVAL_JUDGE_API_KEY")
    judge_base_url = env_vars.get("EVAL_JUDGE_BASE_URL")
    judge_model = env_vars.get("EVAL_JUDGE_MODEL")
    
    if not judge_api_key:
        # Try to resolve "fast" role
        try:
            aliases_json = env_vars.get("LLM_MODEL_ALIASES_JSON")
            bindings_json = env_vars.get("LLM_ROLE_BINDINGS_JSON")
            
            if aliases_json and bindings_json:
                aliases = json.loads(aliases_json)
                bindings = json.loads(bindings_json)
                
                # Check for "fast" role binding
                fast_alias_id = bindings.get("fast")
                if fast_alias_id:
                    # Find matching alias
                    chosen = next((a for a in aliases if a.get("id") == fast_alias_id), None)
                    if chosen:
                        judge_api_key = chosen.get("apiKey")
                        
                        # Handle base URL
                        base = chosen.get("baseURL") or chosen.get("baseUrl") or chosen.get("base_url")
                        if base:
                            judge_base_url = str(base).rstrip("/")
                        
                        # Handle model name
                        model = chosen.get("modelId") or chosen.get("model")
                        if not model and isinstance(chosen.get("models"), dict):
                            model = chosen["models"].get("main")
                        
                        if model:
                            judge_model = str(model)
                            
                        # If provider is openai-compatible, we might need to be careful with base_url
                        if chosen.get("provider") == "openai-compatible" and not judge_base_url:
                             pass # Warn?
        except Exception as e:
            print(f"Warning: Failed to parse project LLM config for 'fast' role: {e}")

    # Fallbacks
    if not judge_api_key:
        judge_api_key = env_vars.get("OPENAI_API_KEY")
    if not judge_base_url:
        judge_base_url = env_vars.get("OPENAI_BASE_URL")
    if not judge_model:
        judge_model = "gpt-4o-mini"

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

@dataclass
class FakeCanvas:
    objects: List[Dict[str, Any]] = field(default_factory=list)

    def apply_commands(self, commands: List[str]) -> List[str]:
        # Minimal implementation: just acknowledge creation
        created = []
        for cmd in commands:
            # simple parsing: "Name = Type(...)"
            if "=" in cmd:
                name = cmd.split("=", 1)[0].strip()
                self.objects.append({"name": name, "definition": cmd})
                created.append(name)
        return created

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
    if not config.judge_api_key:
        return {"pass": False, "reason": "Judge API key not configured (EVAL_JUDGE_API_KEY)"}

    url = f"{config.judge_base_url or 'https://api.openai.com/v1'}/chat/completions"
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
                elif ev["event"] == "final": # Assuming v2 protocol emits 'final' event with text
                    # Depending on protocol, might be in 'final' or aggregated from deltas.
                    # V2 spec says final event has { "output": ... }
                    if isinstance(ev["data"], dict) and "output" in ev["data"]:
                         # Check if output is string or object with content
                         out = ev["data"]["output"]
                         if isinstance(out, str): trace["final_text"] = out
                         elif isinstance(out, dict): trace["final_text"] = out.get("content", "")
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
                canvas.apply_commands(cmds)
                output = {"results": [{"ok": True} for _ in cmds]}
            elif tool_name == "get_canvas_state":
                output = {"objects": canvas.objects}
                
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
