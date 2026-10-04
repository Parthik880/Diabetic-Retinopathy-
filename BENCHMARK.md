# RetinaGram migration measurements

Measured on 2026-10-03, Windows, RTX 3060 12 GiB, CUDA 12.9, MSVC Release build. The reference is the untouched Python FP32 pipeline with persistent CUDA models. The native application uses a partially INT8 IQA graph, FP16 NAFNet, and BF16 lesion/grade models. Each process loaded models once and ran the same image three times. GPU work was synchronized before Python stage timings; ONNX Runtime `Run` and native CPU transfers completed before native stage timers stopped. File generation is included in total analysis time. The runs are a small performance sample, not a throughput or clinical study.

| Case | Implementation | First analysis | Later analyses (mean of 2) | Mean of 3 | Median | p95 of 3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Good, 2592×1728 | Python reference | 6,014 ms | 3,340 ms | 4,231 ms | 3,379 ms | 5,751 ms |
| Good, 2592×1728 | Native C++ | 4,731 ms | 2,865 ms | 3,487 ms | 2,948 ms | 4,553 ms |
| Usable, 768×512 | Python reference | 1,056 ms | 759 ms | 858 ms | 767 ms | 1,027 ms |
| Usable, 768×512 | Native C++ | 14,174 ms | 938 ms | 5,350 ms | 964 ms | 12,853 ms |

The native Good path was about 14% faster for these two later runs. The native Usable path was about 24% slower for these two later runs. Its first run was much slower because ONNX Runtime CUDA initialized the FP16 restoration shape and kernels. These are observed measurements only; different sizes, hardware, artifact output, and cache state can change the result. The native app writes fewer auxiliary artifact formats than the Python reference, so end-to-end timings do not isolate language/runtime speed.

## Warm stage timing

Mean milliseconds over iterations 2–3. `—` means the stage was skipped or a directly comparable timer was not recorded.

| Stage | Good Python | Good native | Usable Python | Usable native |
| --- | ---: | ---: | ---: | ---: |
| IQA including preprocessing | 29.5 | 36 | 14.5 | 15 |
| NAFNet whole stage | — | — | 208.3 | 298 |
| NAFNet forward only | — | — | — | 246.5 |
| Grade and grade CAM, including artifact | 432.1 | 442 | 66.4 | 185.5 |
| Native grade forward | — | 100 | — | 101.5 |
| Native grade CAM generation and PNG | — | 312 | — | 78 |
| Lesion stage, including visualization | 2,759.7 | 2,352 | 402.6 | 432.5 |
| Native lesion forward, resize, CPU transfer | — | 302 | — | 243 |

The Python grade timer also recorded a warm ConvNeXt forward of 25–39 ms for Good and 6.6–6.7 ms for Usable; backward CAM took 60–111 ms and 12 ms respectively. The rest of the Python grade stage includes preprocessing and PNG writing. The native stage timers and Python timers cover slightly different internal boundaries. Raw timing JSON remains local generated evidence, excluded from the branch.

## Startup and memory

| Metric | Python reference | Native C++ |
| --- | ---: | ---: |
| Model initialization, one process | 1,020 ms | 1,566 ms (Good run), 1,508 ms (Usable run) |
| Idle process RAM after model initialization | 866 MiB | 452 MiB |
| Highest observed process RAM, Good | 1,809 MiB sampled RSS | 1,814 MiB Windows peak working set |
| Highest observed process RAM, Usable | 1,867 MiB sampled RSS | 2,232 MiB Windows peak working set |
| Source PyTorch peak allocated VRAM | 445 MiB Good; 707 MiB Usable | Not directly comparable: native ORT and LibTorch use different allocators. |
| Native CUDA device memory used after model initialization | — | 1,214.5 MiB global snapshot |
| Native CUDA device memory used after runs | — | 1,726.5 MiB Good; up to 2,120.5 MiB Usable global snapshots |
| Executable file | — | 642,560 bytes |
| Deployment package | — | 54 files, 4,714,171,084 bytes (4.39 GiB), including four production models totaling 137,957,791 bytes |

