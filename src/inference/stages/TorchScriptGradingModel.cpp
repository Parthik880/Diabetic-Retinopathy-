#include "RuntimeSupport.h"
#include <QElapsedTimer>
#include <algorithm>
namespace retina::inference {
namespace {
class TorchScriptGradingModel final:public IGradingModel {
    StageConfig config_;
    std::shared_ptr<RuntimeContext> runtime_;
    torch::jit::Module module_;
public:
    TorchScriptGradingModel(StageConfig config,std::shared_ptr<RuntimeContext> runtime)
        :config_(std::move(config)),runtime_(std::move(runtime)),module_(torch::jit::load(config_.path.toStdString(),runtime_->device())) {
        module_.eval(); validateTorch(module_,config_,*runtime_,false);
    }
    GradeResult infer(const QImage& image,const QString& directory) override {
        auto input=imageTensor(image,config_,*runtime_);
        QElapsedTimer timer;timer.start();
        const auto output=torchOutput(module_.forward({input}),config_);
        const auto& logits=output.scores;const auto& activations=output.activations;
        require(logits.sizes()==torch::IntArrayRef({1,5}),"Grade logits must have shape [1,5]");
        const auto probabilities=(config_.output.probabilities?logits.to(torch::kFloat32):torch::softmax(logits.to(torch::kFloat32),1)).cpu().contiguous();
        GradeResult result;result.forwardMs=timer.elapsed();
        if(config_.output.probabilities) require(torch::isfinite(probabilities).all().item<bool>()&&probabilities.min().item<float>()>=0&&probabilities.max().item<float>()<=1&&std::abs(probabilities.sum().item<float>()-1.0f)<1e-4f,"Grade probabilities must be finite, in [0,1], and sum to 1");
        const float* scores=probabilities.data_ptr<float>();
        for(int i=0;i<5;++i) result.probabilities[i]=scores[config_.output.classes.indexOf(QString::number(i))];
        result.grade=static_cast<int>(std::max_element(result.probabilities.begin(),result.probabilities.end())-result.probabilities.begin());
        result.confidence=result.probabilities[result.grade];
        timer.restart();
        if(config_.camEnabled) try {
            const int outputIndex=static_cast<int>(config_.output.classes.indexOf(QString::number(result.grade)));
            auto objective=logits.index({0,outputIndex}).to(torch::kFloat32);
            auto gradient=torch::autograd::grad({objective},{activations})[0];
            auto cam=normalizedCam(activations,gradient,config_.input.height,config_.input.width);
            cam=upsample(cam,image.height(),image.width()).squeeze();
            result.camPath=savePng(heatmap(cam,image.width(),image.height()),directory,"grade_gradcam.png");
        } catch(const std::exception& error) {result.warnings<<QString("Grade Grad-CAM failed: %1").arg(QString::fromUtf8(error.what()));}
        result.camMs=timer.elapsed();return result;
    }
};
}
std::unique_ptr<IGradingModel> createTorchGrading(const StageConfig& config,std::shared_ptr<RuntimeContext> runtime) {return std::make_unique<TorchScriptGradingModel>(config,std::move(runtime));}
}
