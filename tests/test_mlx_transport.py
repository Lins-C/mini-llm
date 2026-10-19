# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from app.mlx_transport import MODEL, QWEN_MODEL, MLXTransport, completion_payload, model_specs


class MLXAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_ollama_is_unchanged_and_cloud_does_not_go_to_mlx(self):
        seen = []
        def handler(req):
            seen.append(str(req.url))
            return httpx.Response(200, json={"message": {"content": "original"}})
        async with httpx.AsyncClient(transport=MLXTransport("http://ollama", "http://mlx", httpx.MockTransport(handler))) as client:
            result = await client.post("http://ollama/api/chat", json={"model": "kimi-k3:cloud"})
        self.assertEqual(seen, ["http://ollama/api/chat"])
        self.assertEqual(result.json()["message"]["content"], "original")

    async def test_completion_keeps_tools_schema_images_and_statistics(self):
        def handler(req):
            data = json.loads(req.content)
            self.assertEqual(str(req.url), "http://mlx/v1/chat/completions")
            self.assertEqual(data["response_format"]["json_schema"]["schema"], {"type": "object"})
            self.assertEqual(data["messages"][0]["content"][1]["image_url"]["url"], "data:image/png;base64,aGVsbG8=")
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}", "tool_calls": None}}],
                "usage": {"completion_tokens": 100, "prompt_tokens": 15},
                "timings": {"predicted_ms": 2000}})
        async with httpx.AsyncClient(transport=MLXTransport("http://ollama", "http://mlx", httpx.MockTransport(handler))) as client:
            result = await client.post("http://ollama/api/chat", json={"model": MODEL, "stream": False,
                "messages": [{"role": "user", "content": "Bild", "images": ["aGVsbG8="]}], "format": {"type": "object"}})
        self.assertEqual(result.json()["eval_duration"], 2_000_000_000)
        self.assertEqual(result.json()["eval_count"], 100)

    async def test_stream_accumulates_tool_arguments_and_length(self):
        events = [
            {"choices": [{"delta": {"content": "Hallo ü", "tool_calls": [{"index": 0, "function": {"name": "read", "arguments": '{"path":'}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"a"}'}}]}, "finish_reason": "length"}]},
            {"usage": {"completion_tokens": 4}, "choices": [], "timings": {"predicted_ms": 100}},
        ]
        def handler(req):
            return httpx.Response(200, content="".join("data: " + json.dumps(e) + "\n\n" for e in events) + "data: [DONE]\n\n")
        async with httpx.AsyncClient(transport=MLXTransport("http://ollama", "http://mlx", httpx.MockTransport(handler))) as client:
            result = await client.post("http://ollama/api/chat", json={"model": MODEL, "stream": True})
        chunks = [json.loads(line) for line in result.text.splitlines()]
        self.assertEqual(chunks[0]["message"]["content"], "Hallo ü")
        self.assertEqual(chunks[-1]["done_reason"], "length")
        self.assertEqual(chunks[-1]["message"]["tool_calls"][0]["function"]["arguments"], {"path": "a"})

    async def test_lost_stream_reports_error(self):
        def handler(req):
            return httpx.Response(200, content='data: {"choices":[{"delta":{"content":"part"}}]}\n\ndata: [DONE]\n\n')
        async with httpx.AsyncClient(transport=MLXTransport("http://ollama", "http://mlx", httpx.MockTransport(handler))) as client:
            result = await client.post("http://ollama/api/chat", json={"model": MODEL, "stream": True})
        self.assertIn("error", json.loads(result.text.splitlines()[-1]))

    async def test_unavailable_mlx_does_not_remove_ollama_models(self):
        def handler(req):
            if req.url.host == "mlx":
                raise httpx.ConnectError("offline", request=req)
            return httpx.Response(200, json={"models": [{"name": "existing"}]})
        async with httpx.AsyncClient(transport=MLXTransport("http://ollama", "http://mlx", httpx.MockTransport(handler))) as client:
            result = await client.get("http://ollama/api/tags")
        self.assertEqual(result.json(), {"models": [{"name": "existing"}]})

    async def test_switch_only_unloads_idle_mlx(self):
        seen = []
        def handler(req):
            seen.append(req.url.path)
            return httpx.Response(200, json={})
        transport = MLXTransport("http://ollama", "http://mlx", httpx.MockTransport(handler))
        transport.loaded, transport.active = True, 1
        async with httpx.AsyncClient(transport=transport) as client:
            await client.post("http://ollama/api/chat", json={"model": "other"})
            self.assertNotIn("/unload", seen)
            transport.active = 0
            await client.post("http://ollama/api/chat", json={"model": "other"})
        self.assertEqual(seen, ["/api/chat", "/unload", "/api/chat"])
        self.assertFalse(transport.loaded)

    def test_payload_does_not_change_original_messages(self):
        original = {"messages": [{"role": "user", "content": "test", "images": ["image"]}]}
        completion_payload(original)
        self.assertEqual(original["messages"][0]["images"], ["image"])

    def test_mlx_context_budget_matches_runtime(self):
        from app.kontext import kontext_tokens, kontext_optionen
        with patch("app.kontext.lokales_kontextfenster", return_value=32768):
            self.assertEqual(kontext_tokens(MODEL), 8192)
            self.assertEqual(kontext_optionen(MODEL), {"num_ctx": 8192})
            self.assertEqual(kontext_tokens("ministral-3:8b"), 32768)
            self.assertEqual(kontext_tokens(QWEN_MODEL), 4096)

    async def test_qwen_only_enabled_after_successful_checks_and_routed_separately(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"MINI_LLM_MLX_QWEN_MODEL": directory}):
            root = Path(directory)
            (root / "conversion-progress.json").write_text(json.dumps({"complete": False, "output_bytes": 123}))
            (root / "smoke-test.json").write_text(json.dumps([{"passed": True}] * 3))
            self.assertNotIn(QWEN_MODEL, model_specs())
            (root / "conversion-progress.json").write_text(json.dumps({"complete": True, "output_bytes": 123}))
            self.assertNotIn(QWEN_MODEL, model_specs())
            (root / "context-stress-test.json").write_text(json.dumps([
                {"passed": True, "usage": {"prompt_tokens": 38}, "task": "html"}
                for _ in range(3)]))
            self.assertNotIn(QWEN_MODEL, model_specs())
            (root / "context-stress-test.json").write_text(json.dumps([
                {"passed": True, "usage": {"prompt_tokens": 3149}, "task": task}
                for task in ("marker", "marker", "html")]))
            self.assertIn(QWEN_MODEL, model_specs())
            def handler(req):
                self.assertEqual(str(req.url), "http://mlx/v1/chat/completions")
                payload = json.loads(req.content)
                self.assertEqual(payload["model"], directory)
                self.assertFalse(payload["enable_thinking"])
                return httpx.Response(200, json={"choices": [{"message": {"content": "4"}}]})
            async with httpx.AsyncClient(transport=MLXTransport("http://ollama", "http://mlx", httpx.MockTransport(handler))) as client:
                result = await client.post("http://ollama/api/chat", json={"model": QWEN_MODEL})
                blocked = await client.post("http://ollama/api/chat", json={"model": QWEN_MODEL,
                    "messages": [{"role": "user", "content": "Bild", "images": ["aGVsbG8="]}]})
            self.assertEqual(result.json()["model"], QWEN_MODEL)
            self.assertEqual(blocked.status_code, 400)
            self.assertNotIn("vision", model_specs()[QWEN_MODEL]["capabilities"])
