"""Verify that the active RetinaGram environment can execute CUDA tensors."""

import torch


print(f"torch.__version__: {torch.__version__}")
print(f"torch.version.cuda: {torch.version.cuda}")
print(f"torch.cuda.is_available(): {torch.cuda.is_available()}")
if not torch.cuda.is_available():
    raise SystemExit("CUDA available: False")

device_name = torch.cuda.get_device_name(0)
print(f"GPU name: {device_name}")
x = torch.randn((256, 256), device="cuda")
y = x @ x.T
torch.cuda.synchronize()
print(f"CUDA tensor check: OK ({tuple(y.shape)}, {y.device})")
print("CUDA available: True")
