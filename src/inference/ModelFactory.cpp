#include "inference/ModelFactory.h"
#include "stages/RuntimeSupport.h"
#include <algorithm>
namespace retina::inference {
ModelStages ModelFactory::create(const ModelConfig& config,bool forceContractValidation) {
    auto runtime=std::make_shared<RuntimeContext>();
    runtime->forceContractValidation=forceContractValidation;
    runtime->cuda=torch::cuda::is_available()&&!qEnvironmentVariableIsSet("RETINAGRAM_FORCE_CPU");
    const auto providers=Ort::GetAvailableProviders();
    runtime->ortCuda=runtime->cuda&&std::find(providers.begin(),providers.end(),"CUDAExecutionProvider")!=providers.end();
    ensureContractsValidated(config,*runtime);
    ModelStages stages;
    try {
        stages.quality=createOnnxQuality(config.quality,runtime);
        stages.restoration=createOnnxRestoration(config.restoration,runtime);
    } catch(const Ort::Exception&) {
        if(!runtime->ortCuda) throw;
        stages.quality.reset(); stages.restoration.reset(); runtime->ortCuda=false;
        stages.quality=createOnnxQuality(config.quality,runtime);
        stages.restoration=createOnnxRestoration(config.restoration,runtime);
    }
    if(forceContractValidation) {
        QImage sample(32,32,QImage::Format_RGB888);sample.fill(Qt::black);
        stages.restoration->infer(sample);
        rememberContract(config.restoration,*runtime);
    }
    stages.lesion=createTorchLesion(config,runtime);
    stages.grading=createTorchGrading(config.grading,runtime);
    stages.cuda=runtime->cuda; stages.ortCuda=runtime->ortCuda;
    return stages;
}
}
