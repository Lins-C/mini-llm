# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""JOSHI erhält gezählte Tokens und eval_duration aus der zentralen Modellschicht."""
import asyncio
import json
import unittest

import httpx
from app.main import ollama_chat_stream, ollama_structured_complete


class ModelUsageTests(unittest.TestCase):
    def test_structured_and_streaming_accumulate_exact_generation_metrics(self):
        usage = dict(prompt_tokens=0, completion_tokens=0, calls=0, eval_duration_ns=0, timed_calls=0)

        def antwort(request):
            daten = json.loads(request.content)
            messung = {"prompt_eval_count": 900, "eval_count": 80,
                       "eval_duration": 2_000_000_000, "total_duration": 99_000_000_000}
            if daten["stream"]:
                return httpx.Response(200, text=json.dumps({"message": {"content": "Hallo"}}) + "\n"
                                      + json.dumps({"done": True, **messung}) + "\n")
            return httpx.Response(200, json={"message": {"content": '{"ok":true}'}, **messung})

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(antwort)) as client:
                await ollama_structured_complete(client, "testmodell", [], {}, usage=usage)
                teile = [t async for t in ollama_chat_stream(client, "testmodell", [], usage=usage)]
                self.assertEqual(teile[-1], {"ende": "stop"})

        asyncio.run(run())
        self.assertEqual(usage, dict(prompt_tokens=1800, completion_tokens=160, calls=2,
                                     eval_duration_ns=4_000_000_000, timed_calls=2,
                                     provider_input_usage_reported=True,
                                     provider_output_usage_reported=True,
                                     provider_input_usage_calls=2,
                                     provider_output_usage_calls=2))

    def test_zero_counts_are_actual_provider_usage(self):
        usage = dict(prompt_tokens=0, completion_tokens=0, calls=0)

        def antwort(_request):
            return httpx.Response(200, json={
                "message": {"content": '{"ok":true}'},
                "prompt_eval_count": 0,
                "eval_count": 0,
            })

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(antwort)) as client:
                await ollama_structured_complete(client, "testmodell", [], {}, usage=usage)

        asyncio.run(run())
        self.assertEqual(usage["prompt_tokens"], 0)
        self.assertEqual(usage["completion_tokens"], 0)
        self.assertEqual(usage["calls"], 1)
        self.assertTrue(usage["provider_input_usage_reported"])
        self.assertTrue(usage["provider_output_usage_reported"])
        self.assertEqual(usage["provider_input_usage_calls"], 1)
        self.assertEqual(usage["provider_output_usage_calls"], 1)

    def test_finished_stream_without_counts_is_not_provider_counted(self):
        usage = dict(prompt_tokens=0, completion_tokens=0, calls=0)

        def antwort(_request):
            return httpx.Response(200, text=(
                json.dumps({"message": {"content": "Hallo"}}) + "\n"
                + json.dumps({"done": True, "done_reason": "stop"}) + "\n"
            ))

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(antwort)) as client:
                teile = [teil async for teil in ollama_chat_stream(client, "testmodell", [], usage=usage)]
                self.assertEqual(teile[-1], {"ende": "stop"})

        asyncio.run(run())
        self.assertEqual(usage["prompt_tokens"], 0)
        self.assertEqual(usage["completion_tokens"], 0)
        self.assertEqual(usage["calls"], 1)
        self.assertFalse(usage["provider_input_usage_reported"])
        self.assertFalse(usage["provider_output_usage_reported"])
        self.assertEqual(usage["provider_input_usage_calls"], 0)
        self.assertEqual(usage["provider_output_usage_calls"], 0)

    def test_mixed_calls_keep_the_provider_backed_part_identifiable(self):
        usage = dict(prompt_tokens=0, completion_tokens=0, calls=0)

        def antwort(request):
            daten = json.loads(request.content)
            if daten["stream"]:
                return httpx.Response(200, text=(
                    json.dumps({"message": {"content": "ohne Zähler"}}) + "\n"
                    + json.dumps({"done": True}) + "\n"
                ))
            return httpx.Response(200, json={
                "message": {"content": '{"ok":true}'},
                "prompt_eval_count": 7,
                "eval_count": 5,
            })

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(antwort)) as client:
                await ollama_structured_complete(client, "testmodell", [], {}, usage=usage)
                _ = [teil async for teil in ollama_chat_stream(client, "testmodell", [], usage=usage)]

        asyncio.run(run())
        self.assertEqual((usage["prompt_tokens"], usage["completion_tokens"], usage["calls"]), (7, 5, 2))
        self.assertTrue(usage["provider_input_usage_reported"])
        self.assertTrue(usage["provider_output_usage_reported"])
        self.assertEqual(usage["provider_input_usage_calls"], 1)
        self.assertEqual(usage["provider_output_usage_calls"], 1)
