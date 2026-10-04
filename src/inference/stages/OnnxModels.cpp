#include "RuntimeSupport.h"
#include <QElapsedTimer>
#include <algorithm>
#include <cmath>

namespace retina::inference {
namespace {
ONNXTensorElementDataType ortDtype(TensorDtype type) {
    switch(type) {case TensorDtype::Float32:return ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;case TensorDtype::Float16:return ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16;case TensorDtype::BFloat16:return ONNX_TENSOR_ELEMENT_DATA_TYPE_BFLOAT16;} return ONNX_TENSOR_ELEMENT_DATA_TYPE_UNDEFINED;
}
QString ortDtypeName(ONNXTensorElementDataType type) {
    if(type==ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT) return "float32";
    if(type==ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16) return "float16";
    if(type==ONNX_TENSOR_ELEMENT_DATA_TYPE_BFLOAT16) return "bfloat16";
    return "unsupported";
}
torch::ScalarType ortTorchType(ONNXTensorElementDataType type) {
    if(type==ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16) return torch::kFloat16;
    if(type==ONNX_TENSOR_ELEMENT_DATA_TYPE_BFLOAT16) return torch::kBFloat16;
    require(type==ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT,"ONNX output must be FP32, FP16 or BF16"); return torch::kFloat32;
}
struct OnnxSession {
    StageConfig config;
    std::shared_ptr<RuntimeContext> runtime; // Outlives session.
    Ort::Session session;
    std::string inputName,outputName;
    ONNXTensorElementDataType inputType;
    OnnxSession(StageConfig c,std::shared_ptr<RuntimeContext> r)
        :config(std::move(c)),runtime(std::move(r)),session(runtime->env,
#ifdef _WIN32
            config.path.toStdWString().c_str(),
#else
            config.path.toStdString().c_str(),
#endif
            sessionOptions(runtime->ortCuda)) {
        require(session.GetInputCount()==1&&session.GetOutputCount()==1,config.stage+" ONNX adapter requires exactly one input and one output");
        Ort::AllocatorWithDefaultOptions allocator;
        inputName=session.GetInputNameAllocated(0,allocator).get(); outputName=session.GetOutputNameAllocated(0,allocator).get();
        require(config.input.name.isEmpty()||config.input.name.toStdString()==inputName,config.stage+" configured ONNX input name does not exist");
        require(config.output.name.isEmpty()||config.output.name.toStdString()==outputName,config.stage+" configured ONNX output name does not exist");
        const auto inputInfo=session.GetInputTypeInfo(0); const auto tensorInfo=inputInfo.GetTensorTypeAndShapeInfo();
        const auto shape=tensorInfo.GetShape(); inputType=tensorInfo.GetElementType();
        require(shape.size()==4&&(shape[0]==1||shape[0]<0)&&shape[1]==3,config.stage+" ONNX input must be [1,3,H,W]");
        const auto outputInfo=session.GetOutputTypeInfo(0); const auto outputTensor=outputInfo.GetTensorTypeAndShapeInfo();
        const auto outputShape=outputTensor.GetShape();
        ortTorchType(outputTensor.GetElementType());
        if(config.input.dynamicSpatial) {
            require(shape[2]<0&&shape[3]<0,config.stage+" model must support dynamic spatial dimensions");
            require(config.input.acceptedDtypes.contains(ortDtypeName(inputType)),config.stage+" model input dtype is not in accepted_dtypes");
            require(outputShape.size()==4&&(outputShape[0]==1||outputShape[0]<0)&&(outputShape[1]==3||outputShape[1]<0)&&outputShape[2]<0&&outputShape[3]<0,"Restoration ONNX output must be dynamic [1,3,H,W]");
        } else {
            require((shape[2]<0||shape[2]==config.input.height)&&(shape[3]<0||shape[3]==config.input.width),config.stage+" configured input dimensions do not match the ONNX model");
            require(inputType==ortDtype(config.input.dtype),config.stage+" configured input dtype does not match the ONNX model");
            require(outputShape.size()==2&&(outputShape[0]==1||outputShape[0]<0)&&outputShape[1]==3,"IQA ONNX output must have 3 class scores in shape [1,3]");
        }
    }
    Ort::Value run(std::vector<float>& pixels,int height,int width,qint64* forwardMs=nullptr) {
        const std::array<int64_t,4> shape{1,3,height,width};
        const auto memory=Ort::MemoryInfo::CreateCpu(OrtArenaAllocator,OrtMemTypeDefault);
        torch::Tensor converted; Ort::Value input{nullptr};
        if(inputType==ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT) input=Ort::Value::CreateTensor<float>(memory,pixels.data(),pixels.size(),shape.data(),shape.size());
        else {
            converted=torch::from_blob(pixels.data(),{1,3,height,width},torch::kFloat32).to(ortTorchType(inputType)).contiguous();
            input=Ort::Value::CreateTensor(memory,converted.data_ptr(),converted.nbytes(),shape.data(),shape.size(),inputType);
        }
        const char* inputs[]={inputName.c_str()}; const char* outputs[]={outputName.c_str()};
        QElapsedTimer timer; timer.start();
        auto values=session.Run(Ort::RunOptions{nullptr},inputs,&input,1,outputs,1);
        if(forwardMs) *forwardMs=timer.elapsed();
        return std::move(values[0]);
    }
};
torch::Tensor outputFloats(const Ort::Value& value,const std::vector<int64_t>& shape) {
    const auto type=value.GetTensorTypeAndShapeInfo().GetElementType();
    auto tensor=torch::from_blob(const_cast<void*>(value.GetTensorRawData()),shape,ortTorchType(type));
    return type==ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT?tensor.contiguous():tensor.to(torch::kFloat32).contiguous();
}
class OnnxQualityModel final:public IQualityModel {
    OnnxSession model_;
public:
    OnnxQualityModel(const StageConfig& config,std::shared_ptr<RuntimeContext> runtime):model_(config,std::move(runtime)) {}
    QualityResult infer(const QImage& image) override {
        auto pixels=preprocess(image,model_.config.input);
        auto value=model_.run(pixels,model_.config.input.height,model_.config.input.width);
        require(value.GetTensorTypeAndShapeInfo().GetShape()==std::vector<int64_t>{1,3},"IQA output must have shape [1,3]");
        auto scores=outputFloats(value,{1,3}); const float* logits=scores.data_ptr<float>();
        std::array<float,3> raw{};
        if(model_.config.output.probabilities) {
            std::copy_n(logits,3,raw.begin()); float sum=0;
            for(float n:raw) {require(std::isfinite(n)&&n>=0&&n<=1,"IQA returned invalid probabilities");sum+=n;}
            require(std::abs(sum-1.0f)<1e-4f,"IQA probabilities must sum to 1");
        } else {
            const float largest=std::max({logits[0],logits[1],logits[2]}); float denominator=0.0f;
            for(int i=0;i<3;++i) {raw[i]=std::exp(logits[i]-largest);denominator+=raw[i];}
            require(std::isfinite(denominator)&&denominator>0.0f,"IQA returned invalid scores");
            for(float& n:raw) n/=denominator;
        }
        QualityResult result; const QStringList canonical{"Good","Usable","Reject"};
        for(int i=0;i<3;++i) result.probabilities[i]=raw[model_.config.output.classes.indexOf(canonical[i])];
        const int selected=static_cast<int>(std::max_element(result.probabilities.begin(),result.probabilities.end())-result.probabilities.begin());
        result.quality=static_cast<Quality>(selected);result.label=canonical[selected];result.confidence=result.probabilities[selected];return result;
    }
};
class OnnxRestorationModel final:public IRestorationModel {
    OnnxSession model_;
public:
    OnnxRestorationModel(const StageConfig& config,std::shared_ptr<RuntimeContext> runtime):model_(config,std::move(runtime)) {}
    RestorationResult infer(const QImage& image) override {
        auto pixels=chwPixels(image,model_.config.input); RestorationResult result;
        auto value=model_.run(pixels,image.height(),image.width(),&result.forwardMs);
        const std::vector<int64_t> shape{1,3,image.height(),image.width()};
        require(value.GetTensorTypeAndShapeInfo().GetShape()==shape,"NAFNet output dimensions do not match the image");
        const auto restored=outputFloats(value,shape);result.image=fromChwPixels(restored.data_ptr<float>(),image.width(),image.height());return result;
    }
};
}
std::unique_ptr<IQualityModel> createOnnxQuality(const StageConfig& config,std::shared_ptr<RuntimeContext> runtime) {return std::make_unique<OnnxQualityModel>(config,std::move(runtime));}
std::unique_ptr<IRestorationModel> createOnnxRestoration(const StageConfig& config,std::shared_ptr<RuntimeContext> runtime) {return std::make_unique<OnnxRestorationModel>(config,std::move(runtime));}
} // namespace retina::inference
