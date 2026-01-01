import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, Response
from langgraph.types import Command
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .debug_trace import trace_exception, trace_http, trace_sse
from .llm_decider import load_llm_config
from .protocol_v2 import PROTOCOL_VERSION, ToolResumePayload, get_protocol_schema_v2
from .runtime_graph import graph_local as graph


@dataclass
class ThreadState:
    created_at_ms: int
    last_user_text: Optional[str] = None


@dataclass
class PendingTool:
    tool_name: str
    tool_call_id: str
    input: Any


@dataclass
class RunState:
    created_at_ms: int
    thread_id: str
    user_text: str
    ui_debug: bool = False
    pending_tool: Optional[PendingTool] = None
    tool_calls_used: int = 0
    tool_calls_limit: int = 12
    model_calls_used: int = 0
    model_calls_limit: int = 6
    completed_tool_call_ids: set[str] = field(default_factory=set)


class RunInput(BaseModel):
    user_text: str = Field(..., min_length=1)


class UIContext(BaseModel):
    locale: str = "zh-CN"
    debug: bool = False
    plan_mode: bool = True


class RunStreamRequest(BaseModel):
    input: RunInput
    ui_context: UIContext = Field(default_factory=UIContext)


class ResumeCommand(BaseModel):
    resume: ToolResumePayload


class ResumeRequest(BaseModel):
    command: ResumeCommand


app = FastAPI(title="GeoGebra AI Drawer v2 API", version="0.0.0")

