"""Loads the pack as ComfyUI does, without a server: run the checks of this folder with the python of ComfyUI (the pack needs comfy_api).

    ComfyUI/.venv/Scripts/python.exe custom_nodes/ComfyUI-Majoor-VideoTools/tests/comfy/check_schemas.py
"""
import importlib.util
import os
import sys
import types
from pathlib import Path

PACK = Path(__file__).resolve().parents[2]
COMFY = PACK.parents[1]
os.chdir(COMFY)
sys.path.insert(0, str(COMFY))

import server  # noqa: E402


class _Routes:
    def get(self, *args, **kwargs):
        return lambda f: f

    def post(self, *args, **kwargs):
        return lambda f: f


server.PromptServer.instance = types.SimpleNamespace(routes=_Routes())
spec = importlib.util.spec_from_file_location("MVT", PACK / "__init__.py", submodule_search_locations=[str(PACK)])
pack = importlib.util.module_from_spec(spec)
sys.modules["MVT"] = pack
spec.loader.exec_module(pack)
