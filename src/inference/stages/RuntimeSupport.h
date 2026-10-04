#pragma once
// Private runtime types: only adapters and ModelFactory include this header.
#include "inference/ModelConfig.h"
#include "inference/ModelTypes.h"
#include "inference/Preprocessing.h"
#include <onnxruntime_cxx_api.h>
#include <torch/script.h>
#include <torch/torch.h>
#include <memory>

namespace retina::inference {
struct RuntimeContext {
    Ort::Env env{ORT_LOGGING_LEVEL_WARNING,"RetinaGram"};
    bool cuda = false, ortCuda = false;
    bool forceContractValidation = false;
    bool externalContractsVerified = false;
    torch::Device device() const { return torch::Device(cuda?torch::kCUDA:torch::kCPU); }
};
Ort::SessionOptions sessionOptions(bool cuda);
torch::ScalarType torchDtype(TensorDtype dtype);
torch::Tensor upsample(const torch::Tensor&, int height, int width, bool nearest=false);
QImage heatmap(const torch::Tensor&, int width, int height);
torch::Tensor normalizedCam(torch::Tensor activations,torch::Tensor gradients,int height,int width);
torch::Tensor imageTensor(const QImage&,const StageConfig&,const RuntimeContext&);
struct TorchOutputs { torch::Tensor scores, activations; };
TorchOutputs torchOutput(const c10::IValue&,const StageConfig&);
void validateTorch(torch::jit::Module&,const StageConfig&,const RuntimeContext&,bool segmentation);
void ensureContractsValidated(const ModelConfig&,RuntimeContext&);
void rememberContract(const StageConfig&,const RuntimeContext&);
std::unique_ptr<IQualityModel> createOnnxQuality(const StageConfig&,std::shared_ptr<RuntimeContext>);
std::unique_ptr<IRestorationModel> createOnnxRestoration(const StageConfig&,std::shared_ptr<RuntimeContext>);
std::unique_ptr<IGradingModel> createTorchGrading(const StageConfig&,std::shared_ptr<RuntimeContext>);
std::unique_ptr<ILesionModel> createTorchLesion(const ModelConfig&,std::shared_ptr<RuntimeContext>);
}
