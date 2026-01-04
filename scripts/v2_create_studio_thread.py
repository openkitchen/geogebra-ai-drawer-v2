#!/usr/bin/env python3
"""
Create a LangGraph Studio thread from a FastAPI thread.

This script extracts thread information from FastAPI and creates a corresponding
thread in Studio (or provides instructions to do so).

Usage:
    python3 scripts/v2_create_studio_thread.py <fastapi_thread_id>
    python3 scripts/v2_create_studio_thread.py <fastapi_thread_id> --studio-url http://127.0.0.1:2024
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests


def get_fastapi_thread(thread_id: str, base_url: str = "http://127.0.0.1:3002") -> dict[str, Any]:
    """Get thread information from FastAPI."""
    try:
        response = requests.get(f"{base_url}/api/threads/{thread_id}/state", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching thread from FastAPI: {e}", file=sys.stderr)
        sys.exit(1)


def get_fastapi_thread_history(thread_id: str, base_url: str = "http://127.0.0.1:3002", limit: int = 1) -> dict[str, Any]:
    """Get thread history from FastAPI."""
    try:
        response = requests.get(
            f"{base_url}/api/threads/{thread_id}/state/history",
            params={"limit": limit},
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching thread history from FastAPI: {e}", file=sys.stderr)
        sys.exit(1)


def extract_user_input(thread_data: dict[str, Any]) -> str:
    """Extract user input from thread data."""
    # Try to get from last_user_text
    if thread_data.get("last_user_text"):
        return thread_data["last_user_text"]
    
    # Try to get from graph state
    graph_values = thread_data.get("graph", {}).get("values", {})
    if graph_values.get("user_text"):
        return graph_values["user_text"]
    
    # Try to get from history
    history = thread_data.get("history", [])
    if history:
        last_state = history[-1].get("values", {})
        if last_state.get("user_text"):
            return last_state["user_text"]
    
    return ""


def create_studio_thread_via_api(user_text: str, studio_url: str = "http://127.0.0.1:2024") -> str | None:
    """Try to create a thread in Studio via API (if supported)."""
    # LangGraph Studio API structure may vary
    # Try common endpoints
    endpoints = [
        "/threads",
        "/api/threads",
        "/threads/create",
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.post(
                f"{studio_url}{endpoint}",
                json={"input": {"user_text": user_text}},
                timeout=5
            )
            if response.status_code in (200, 201):
                data = response.json()
                return data.get("thread_id") or data.get("id")
        except requests.exceptions.RequestException:
            continue
    
    return None


def generate_studio_instructions(thread_id: str, user_text: str, thread_data: dict[str, Any]) -> str:
    """Generate instructions for manually creating a thread in Studio."""
    instructions = f"""
# Instructions to create thread in LangGraph Studio

## FastAPI Thread Information
- Thread ID: {thread_id}
- User Text: {user_text}
- Created At: {thread_data.get('created_at_ms', 'N/A')}

## Steps to create in Studio:

1. Open LangGraph Studio: https://smith.langchain.com/o/.../studio

2. Click "New Thread" or "Create Thread"

3. Enter the following input:
   ```
   {json.dumps({"user_text": user_text}, indent=2, ensure_ascii=False)}
   ```

4. Click "Run" to execute

## Alternative: Use Studio API directly

If Studio API is accessible, you can create the thread programmatically:

```bash
curl -X POST http://127.0.0.1:2024/threads \\
  -H "Content-Type: application/json" \\
  -d '{json.dumps({"input": {"user_text": user_text}}, indent=2, ensure_ascii=False)}'
```

## Thread State Summary

Graph State:
{json.dumps(thread_data.get("graph", {}), indent=2, ensure_ascii=False)}
"""
    return instructions


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Create a LangGraph Studio thread from a FastAPI thread"
    )
    parser.add_argument("thread_id", help="FastAPI thread ID")
    parser.add_argument(
        "--fastapi-url",
        default="http://127.0.0.1:3002",
        help="FastAPI base URL (default: http://127.0.0.1:3002)",
    )
    parser.add_argument(
        "--studio-url",
        default="http://127.0.0.1:2024",
        help="Studio base URL (default: http://127.0.0.1:2024)",
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--auto-create",
        action="store_true",
        help="Try to automatically create thread in Studio via API",
    )
    
    args = parser.parse_args(argv)
    
    # Get thread data from FastAPI
    print(f"Fetching thread {args.thread_id} from FastAPI...", file=sys.stderr)
    thread_data = get_fastapi_thread(args.thread_id, args.fastapi_url)
    
    # Extract user input
    user_text = extract_user_input(thread_data)
    if not user_text:
        print("Warning: Could not extract user_text from thread", file=sys.stderr)
        user_text = "（无法提取用户输入）"
    
    # Try to create in Studio automatically
    studio_thread_id = None
    if args.auto_create:
        print(f"Attempting to create thread in Studio...", file=sys.stderr)
        studio_thread_id = create_studio_thread_via_api(user_text, args.studio_url)
        if studio_thread_id:
            print(f"✅ Created Studio thread: {studio_thread_id}", file=sys.stderr)
        else:
            print("⚠️  Could not create thread via API, generating instructions...", file=sys.stderr)
    
    # Generate instructions
    instructions = generate_studio_instructions(args.thread_id, user_text, thread_data)
    
    if studio_thread_id:
        instructions = f"✅ Studio Thread ID: {studio_thread_id}\n\n{instructions}"
    
    # Output
    if args.output:
        Path(args.output).write_text(instructions, encoding="utf-8")
        print(f"Instructions written to: {args.output}", file=sys.stderr)
    else:
        print(instructions)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

