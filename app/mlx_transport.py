# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Optional local MLX server adapter; existing Ollama traffic stays unchanged."""
from __future__ import annotations

import copy
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx

MODEL = "ministral-3:8b-mlx"
SOURCE = "mlx-community/Ministral-3-8B-Instruct-2512-4bit"
QWEN_MODEL = "qwen3.8:27b-mlx-q3"


def model_specs():
    specs = {MODEL: {"source": os.getenv("MINI_LLM_MLX_MODEL") or SOURCE,
        "family": "mistral3", "parameters": "8.9B", "quant": "MLX INT4", "context": 8192,
        "size": 5630000000, "capabilities": ["completion", "vision", "tools"]}}
    source = os.getenv("MINI_LLM_MLX_QWEN_MODEL", "").strip()
    if source:
        try:
            root = Path(source)
            progress = json.loads((root / "conversion-progress.json").read_text())
            checks = json.loads((root / "smoke-test.json").read_text())
            stress = json.loads((root / "context-stress-test.json").read_text())
            context_ok = (len(stress) >= 3 and all(row.get("passed") and
                row.get("usage", {}).get("prompt_tokens", 0) >= 3000 for row in stress)
                and any(row.get("task") == "html" for row in stress))
            if progress.get("complete") and context_ok and len(checks) >= 3 and all(row.get("passed") for row in checks):
                specs[QWEN_MODEL] = {"source": source, "family": "qwen3_5", "parameters": "27B",
                    "quant": "MLX INT3", "context": 4096, "size": progress["output_bytes"],
                    "capabilities": ["completion", "tools", "thinking"]}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return specs