_threads: Dict[str, ThreadState] = {}
_runs: Dict[str, RunState] = {}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _to_jsonable(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


def _sse(event: str, data: Any) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/schema/v2")
def get_schema_v2() -> dict:
    return get_protocol_schema_v2()


@app.get("/api/graph/v2/mermaid", response_class=PlainTextResponse)
def get_langgraph_mermaid() -> str:
    return graph.get_graph().draw_mermaid()


@app.get("/api/graph/v2/mermaid.png")
def get_langgraph_mermaid_png() -> Response:
    png_bytes = graph.get_graph().draw_mermaid_png()
    return Response(content=png_bytes, media_type="image/png")


@app.post("/api/threads")
def create_thread() -> dict:
    thread_id = str(uuid.uuid4())
    _threads[thread_id] = ThreadState(created_at_ms=_now_ms())
    return {"thread_id": thread_id}


@app.get("/api/threads/{thread_id}/state")
def get_thread_state(thread_id: str) -> dict:
    state = _threads.get(thread_id)
    if state is None:
        raise HTTPException(status_code=404, detail="thread not found")
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    snap_cfg = snapshot.config.get("configurable") if snapshot.config else None
    return {
        "thread_id": thread_id,
        "created_at_ms": state.created_at_ms,
        "last_user_text": state.last_user_text,
        "graph": {
            "values": _to_jsonable(snapshot.values),
            "next": list(snapshot.next),
            "checkpoint_id": snap_cfg.get("checkpoint_id") if isinstance(snap_cfg, dict) else None,
            "checkpoint_ns": snap_cfg.get("checkpoint_ns") if isinstance(snap_cfg, dict) else None,
        },
    }


@app.get("/api/threads/{thread_id}/state/history")
def get_thread_state_history(thread_id: str, limit: int = 20) -> dict:
    state = _threads.get(thread_id)
    if state is None:
        raise HTTPException(status_code=404, detail="thread not found")

    safe_limit = max(1, min(int(limit), 100))
    config = {"configurable": {"thread_id": thread_id}}
    items = []
    for snap in graph.get_state_history(config, limit=safe_limit):
        snap_cfg = snap.config.get("configurable") if snap.config else None
        items.append(
            {
                "values": _to_jsonable(snap.values),
                "next": list(snap.next),
                "checkpoint_id": snap_cfg.get("checkpoint_id") if isinstance(snap_cfg, dict) else None,
                "checkpoint_ns": snap_cfg.get("checkpoint_ns") if isinstance(snap_cfg, dict) else None,
                "created_at": snap.created_at,
                "metadata": _to_jsonable(snap.metadata),
            }
        )

    return {
        "thread_id": thread_id,
        "created_at_ms": state.created_at_ms,
        "last_user_text": state.last_user_text,
        "history": items,
    }


@app.post("/api/threads/{thread_id}/runs/stream")
async def run_stream(thread_id: str, body: RunStreamRequest) -> EventSourceResponse:
    state = _threads.get(thread_id)
    if state is None:
        raise HTTPException(status_code=404, detail="thread not found")

    run_id = str(uuid.uuid4())
    state.last_user_text = body.input.user_text
    _runs[run_id] = RunState(
        created_at_ms=_now_ms(),
        thread_id=thread_id,
        user_text=body.input.user_text,
        ui_debug=body.ui_context.debug,
    )

    async def event_gen():
        run = _runs.get(run_id)
        ui_debug = bool(run.ui_debug) if run is not None else False

        trace_http(
            run_id=run_id,
            ui_debug=ui_debug,
            name="runs_stream.request",
            data={
                "thread_id": thread_id,
                "user_text": body.input.user_text,
                "ui_context": body.ui_context.model_dump(),
            },
        )

        try:
            llm_cfg = load_llm_config()
        except Exception as e:
            trace_exception(run_id=run_id, ui_debug=ui_debug, where="load_llm_config(runs_stream)", exc=e)
            llm_cfg = None

        llm_enabled = llm_cfg is not None
        run_start = {
            "run_id": run_id,
            "thread_id": thread_id,
            "protocol_version": PROTOCOL_VERSION,
            "llm_enabled": llm_enabled,
            "llm_model": llm_cfg.model if llm_cfg else None,
            "llm_base_url": llm_cfg.base_url if llm_cfg else None,
        }
        trace_sse(run_id=run_id, ui_debug=ui_debug, event="run_start", data=run_start)
        yield _sse("run_start", run_start)

        if run is None:
            final_payload = {
                "answer": {
                    "explanation": "运行状态丢失，无法开始。",
                    "overlay_text": None,
                }
            }
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="final", data=final_payload)
            yield _sse("final", final_payload)
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="run_end", data={})
            yield _sse("run_end", {})
            return

        budget_payload = {
            "model_calls_used": run.model_calls_used,
            "model_calls_limit": run.model_calls_limit,
            "tool_calls_used": run.tool_calls_used,
            "tool_calls_limit": run.tool_calls_limit,
        }
        trace_sse(run_id=run_id, ui_debug=ui_debug, event="budget", data=budget_payload)
        yield _sse("budget", budget_payload)

        trace_sse(run_id=run_id, ui_debug=ui_debug, event="node_start", data={"name": "ingest_node"})
        yield _sse("node_start", {"name": "ingest_node"})

        await asyncio.sleep(0.05)
        token_payload = {"text_delta": "（v2 llm）准备开始…" if llm_enabled else "（v2 stub）准备开始…"}
        trace_sse(run_id=run_id, ui_debug=ui_debug, event="token", data=token_payload)
        yield _sse("token", token_payload)
        await asyncio.sleep(0.05)

        config = {"configurable": {"thread_id": thread_id}}
        input_state = {
            "run_id": run_id,
            "ui_debug": ui_debug,
            "plan_mode": bool(body.ui_context.plan_mode),
            "user_text": body.input.user_text,
            "tool_calls_used": run.tool_calls_used,
            "tool_calls_limit": run.tool_calls_limit,
            "model_calls_used": run.model_calls_used,
            "model_calls_limit": run.model_calls_limit,
        }
        interrupt_value: Optional[dict] = None
        answer_text: Optional[str] = None
        try:
            interrupts_seen = False
            plan_sent = False
            for chunk in graph.stream(input_state, config):
                interrupts = chunk.get("__interrupt__")
                if interrupts and not interrupts_seen:
                    # IMPORTANT: do not break early. Let the LangGraph stream generator
                    # finish gracefully so GeneratorExit is not reported as an error in tracing.
                    interrupt_value = interrupts[0].value
                    interrupts_seen = True
                    continue
                if interrupts_seen:
                    continue
                for node_name in ("ingest_node", "plan_node", "act_node", "finalize_node"):
                    node_out = chunk.get(node_name)
                    if not isinstance(node_out, dict):
                        continue

                    if node_name == "plan_node" and not plan_sent:
                        plan = node_out.get("plan")
                        if isinstance(plan, list) and plan:
                            plan_payload = {"plan": plan}
                            trace_sse(run_id=run_id, ui_debug=ui_debug, event="plan_update", data=plan_payload)
                            yield _sse("plan_update", plan_payload)
                            plan_sent = True

                    if "model_calls_used" in node_out:
                        try:
                            run.model_calls_used = int(node_out["model_calls_used"])
                        except Exception:
                            pass
                    if "model_calls_limit" in node_out:
                        try:
                            run.model_calls_limit = int(node_out["model_calls_limit"])
                        except Exception:
                            pass
                    if isinstance(node_out.get("answer_text"), str):
                        answer_text = node_out["answer_text"]
        except Exception as e:
            trace_exception(run_id=run_id, ui_debug=ui_debug, where="graph.stream(runs_stream)", exc=e)
            final_payload = {
                "answer": {
                    "explanation": "服务端运行时出错了（已记录日志）。请把该条消息的 Debug events 发给我，我来修复。",
                    "overlay_text": None,
                }
            }
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="final", data=final_payload)
            yield _sse("final", final_payload)
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="run_end", data={})
            yield _sse("run_end", {})
            _runs.pop(run_id, None)
            return

        if interrupt_value is None:
            final_payload = {
                "answer": {
                    "explanation": answer_text or "运行未按预期发出前端工具请求（interrupt）。",
                    "overlay_text": None,
                }
            }
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="final", data=final_payload)
            yield _sse("final", final_payload)
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="run_end", data={})
            yield _sse("run_end", {})
            _runs.pop(run_id, None)
            return

        run.pending_tool = PendingTool(
            tool_name=interrupt_value["tool_name"],
            tool_call_id=interrupt_value["tool_call_id"],
            input=interrupt_value["input"],
        )
        tool_start_payload = {
            "tool_name": interrupt_value["tool_name"],
            "tool_call_id": interrupt_value["tool_call_id"],
            "input": interrupt_value["input"],
        }
        trace_sse(run_id=run_id, ui_debug=ui_debug, event="tool_start", data=tool_start_payload)
        yield _sse("tool_start", tool_start_payload)
        trace_sse(run_id=run_id, ui_debug=ui_debug, event="interrupt", data=interrupt_value)
        yield _sse("interrupt", interrupt_value)
        # IMPORTANT: do not emit run_end here. The run is paused until /resume.

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return EventSourceResponse(event_gen(), headers=headers)


