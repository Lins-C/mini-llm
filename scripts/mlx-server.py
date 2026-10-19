# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Start the local MLX API with a bounded allocator cache on 16-GB Macs."""
import mlx.core as mx
import mlx.nn as nn
from pathlib import Path

mx.set_cache_limit(64 * 1024**2)

from mlx_vlm.server import main, generation

_load = generation.load


def load_for_server(model_path, *args, **kwargs):
    # This derived checkpoint is exposed as text-only by mlx_transport. Avoid
    # eagerly materializing its unused vision weights on the 16-GB host.
    if Path(str(model_path)).name == "qwen3.8-27b-q3":
        kwargs["lazy"] = True
        model, processor = _load(model_path, *args, **kwargs)
        model.vision_tower = nn.Module()
        mx.eval(model.parameters())
        mx.clear_cache()
        return model, processor
    return _load(model_path, *args, **kwargs)


generation.load = load_for_server

if __name__ == "__main__":
    main()
