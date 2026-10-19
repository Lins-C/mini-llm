# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class LauncherTests(unittest.TestCase):
    def test_only_text_qwen_drops_vision_and_loads_lazily(self):
        core = types.ModuleType("mlx.core")
        core.set_cache_limit = Mock()
        core.eval = Mock()
        core.clear_cache = Mock()
        nn = types.ModuleType("mlx.nn")
        nn.Module = Mock()
        model = Mock()
        processor = object()
        original = Mock(return_value=(model, processor))
        server = types.ModuleType("mlx_vlm.server")
        server.main = Mock()
        server.generation = types.SimpleNamespace(load=original)
        modules = {"mlx": types.ModuleType("mlx"), "mlx.core": core,
                   "mlx.nn": nn, "mlx_vlm": types.ModuleType("mlx_vlm"),
                   "mlx_vlm.server": server}
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location("launcher_test",
                Path(__file__).resolve().parents[1] / "scripts/mlx-server.py")
            launcher = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(launcher)
            launcher.load_for_server("/models/ministral", trust_remote_code=False)
            self.assertNotIn("lazy", original.call_args.kwargs)
            core.eval.assert_not_called()
            result = launcher.load_for_server("/models/qwen3.8-27b-q3")
            self.assertTrue(original.call_args.kwargs["lazy"])
            self.assertIs(model.vision_tower, nn.Module.return_value)
            core.eval.assert_called_once_with(model.parameters())
            core.clear_cache.assert_called_once()
            self.assertEqual(result, (model, processor))