@app.post("/api/threads/{thread_id}/runs/{run_id}/resume")
async def resume_run(thread_id: str, run_id: str, body: ResumeRequest) -> EventSourceResponse:
    run = _runs.get(run_id)
    if run is None or run.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="run not found or not resumable")

    ui_debug = bool(run.ui_debug)
    trace_http(
        run_id=run_id,
        ui_debug=ui_debug,
        name="resume.request",
        data={"thread_id": thread_id, "resume": body.command.resume.model_dump()},
    )

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }

    pending = run.pending_tool
    if pending is None:
        raise HTTPException(status_code=409, detail="run has no pending tool; cannot resume")

    resume = body.command.resume
    if resume.tool_call_id in run.completed_tool_call_ids and resume.tool_call_id != pending.tool_call_id:

        async def dup_event_gen():
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="node_start", data={"name": "resume_duplicate"})
            yield _sse("node_start", {"name": "resume_duplicate"})

            token_payload = {"text_delta": "检测到重复的 /resume，本次已忽略；仍在等待最新的工具请求。"}
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="token", data=token_payload)
            yield _sse("token", token_payload)

            tool_start_payload = {
                "tool_name": pending.tool_name,
                "tool_call_id": pending.tool_call_id,
                "input": pending.input,
            }
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="tool_start", data=tool_start_payload)
            yield _sse("tool_start", tool_start_payload)

            interrupt_payload = {
                "kind": "frontend_tool",
                "tool_name": pending.tool_name,
                "tool_call_id": pending.tool_call_id,
                "input": pending.input,
            }
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="interrupt", data=interrupt_payload)
            yield _sse("interrupt", interrupt_payload)

        return EventSourceResponse(dup_event_gen(), headers=headers)

    if resume.tool_call_id != pending.tool_call_id or resume.tool_name != pending.tool_name:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "tool_call_id/tool_name mismatch",
                "expected": {"tool_call_id": pending.tool_call_id, "tool_name": pending.tool_name},
                "got": {"tool_call_id": resume.tool_call_id, "tool_name": resume.tool_name},
            },
        )

    run.completed_tool_call_ids.add(resume.tool_call_id)
    run.tool_calls_used += 1
    run.pending_tool = None

    async def event_gen():
        try:
            llm_enabled = load_llm_config() is not None
        except Exception as e:
            trace_exception(run_id=run_id, ui_debug=ui_debug, where="load_llm_config(resume)", exc=e)
            llm_enabled = False

        trace_sse(run_id=run_id, ui_debug=ui_debug, event="node_start", data={"name": "apply_tool_result"})
        yield _sse("node_start", {"name": "apply_tool_result"})

        tool_end_payload = {
            "tool_name": pending.tool_name,
            "tool_call_id": pending.tool_call_id,
            "output": resume.output,
            "ok": resume.ok,
            "error": resume.error,
        }
        trace_sse(run_id=run_id, ui_debug=ui_debug, event="tool_end", data=tool_end_payload)
        yield _sse("tool_end", tool_end_payload)

        budget_payload = {
            "model_calls_used": run.model_calls_used,
            "model_calls_limit": run.model_calls_limit,
            "tool_calls_used": run.tool_calls_used,
            "tool_calls_limit": run.tool_calls_limit,
        }
        trace_sse(run_id=run_id, ui_debug=ui_debug, event="budget", data=budget_payload)
        yield _sse("budget", budget_payload)

        token_payload = {"text_delta": "（v2 llm）已收到工具结果，继续…" if llm_enabled else "（v2 stub）已收到工具结果，继续…"}
        trace_sse(run_id=run_id, ui_debug=ui_debug, event="token", data=token_payload)
        yield _sse("token", token_payload)
        await asyncio.sleep(0.05)

        config = {"configurable": {"thread_id": thread_id}}
        interrupt_value: Optional[dict] = None
        answer_text: Optional[str] = None
        try:
            interrupts_seen = False
            for chunk in graph.stream(Command(resume=resume.model_dump()), config):
                interrupts = chunk.get("__interrupt__")
                if interrupts and not interrupts_seen:
                    # IMPORTANT: do not break early. Let the LangGraph stream generator
                    # finish gracefully so GeneratorExit is not reported as an error in tracing.
                    interrupt_value = interrupts[0].value
                    interrupts_seen = True
                    continue
                if interrupts_seen:
                    continue

                for node_name in ("act_node", "finalize_node"):
                    node_out = chunk.get(node_name)
                    if not isinstance(node_out, dict):
                        continue
                    if "model_calls_used" in node_out:
                        try:
                            run.model_calls_used = int(node_out["model_calls_used"])
                        except Exception:
                            pass
                    if "model_calls_limit" in node_out:
                        try:
                            run.model_calls_limit = int(node_out["model_calls_limit"])
                        except Exception:
                            pass
                    if isinstance(node_out.get("answer_text"), str):
                        answer_text = node_out["answer_text"]
        except Exception as e:
            trace_exception(run_id=run_id, ui_debug=ui_debug, where="graph.stream(resume)", exc=e)
            final_payload = {
                "answer": {
                    "explanation": "服务端在 resume 过程中出错了（已记录日志）。请把该条消息的 Debug events 发给我，我来修复。",
                    "overlay_text": None,
                }
            }
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="final", data=final_payload)
            yield _sse("final", final_payload)
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="run_end", data={})
            yield _sse("run_end", {})
            _runs.pop(run_id, None)
            return

        if interrupt_value is not None:
            run.pending_tool = PendingTool(
                tool_name=interrupt_value["tool_name"],
                tool_call_id=interrupt_value["tool_call_id"],
                input=interrupt_value["input"],
            )
            tool_start_payload = {
                "tool_name": interrupt_value["tool_name"],
                "tool_call_id": interrupt_value["tool_call_id"],
                "input": interrupt_value["input"],
            }
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="tool_start", data=tool_start_payload)
            yield _sse("tool_start", tool_start_payload)
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="interrupt", data=interrupt_value)
            yield _sse("interrupt", interrupt_value)
            trace_sse(run_id=run_id, ui_debug=ui_debug, event="node_end", data={"name": "apply_tool_result"})
            yield _sse("node_end", {"name": "apply_tool_result"})
            return

        final_payload = {
            "answer": {
                "explanation": answer_text or f"我已经收到：{run.user_text}",
                "overlay_text": None,
            }
        }
        trace_sse(run_id=run_id, ui_debug=ui_debug, event="final", data=final_payload)
        yield _sse("final", final_payload)
        trace_sse(run_id=run_id, ui_debug=ui_debug, event="node_end", data={"name": "apply_tool_result"})
        yield _sse("node_end", {"name": "apply_tool_result"})
        trace_sse(run_id=run_id, ui_debug=ui_debug, event="run_end", data={})
        yield _sse("run_end", {})

        _runs.pop(run_id, None)

    return EventSourceResponse(event_gen(), headers=headers)