def completion_payload(payload: dict[str, Any]) -> dict[str, Any]:
    messages = copy.deepcopy(payload.get("messages", []))
    for message in messages:
        images = message.pop("images", [])
        if images:
            message["content"] = [
                {"type": "text", "text": message.get("content", "")},
                *({"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}}
                  for image in images),
            ]
        for call in message.get("tool_calls") or []:
            args = call.get("function", {}).get("arguments")
            if isinstance(args, dict):
                call["function"]["arguments"] = json.dumps(args)
    options = payload.get("options", {})
    spec = model_specs().get(payload.get("model", MODEL), model_specs()[MODEL])
    result = {"model": spec["source"],
              "messages": messages, "stream": bool(payload.get("stream"))}
    if payload.get("model") == QWEN_MODEL:
        result["enable_thinking"] = bool(payload.get("think", False))
    for key in ("temperature", "top_p", "top_k", "seed", "stop"):
        if key in options:
            result[key] = options[key]
    limit = int(options.get("num_predict", 2048))
    result["max_tokens"] = limit if limit > 0 else 4096
    if payload.get("tools"):
        result["tools"] = payload["tools"]
    schema = payload.get("format")
    if isinstance(schema, dict):
        result["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "result", "schema": schema}}
    elif schema == "json":
        result["response_format"] = {"type": "json_object"}
    if result["stream"]:
        result["stream_options"] = {"include_usage": True}
    return result


def ollama_chunk(data: dict[str, Any], *, streaming: bool, model: str = MODEL) -> dict[str, Any]:
    choices = data.get("choices") or []
    choice = choices[0] if choices else {}
    message = copy.deepcopy(choice.get("delta" if streaming else "message") or {})
    message.setdefault("role", "assistant")
    message["content"] = message.get("content") or ""
    if message.get("reasoning_content"):
        message["thinking"] = message.pop("reasoning_content")
    for call in message.get("tool_calls") or []:
        fn = call.get("function", {})
        if isinstance(fn.get("arguments"), str):
            try:
                fn["arguments"] = json.loads(fn["arguments"])
            except json.JSONDecodeError:
                pass
    done = not streaming or bool(data.get("usage"))
    out = {"model": model, "message": message, "done": done}
    if done:
        usage = data.get("usage") or {}
        timing = data.get("timings") or {}
        out.update(done_reason="length" if choice.get("finish_reason") == "length" else "stop",
                   eval_count=usage.get("completion_tokens", 0),
                   prompt_eval_count=usage.get("prompt_tokens", 0),
                   eval_duration=int(timing.get("predicted_ms", 0) * 1e6),
                   prompt_eval_duration=int(timing.get("prompt_ms", 0) * 1e6))
    return out


class MLXStream(httpx.AsyncByteStream):
    def __init__(self, response: httpx.Response, release=None, model=MODEL):
        self.response = response
        self.release = release
        self.model = model

    async def __aiter__(self):
        done = False
        tool_parts: dict[int, dict[str, Any]] = {}
        finish = "stop"
        try:
            async for line in self.response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                data = json.loads(raw)
                if data.get("error"):
                    yield (json.dumps({"error": data["error"]}) + "\n").encode()
                    return
                for choice in data.get("choices", []):
                    finish = choice.get("finish_reason") or finish
                    for call in choice.get("delta", {}).pop("tool_calls", None) or []:
                        part = tool_parts.setdefault(call.get("index", 0), {"function": {"name": "", "arguments": ""}})
                        fn = call.get("function", {})
                        part["function"]["name"] += fn.get("name") or ""
                        part["function"]["arguments"] += fn.get("arguments") or ""
                chunk = ollama_chunk(data, streaming=True, model=self.model)
                if chunk["done"]:
                    chunk["done_reason"] = "length" if finish == "length" else "stop"
                    if tool_parts:
                        chunk["message"]["tool_calls"] = list(tool_parts.values())
                        for call in chunk["message"]["tool_calls"]:
                            call["function"]["arguments"] = json.loads(call["function"]["arguments"] or "{}")
                    done = True
                yield (json.dumps(chunk) + "\n").encode()
            if not done:
                # A truncated HTTP/SSE stream must never become a successful empty answer.
                yield (json.dumps({"error": "MLX-Verbindung vor dem Abschluss unterbrochen. Bitte wiederholen."}) + "\n").encode()
        finally:
            await self.aclose()

    async def aclose(self):
        try:
            await self.response.aclose()
        finally:
            if self.release is not None:
                callback, self.release = self.release, None
                callback()


class MLXTransport(httpx.AsyncBaseTransport):
    def __init__(self, ollama_url: str, mlx_url: str, transport=None):
        self.ollama = ollama_url.rstrip("/")
        self.mlx = mlx_url.rstrip("/")
        self.inner = transport or httpx.AsyncHTTPTransport()
        self.active = 0
        self.loaded = False
        self.switch_lock = asyncio.Lock()

    def release(self):
        self.active -= 1

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not str(request.url).startswith(self.ollama + "/api/"):
            return await self.inner.handle_async_request(request)
        path = request.url.path
        payload = json.loads(await request.aread()) if request.method == "POST" else {}
        specs = model_specs()
        selected = payload.get("model")
        spec = specs.get(selected)
        if spec and path == "/api/show":
            return httpx.Response(200, json={"capabilities": spec["capabilities"],
                "details": {"format": "safetensors", "family": spec["family"], "parameter_size": spec["parameters"], "quantization_level": spec["quant"]},
                "model_info": {spec["family"] + ".context_length": spec["context"]}})
        if spec and path == "/api/chat":
            if selected == QWEN_MODEL and any(message.get("images") for message in payload.get("messages", [])):
                return httpx.Response(400, json={"error": "Qwen 27B Q3 läuft auf diesem 16-GB-Mac im Textmodus. Für Bilder bitte Ministral oder ein anderes Bildmodell auswählen."})
            async with self.switch_lock:
                self.active += 1
                self.loaded = True
            try:
                upstream = httpx.Request("POST", self.mlx + "/v1/chat/completions",
                                        json=completion_payload(payload), extensions=request.extensions)
                response = await self.inner.handle_async_request(upstream)
            except BaseException:
                self.release()
                raise
            if response.status_code >= 400:
                try:
                    await response.aread()
                finally:
                    self.release()
                return response
            if payload.get("stream"):
                return httpx.Response(200, headers={"content-type": "application/x-ndjson"}, stream=MLXStream(response, self.release, selected))
            try:
                await response.aread()
                return httpx.Response(200, json=ollama_chunk(response.json(), streaming=False, model=selected))
            finally:
                self.release()
        if path == "/api/chat" and self.loaded:
            # Switching away releases idle MLX weights on 16-GB Macs. Never
            # unload while an MLX response is still generating or streaming.
            async with self.switch_lock:
                if self.active == 0:
                    try:
                        unloaded = await self.inner.handle_async_request(httpx.Request("POST", self.mlx + "/unload",
                            extensions={"timeout": {"connect": 1, "read": 10, "write": 1, "pool": 1}}))
                        await unloaded.aread()
                        if unloaded.status_code == 200:
                            self.loaded = False
                    except httpx.HTTPError:
                        pass
        response = await self.inner.handle_async_request(request)
        if path == "/api/tags" and response.status_code == 200:
            await response.aread()
            try:
                health = await self.inner.handle_async_request(httpx.Request("GET", self.mlx + "/health",
                    extensions={"timeout": {"connect": 0.5, "read": 0.5, "write": 0.5, "pool": 0.5}}))
                await health.aread()
                if health.status_code == 200:
                    data = response.json()
                    for name, entry in specs.items():
                        data.setdefault("models", []).append({"name": name, "model": name, "size": entry["size"],
                            "details": {"format": "safetensors", "family": entry["family"], "parameter_size": entry["parameters"], "quantization_level": entry["quant"]}})
                    return httpx.Response(200, json=data)
            except httpx.HTTPError:
                pass
        return response

    async def aclose(self):
        await self.inner.aclose()


def optional_transport(ollama_url: str):
    url = os.getenv("MINI_LLM_MLX_URL", "").strip()
    return MLXTransport(ollama_url, url) if url else None
