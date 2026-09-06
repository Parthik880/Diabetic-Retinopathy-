# NAFNet restoration

This package vendors the required architecture files from
[`megvii-research/NAFNet`](https://github.com/megvii-research/NAFNet) at commit
`2b4af71ebe098a92a75910c233a3965a3e93ede4`. The upstream MIT license and the
Apache 2.0 terms for BasicSR-derived portions are included in `nafnet/LICENSE`;
source copyright and attribution headers are retained.

The wrapper uses the width-32 configuration prepared for the retinal pipeline:

```text
width: 32
encoder blocks: [2, 2, 4, 8]
middle blocks: 12
decoder blocks: [2, 2, 2, 2]
input: RGB float tensor in [0, 1], without ImageNet normalization
output: same spatial resolution as the input
```

The current default checkpoint is provided by the centralized offline bundle:

```text
checkpoint/restoration/NAFNet-SIDD-width32.pth
```

BasicSR wrappers containing `params`, `params_ema`, `state_dict`, `net_g`, or
`model` are accepted and loaded strictly. The official generic
`NAFNet-SIDD-width32.pth` is 116,861,841 bytes, exceeds GitHub's normal 100 MB
file limit, and is therefore not committed. It is a SIDD denoising checkpoint,
not a retinal-trained model. The loader reads it directly and never downloads
weights. Set `DR_CHECKPOINT_DIR` when the extracted bundle is not at the
repository-relative `checkpoint/` path.

The locally prepared retinal training setup used aligned 384x384 RGB pairs,
256x256 training crops, no flip/rotation augmentation, AdamW, PSNR loss, and
the official width-32 network. Training datasets and environments are not part
of this inference repository.