Native CUDA memory figures are `cudaMemGetInfo` snapshots after stages and include other device allocations; they are not a process peak. On this Windows WDDM host, `nvidia-smi` reports process VRAM as `N/A`, so a process-specific native peak could not be measured. The source figure is PyTorch allocator peak and excludes driver/context or non-PyTorch allocations. CPU fallback was verified on 512×341 Good and Usable images, taking about 34 seconds per analysis.

Model initialization is the measured startup proxy. Full cold boot/process import time and a separate warm process startup time were not isolated. The first analysis column shows kernel and shape setup after model loading; later columns show reuse of the same sessions. The p95 values interpolate only three runs and should not be used as a production latency estimate.

## Accuracy checks tied to the benchmark

Six local Good/Usable/Reject cases agreed on IQA class and routing. Five non-rejected cases agreed on DR grade. The 768×512 Usable restoration had 49.71 dB PSNR against the FP32 reference PNG with mean absolute uint8 difference 0.168. Its largest 129-level channel difference was at a nearly black border pixel; 30 pixels had any channel difference above 30. On reference pixels with mean intensity above 30, the maximum difference was 27. Grade CAM spatial correlations were high on most cases. Lesion mask IoU varies by class and image, with zero overlap on very sparse EX predictions in two cases. This discrepancy follows the requested FP32-to-BF16 conversion and prevents a claim of clinical equivalence.

The table above records the original 2026-10-03 migration build, not the final executable's file size or an updated performance guarantee. Raw files were local generated evidence under build/validation and are deliberately excluded from the branch. Re-run scripts/benchmark_reference.py, scripts/benchmark-native.ps1 with explicit -GoodImage and -UsableImage inputs, and scripts/compare_outputs.py using the local fixture setup in README. Image bytes and generated artifacts are not included in Git.

## Model-modularity measurements (2026-10-04)

Three GPU iterations per implementation/case; warm mean uses iterations 2–3.
Totals include artifact generation. Before/after refer to the original native
manager and the refactored native adapters, both using the same production bytes.

| Metric | Good before -> after | Usable before -> after |
| --- | ---: | ---: |
| Initialization | 2,264 -> 2,456 ms | 2,429 -> 2,301 ms |
| First analysis | 4,301 -> 4,306 ms | 13,308 -> 12,846 ms |
| Warm mean | 2,663.5 -> 2,548.5 ms | 891 -> 895.5 ms |
| Idle process RAM | 451.21 -> 452.94 MiB | 451.98 -> 452.82 MiB |
| Observed peak process RAM | 1,813.47 -> 1,819.61 MiB | 2,235.71 -> 2,224.41 MiB |
| Total-device CUDA used snapshot | 1,726.5 -> 1,726.5 MiB | 2,120.5 -> 2,120.5 MiB |

The CUDA value was sampled after the last run, includes other device allocations,
and is neither isolated process VRAM nor a transient peak. This sample does not
establish a statistically significant speed improvement.

CPU Good analysis measured 34,018 -> 33,081 ms; CPU Usable 35,851 -> 34,290 ms.
Cache-miss/hit initialization in an isolated Reject process measured
12,484 / 5,479 ms. Hardware, file/cache state, and validation probes affect startup.

Seven of eight strict native comparisons were exact: five GPU cases and two CPU
cases. GPU Usable kept grade 3 and MA/HE/EX/SE counts 13/30/1/0, while confidence
changed 0.9749262928962708 -> 0.9745547771453857. Restoration differed by at most
one uint8 level (MAE 0.00119527; PSNR 77.3561 dB); MA/HE mask IoUs were
0.98507463 / 0.97732531, EX/SE 1. Original-executable repeats also differed by
one restored level, with grade confidence changes up to +0.00112224 and changing
MA/HE counts. The refactor therefore does not warrant a bitwise GPU Usable claim.
See specs/S2-model-modularity.txt for full measurements and scope.
