#include "inference/ModelConfig.h"
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QSet>
#include <cmath>
#include <stdexcept>

namespace retina::inference {
namespace {
[[noreturn]] void invalid(const QString& context, const QString& reason) {
    throw std::runtime_error(QString("Invalid %1 model configuration: %2").arg(context, reason).toStdString());
}
struct Fields {
    QJsonObject object;
    QString context;
    void keys(const QStringList& allowed) const {
        for(auto it=object.begin();it!=object.end();++it)
            if(!allowed.contains(it.key())) invalid(context,"unknown field '"+it.key()+"'");
    }
    QJsonValue value(const QString& key) const {
        if(!object.contains(key)) invalid(context,"missing required field '"+key+"'");
        return object[key];
    }
    QString string(const QString& key) const {
        const auto v=value(key);
        if(!v.isString()||v.toString().isEmpty()) invalid(context,key+" must be a non-empty string");
        return v.toString();
    }
    bool boolean(const QString& key) const {
        const auto v=value(key); if(!v.isBool()) invalid(context,key+" must be boolean"); return v.toBool();
    }
    double number(const QString& key) const {
        const auto v=value(key); if(!v.isDouble()||!std::isfinite(v.toDouble())) invalid(context,key+" must be finite numeric"); return v.toDouble();
    }
    int integer(const QString& key, int minimum=0, int maximum=8192) const {
        const double n=number(key); if(n!=std::floor(n)||n<minimum||n>maximum) invalid(context,key+QString(" must be an integer in [%1,%2]").arg(minimum).arg(maximum)); return static_cast<int>(n);
    }
    Fields child(const QString& key) const {
        const auto v=value(key); if(!v.isObject()) invalid(context,key+" must be an object"); return {v.toObject(),context+"."+key};
    }
    QStringList strings(const QString& key) const {
        const auto v=value(key); if(!v.isArray()) invalid(context,key+" must be an array");
        QStringList out; for(const auto& item:v.toArray()) { if(!item.isString()||item.toString().isEmpty()) invalid(context,key+" must contain non-empty strings"); out<<item.toString(); } return out;
    }
    void exact(const QString& key, const QString& expected) const {
        if(string(key)!=expected) invalid(context,key+" must be '"+expected+"'");
    }
    void unitRange(const QString& key) const {
        const auto v=value(key); if(!v.isArray()||v.toArray()!=QJsonArray{0.0,1.0}) invalid(context,key+" must be [0.0,1.0]");
    }
};
TensorDtype dtype(const QString& value, const QString& context) {
    if(value=="float32") return TensorDtype::Float32;
    if(value=="float16") return TensorDtype::Float16;
    if(value=="bfloat16") return TensorDtype::BFloat16;
    invalid(context,"dtype must be float32, float16 or bfloat16");
}
std::array<float,3> triple(const Fields& fields,const QString& key,bool positive) {
    const auto v=fields.value(key); if(!v.isArray()||v.toArray().size()!=3) invalid(fields.context,key+" must contain 3 values");
    std::array<float,3> out{}; int i=0;
    for(const auto& n:v.toArray()) {
        if(!n.isDouble()||!std::isfinite(n.toDouble())||(positive&&n.toDouble()<=0)||std::abs(n.toDouble())>1e6) invalid(fields.context,key+" contains an invalid value");
        out[i++]=static_cast<float>(n.toDouble());
    } return out;
}
void canonicalClasses(const Fields& fields, const QStringList& expected, QStringList& out) {
    out=fields.strings("classes");
    if(out.size()!=expected.size()) invalid(fields.context,QString("expected %1 class labels but %2 were configured").arg(expected.size()).arg(out.size()));
    auto sorted=out, target=expected; sorted.sort(); target.sort();
    if(sorted!=target) invalid(fields.context,"classes must be a permutation of "+expected.join(", "));
}
StageConfig stage(const Fields& root,const QString& name,const QString& expectedAdapter,const QString& checkpoints) {
    const auto f=root.child(name); f.keys(name=="lesion"?QStringList{"enabled","adapter","model","input","output","cam","classes","postprocessing"}:name=="grading"?QStringList{"enabled","adapter","model","input","output","cam"}:QStringList{"enabled","adapter","model","input","output"});
    if(!f.boolean("enabled")) invalid(name,"this pipeline requires the stage to be enabled");
    StageConfig s; s.stage=name; s.adapter=f.string("adapter"); s.model=f.string("model");
    if(s.adapter!=expectedAdapter) invalid(name,"unsupported adapter '"+s.adapter+"'");
    if(s.model=="."||s.model==".."||s.model.contains('/')||s.model.contains('\\')||s.model.contains(':')||QDir::isAbsolutePath(s.model)) invalid(name,"model must be a filename in the flat checkpoints directory");
    s.path=QDir(checkpoints).absoluteFilePath(s.model);
    if(!QFileInfo(s.path).isFile()) invalid(name,"required model is missing: "+s.path);
    const auto in=f.child("input");
    in.keys({"name","width","height","dynamic_spatial","channels","layout","dtype","color","resize","normalization","range","accepted_dtypes"});
    if(in.integer("channels",1,16)!=3) invalid(name,"input channels must be 3");
    in.exact("layout","NCHW"); in.exact("color","RGB");
    if(in.object.contains("name")) s.input.name=in.string("name");
    const auto norm=in.child("normalization"); norm.keys({"type","mean","std"});
    const QString normType=norm.string("type");
    if(normType!="none"&&normType!="imagenet"&&normType!="mean_std") invalid(name,"unsupported normalization type");
    s.input.normalize=normType!="none";
    if(s.input.normalize) { s.input.mean=triple(norm,"mean",false); s.input.std=triple(norm,"std",true); }
    else if(norm.object.size()!=1) invalid(name,"none normalization cannot specify mean/std");
    const auto out=f.child("output");
    if(name=="restoration") {
        out.keys({"name","same_dimensions_as_input","range"});
        if(!in.boolean("dynamic_spatial")||!out.boolean("same_dimensions_as_input")) invalid(name,"adapter requires dynamic spatial input and same-dimension output");
        if(in.object.contains("width")||in.object.contains("height")||in.object.contains("dtype")) invalid(name,"dynamic restoration uses accepted_dtypes, not fixed size/dtype");
        in.exact("resize","none"); in.unitRange("range"); out.unitRange("range");
        if(s.input.normalize) invalid(name,"restoration requires none normalization");
        s.input.dynamicSpatial=true; s.input.acceptedDtypes=in.strings("accepted_dtypes");
        if(s.input.acceptedDtypes.isEmpty()) invalid(name,"accepted_dtypes cannot be empty");
        for(const auto& t:s.input.acceptedDtypes) dtype(t,name);
    } else {
        s.input.width=in.integer("width",1,8192); s.input.height=in.integer("height",1,8192);
        if(static_cast<qint64>(s.input.width)*s.input.height>16'000'000) invalid(name,"input exceeds 16 megapixels");
        in.exact("resize","pillow_bilinear"); s.input.dtype=dtype(in.string("dtype"),name);
        if(in.object.contains("dynamic_spatial")||in.object.contains("accepted_dtypes")||in.object.contains("range")) invalid(name,"fixed-size adapter does not accept dynamic restoration settings");
        out.keys(name=="iqa"?QStringList{"name","type","activation","classes"}:name=="grading"?QStringList{"type","contract","activation","classes","scores_index","activations_index"}:QStringList{"type","contract","activation","channels","scores_index","activations_index"});
        const QString type=out.string("type");
        if(type!="logits"&&type!="probabilities") invalid(name,"output.type must be logits or probabilities");
        s.output.probabilities=type=="probabilities";
        out.exact("activation",s.output.probabilities?"none":name=="lesion"?"sigmoid":"softmax");
        if(name=="iqa") canonicalClasses(out,{"Good","Usable","Reject"},s.output.classes);
        else {
            const QString contract=out.string("contract");
            if(contract!="tensor"&&contract!="scores_and_activations") invalid(name,"output.contract must be tensor or scores_and_activations");
            s.output.tuple=contract=="scores_and_activations";
            if(s.output.tuple) {
                s.output.scoresIndex=out.integer("scores_index",0,1); s.output.activationsIndex=out.integer("activations_index",0,1);
                if(s.output.scoresIndex==s.output.activationsIndex) invalid(name,"tuple scores/activations indices must be distinct");
            } else if(out.object.contains("scores_index")||out.object.contains("activations_index")) invalid(name,"tensor contract cannot specify tuple indices");
            if(name=="grading") canonicalClasses(out,{"0","1","2","3","4"},s.output.classes);
            else if(out.integer("channels",1,64)!=4) invalid(name,"the current canonical lesion adapter requires 4 output channels");
            const auto cam=f.child("cam");
            if(name=="grading") { cam.keys({"enabled"}); s.camEnabled=cam.boolean("enabled"); }
            else { cam.keys({"enabled_by_default","environment_override"}); s.camEnabled=cam.boolean("enabled_by_default"); const auto environment=cam.value("environment_override"); if(!environment.isString()) invalid(name,"environment_override must be a string"); s.camEnvironment=environment.toString(); }
            if((s.camEnabled||!s.camEnvironment.isEmpty())&&!s.output.tuple) invalid(name,"CAM requires the scores_and_activations contract; use empty environment_override with CAM disabled for tensor-only lesions");
        }
    }
    if(out.object.contains("name")) s.output.name=out.string("name");
    return s;
}
}
QString dtypeName(TensorDtype value) {
    switch(value) { case TensorDtype::Float32:return "float32";case TensorDtype::Float16:return "float16";case TensorDtype::BFloat16:return "bfloat16"; } return {};
}
QString ModelConfig::defaultPath() {
    if(qEnvironmentVariableIsSet("RETINAGRAM_MODEL_CONFIG")) {
        const auto file=qEnvironmentVariable("RETINAGRAM_MODEL_CONFIG");
        if(file.isEmpty()) invalid("root","RETINAGRAM_MODEL_CONFIG is empty");
        return QFileInfo(file).absoluteFilePath();
    }
    QDir dir(QCoreApplication::applicationDirPath());
    for(int i=0;i<5;++i) { const auto path=dir.filePath("config/models.json"); if(QFileInfo(path).isFile()) return path; if(!dir.cdUp()) break; }
    return QDir::current().filePath("config/models.json");
}
ModelConfig ModelConfig::load(QString file,QString checkpoints) {
    if(file.isEmpty()) file=defaultPath();
    QFile input(file); if(!input.open(QIODevice::ReadOnly)) invalid("root","cannot read "+file+": "+input.errorString());
    QJsonParseError error; const auto doc=QJsonDocument::fromJson(input.readAll(),&error);
    if(error.error!=QJsonParseError::NoError||!doc.isObject()) invalid("root","invalid JSON in "+file+": "+error.errorString());
    const Fields root{doc.object(),"root"}; root.keys({"version","checkpoints_directory","iqa","restoration","grading","lesion"});
    if(root.integer("version",1,1)!=1) invalid("root","unsupported version");
    ModelConfig c; c.file=QFileInfo(file).absoluteFilePath();
    const QString configuredDirectory=root.string("checkpoints_directory");
    c.checkpointsDirectory=checkpoints.isEmpty()?QDir(QFileInfo(c.file).absolutePath()).absoluteFilePath(configuredDirectory):QFileInfo(checkpoints).absoluteFilePath();
    c.quality=stage(root,"iqa","onnx_classification",c.checkpointsDirectory);
    c.restoration=stage(root,"restoration","onnx_image_restoration",c.checkpointsDirectory);
    c.grading=stage(root,"grading","torchscript_classifier_cam",c.checkpointsDirectory);
    c.lesion=stage(root,"lesion","torchscript_segmentation_cam",c.checkpointsDirectory);
    const auto lesion=root.child("lesion"); const auto classes=lesion.value("classes");
    if(!classes.isArray()||classes.toArray().size()!=4) invalid("lesion","expected 4 canonical lesion classes");
    QSet<QString> codes; QSet<int> channels;
    const QStringList canonical{"MA","HE","EX","SE"};
    for(const auto& item:classes.toArray()) {
        if(!item.isObject()) invalid("lesion","class must be an object");
        const Fields f{item.toObject(),"lesion.class"}; f.keys({"code","channel","threshold","minimum_area","merge_distance"});
        LesionClassConfig cl; cl.code=f.string("code");
        const int i=static_cast<int>(canonical.indexOf(cl.code));
        if(i<0||codes.contains(cl.code)) invalid("lesion","classes must contain MA, HE, EX, SE exactly once");
        codes.insert(cl.code); cl.channel=f.integer("channel",0,63);
        if(cl.channel>=4) invalid("lesion",QString("class %1 refers to channel %2 but the configured model output contains only 4 channels").arg(cl.code).arg(cl.channel));
        if(channels.contains(cl.channel)) invalid("lesion","channel mapping must be unique"); channels.insert(cl.channel);
        const double threshold=f.number("threshold");
        if(threshold<0||threshold>1) invalid("lesion","threshold must be in [0,1]"); cl.threshold=static_cast<float>(threshold);
        cl.minimumArea=f.number("minimum_area"); cl.mergeDistance=f.number("merge_distance");
        if(cl.minimumArea<0||cl.mergeDistance<0||cl.mergeDistance>64) invalid("lesion","area must be nonnegative and merge_distance must be in [0,64]");
        c.lesionClasses[i]=cl;
    }
    const auto post=lesion.child("postprocessing"); post.keys({"reference_size","connectivity","minimum_mean_probability","overlay_alpha"});
    c.postprocessingReferenceSize=post.number("reference_size");
    if(c.postprocessingReferenceSize<=0||c.postprocessingReferenceSize>8192) invalid("lesion","reference_size must be in (0,8192]");
    // These remain application display invariants for this adapter version.
    if(post.integer("connectivity",4,8)!=8||post.number("minimum_mean_probability")!=0.5||post.number("overlay_alpha")!=0.45) invalid("lesion","this postprocessor requires connectivity 8, minimum_mean_probability 0.5 and overlay_alpha 0.45");
    return c;
}
} // namespace retina::inference
