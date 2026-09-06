"""Keep unused torch compiler modules out of the frozen CPU inference app.

torchvision imports ``torch._dynamo.utils.is_compile_supported`` while it
registers optional ROI operations. RetinaGram does not call those operations
or ``torch.compile``, so importing the compiler stack adds no runtime behavior.
In torch 2.14 that stack imports ``torch._numpy._ufuncs``, whose dynamic module
namespace construction is not compatible with PyInstaller's frozen importer.
"""

from __future__ import annotations

import sys
from types import ModuleType


def _identity_decorator(function=None, *args, **kwargs):
    if function is None:
        return lambda decorated: decorated
    return function


dynamo = ModuleType("torch._dynamo")
dynamo.__path__ = []
dynamo.disable = _identity_decorator
dynamo.allow_in_graph = _identity_decorator
dynamo.is_compiling = lambda: False

dynamo_utils = ModuleType("torch._dynamo.utils")
dynamo_utils.is_compile_supported = lambda *args, **kwargs: False

sys.modules["torch._dynamo"] = dynamo
sys.modules["torch._dynamo.utils"] = dynamo_utils
