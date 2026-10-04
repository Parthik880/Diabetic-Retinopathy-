#include "RuntimeSupport.h"
#include "inference/ModelTypes.h"
#include <torch/nn/functional/upsampling.h>
#include <torch/version.h>
#include <QCryptographicHash>
#include <QDataStream>
#include <QDir>
#include <QFile>
#include <QSaveFile>
#include <QStandardPaths>
#include <QProcess>
#include <QCoreApplication>
#include <QFileInfo>
namespace retina::inference {
torch::Tensor upsample(const torch::Tensor& tensor, int height, int width, bool nearest) {
    using namespace torch::nn::functional;
    auto options = InterpolateFuncOptions().size(std::vector<int64_t>{height, width});
    if (nearest) return interpolate(tensor, options.mode(torch::kNearest));
    return interpolate(tensor, options.mode(torch::kBilinear).align_corners(false));
}

torch::Tensor normalizedCam(torch::Tensor activations, torch::Tensor gradients, int height, int width) {
    auto weights = gradients.mean({2, 3}, true);
    auto cam = torch::relu((weights * activations).sum(1, true));
    cam = upsample(cam, height, width).to(torch::kFloat32);
    const auto minimum = cam.amin({2, 3}, true);
    const auto maximum = cam.amax({2, 3}, true);
    return ((cam - minimum) / (maximum - minimum + 1e-8)).detach().cpu();
}

Ort::SessionOptions sessionOptions(bool cuda) {
    Ort::SessionOptions options;
    options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
    options.SetIntraOpNumThreads(2);
    if (cuda) {
        OrtCUDAProviderOptions gpu{};
        gpu.device_id = 0;
        options.AppendExecutionProvider_CUDA(gpu);
    }
    return options;
}


torch::ScalarType torchDtype(TensorDtype type) {
    switch(type) { case TensorDtype::Float32:return torch::kFloat32;case TensorDtype::Float16:return torch::kFloat16;case TensorDtype::BFloat16:return torch::kBFloat16; } return torch::kFloat32;
}
QImage heatmap(const torch::Tensor& values,int width,int height) {
    const auto map=values.detach().to(torch::kCPU,torch::kFloat32).contiguous();
    return probabilityHeatmap({map.data_ptr<float>(),static_cast<size_t>(map.numel())},width,height);
}
torch::Tensor imageTensor(const QImage& image,const StageConfig& config,const RuntimeContext& context) {
    auto pixels=preprocess(image,config.input);
    auto input=torch::from_blob(pixels.data(),{1,3,config.input.height,config.input.width},torch::kFloat32).to(context.device(),torchDtype(config.input.dtype));
    return !context.cuda&&config.input.dtype==TensorDtype::Float32?input.clone():input;
}
TorchOutputs torchOutput(const c10::IValue& value,const StageConfig& config) {
    if(!config.output.tuple) { require(value.isTensor(),config.stage+" model must return a tensor"); return {value.toTensor(),{}}; }
    require(value.isTuple(),config.stage+" model must return scores and activations");
    const auto elements=value.toTuple()->elements();
    require(elements.size()==2&&elements[config.output.scoresIndex].isTensor()&&elements[config.output.activationsIndex].isTensor(),config.stage+" model must return exactly two tensors at the configured tuple indices");
    return {elements[config.output.scoresIndex].toTensor(),elements[config.output.activationsIndex].toTensor()};
}

namespace {
const QByteArray verified("RetinaGram verified model contract v2\n");
QString cacheDirectory() {
    const auto internal=qEnvironmentVariable("RETINAGRAM_INTERNAL_CONTRACT_CACHE");
    return internal.isEmpty()?QDir(QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation)).filePath("model-contracts"):internal;
}
QString cachePath(const StageConfig& config,const RuntimeContext& context) {
    QFile artifact(config.path);require(artifact.open(QIODevice::ReadOnly),"Cannot read model for contract validation: "+config.path);
    QCryptographicHash hash(QCryptographicHash::Sha256);require(hash.addData(&artifact),"Cannot hash model for contract validation: "+config.path);
    QByteArray contract;QDataStream stream(&contract,QIODevice::WriteOnly);
    stream<<QString("contract-v2")<<QString(TORCH_VERSION)<<config.stage<<config.input.width<<config.input.height
          <<static_cast<int>(config.input.dtype)<<config.input.dynamicSpatial<<config.input.acceptedDtypes
          <<config.output.tuple<<config.output.scoresIndex<<config.output.activationsIndex<<config.output.probabilities<<context.cuda;
    return QDir(cacheDirectory()).filePath(QString::fromLatin1(hash.result().toHex())+".ok");
}
bool cached(const StageConfig& config,const RuntimeContext& context) {
    QFile file(cachePath(config,context));return file.open(QIODevice::ReadOnly)&&file.readAll()==verified;
}
}
void rememberContract(const StageConfig& config,const RuntimeContext& context) {
    if(QDir().mkpath(cacheDirectory())) {QSaveFile file(cachePath(config,context));if(file.open(QIODevice::WriteOnly)){file.write(verified);file.commit();}}
}
void ensureContractsValidated(const ModelConfig& config,RuntimeContext& context) {
    if(context.forceContractValidation) return;
    if(cached(config.restoration,context)&&cached(config.grading,context)&&cached(config.lesion,context)) {context.externalContractsVerified=true;return;}
    // Keep validation warm-up out of the patient process and preserve the
    // original stage execution order. Use the native CLI once on cache misses,
    // then load the persistent patient-work sessions normally.
    const auto helper=QDir(QCoreApplication::applicationDirPath()).filePath(
#ifdef _WIN32
        "RetinaGram.exe"
#else
        "RetinaGram"
#endif
    );
    require(QFileInfo(helper).isFile(),"Native model validation helper is missing: "+helper);
    QProcess process;
    process.start(helper,{"--validate-models",config.file,config.checkpointsDirectory,cacheDirectory()});
    require(process.waitForStarted(30000),"Could not start native model contract validation: "+process.errorString());
    if(!process.waitForFinished(300000)) {process.kill();process.waitForFinished();require(false,"Native model contract validation timed out");}
    require(process.exitStatus()==QProcess::NormalExit&&process.exitCode()==0,"Model contract validation failed: "+QString::fromUtf8(process.readAllStandardError()));
    context.externalContractsVerified=true;
}
void validateTorch(torch::jit::Module& module,const StageConfig& config,const RuntimeContext& context,bool segmentation) {
    const auto schema=module.get_method("forward").function().getSchema();
    require(schema.arguments().size()==2&&schema.returns().size()==1,config.stage+" adapter requires one image tensor input");
    if(context.externalContractsVerified) return;
    torch::NoGradGuard guard;
    auto sample=torch::zeros({1,3,config.input.height,config.input.width},torch::TensorOptions().device(context.device()).dtype(torchDtype(config.input.dtype)));
    const auto output=torchOutput(module.forward({sample}),config);
    if(segmentation) require(output.scores.sizes()==torch::IntArrayRef({1,4,config.input.height,config.input.width}),"Lesion model output must be [1,4,configured height,configured width]");
    else require(output.scores.sizes()==torch::IntArrayRef({1,5}),"Grading model output must have 5 class scores in shape [1,5]");
    require(output.scores.is_floating_point(),config.stage+" scores must be floating point");
    if(config.output.tuple) require(output.activations.dim()==4&&output.activations.size(0)==1&&output.activations.is_floating_point(),config.stage+" CAM activation must be a floating point NCHW tensor");
    rememberContract(config,context);
}
} // namespace retina::inference
