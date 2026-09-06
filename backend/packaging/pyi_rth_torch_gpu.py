"""Keep the unused Torch compiler stack out of frozen eager CUDA inference.

torchvision imports ``torch._dynamo.utils.is_compile_supported`` while it
registers optional ROI operations. RetinaGram uses eager CUDA inference and
does not call those operations or ``torch.compile``. Importing the compiler
stack under PyInstaller reaches ``torch._numpy._ufuncs``, whose dynamically
constructed namespace is not compatible with the frozen importer used here.

This hook does not alter CUDA availability, CUDA libraries, or device choice.
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
