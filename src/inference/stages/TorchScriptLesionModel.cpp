#include "RuntimeSupport.h"
#include "inference/stages/LesionPostprocessor.h"
#include <QElapsedTimer>
namespace retina::inference {
namespace {
class TorchScriptLesionModel final:public ILesionModel {
    ModelConfig config_;
    std::shared_ptr<RuntimeContext> runtime_;
    torch::jit::Module module_;
    LesionPostprocessor postprocessor_;
public:
    TorchScriptLesionModel(ModelConfig config,std::shared_ptr<RuntimeContext> runtime)
        :config_(std::move(config)),runtime_(std::move(runtime)),module_(torch::jit::load(config_.lesion.path.toStdString(),runtime_->device())),
         postprocessor_(config_.lesionClasses,config_.postprocessingReferenceSize) {
        module_.eval();validateTorch(module_,config_.lesion,*runtime_,true);
    }
    LesionResult infer(const QImage& image,const QString& directory,const ProgressCallback& progress) override {
        const auto& config=config_.lesion;const int width=image.width(),height=image.height(),pixelCount=width*height;
        auto input=imageTensor(image,config,*runtime_);
        if(progress) progress("LESION_INFERENCE");
        QElapsedTimer timer;timer.start();
        const auto output=torchOutput(module_.forward({input}),config);
        const auto& logits=output.scores;const auto& activations=output.activations;
        require(logits.sizes()==torch::IntArrayRef({1,4,config.input.height,config.input.width}),"Lesion logits must be [1,4,configured height,configured width]");
        const auto modelProbabilities=config.output.probabilities?logits.to(torch::kFloat32):torch::sigmoid(logits.to(torch::kFloat32));
        if(config.output.probabilities) require(torch::isfinite(modelProbabilities).all().item<bool>()&&modelProbabilities.min().item<float>()>=0&&modelProbabilities.max().item<float>()<=1,"Lesion probabilities must be finite and in [0,1]");
        auto probabilities=upsample(modelProbabilities,height,width).to(torch::kCPU,torch::kFloat32).contiguous();
        const qint64 forwardMs=timer.elapsed();
        SegmentationProbabilities planes;planes.width=width;planes.height=height;
        const float* maps=probabilities.data_ptr<float>();
        for(int i=0;i<4;++i) planes.channels[i]={maps+static_cast<size_t>(config_.lesionClasses[i].channel)*pixelCount,static_cast<size_t>(pixelCount)};
        auto result=postprocessor_.process(image,planes,directory,progress);result.forwardAndTransferMs=forwardMs;
        const bool camEnabled=config.camEnvironment.isEmpty()?config.camEnabled:qEnvironmentVariableIsSet(config.camEnvironment.toUtf8().constData())?qEnvironmentVariableIntValue(config.camEnvironment.toUtf8().constData())==1:config.camEnabled;
        if(camEnabled) for(int i=0;i<4;++i) {
            auto& channel=result.channels[i]; if(channel.rawRegions.empty()) continue;
            try {
                std::vector<float> mask(pixelCount);
                for(int pixel=0;pixel<pixelCount;++pixel) mask[pixel]=channel.binaryMask[pixel]?1.0f:0.0f;
                auto targetMask=torch::from_blob(mask.data(),{1,1,height,width},torch::kFloat32).to(runtime_->device()).clone();
                targetMask=upsample(targetMask,config.input.height,config.input.width,true).squeeze();
                require(targetMask.sum().item<float>()>0.0f,"Lesion Grad-CAM target disappeared on resize");
                auto objective=(logits.index({0,config_.lesionClasses[i].channel}).to(torch::kFloat32)*targetMask).sum()/targetMask.sum();
                auto gradient=torch::autograd::grad({objective},{activations},{},true)[0];
                auto cam=normalizedCam(activations,gradient,height,width).squeeze();
                channel.camPath=savePng(heatmap(cam,width,height),directory,channel.code+"_gradcam.png");
            } catch(const std::exception& error) {result.warnings<<QString("%1 lesion Grad-CAM failed: %2").arg(channel.code,QString::fromUtf8(error.what()));}
        }
        if(progress) progress("LESION_RESULTS_SAVING");return result;
    }
};
}
std::unique_ptr<ILesionModel> createTorchLesion(const ModelConfig& config,std::shared_ptr<RuntimeContext> runtime) {return std::make_unique<TorchScriptLesionModel>(config,std::move(runtime));}
}
