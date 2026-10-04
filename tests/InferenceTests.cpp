#include "inference/ModelConfig.h"
#include "inference/ModelManager.h"
#include "inference/stages/LesionPostprocessor.h"
#include <QTest>
#include <QTemporaryDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QStandardPaths>
#include <stdexcept>
using namespace retina::inference;
namespace {
struct Calls {int quality=0,restoration=0,grade=0,lesion=0;QImage gradeInput,lesionInput;};
class QualityStub final:public IQualityModel {
    Calls& calls_;Quality quality_;
public: QualityStub(Calls& calls,Quality quality):calls_(calls),quality_(quality) {}
    QualityResult infer(const QImage&) override {++calls_.quality;QualityResult r;r.quality=quality_;r.label=QStringList{"Good","Usable","Reject"}[static_cast<int>(quality_)];r.probabilities[static_cast<int>(quality_)]=1;r.confidence=1;return r;}
};
class RestorationStub final:public IRestorationModel {
    Calls& calls_;
public: explicit RestorationStub(Calls& calls):calls_(calls) {}
    RestorationResult infer(const QImage& image) override {++calls_.restoration;QImage restored=image;restored.fill(QColor(10,20,30));return {restored,0};}
};
class GradeStub final:public IGradingModel {
    Calls& calls_;
public: explicit GradeStub(Calls& calls):calls_(calls) {}
    GradeResult infer(const QImage& image,const QString&) override {++calls_.grade;calls_.gradeInput=image;GradeResult r;r.grade=2;r.probabilities[2]=1;r.confidence=1;return r;}
};
class LesionStub final:public ILesionModel {
    Calls& calls_;
public: explicit LesionStub(Calls& calls):calls_(calls) {}
    LesionResult infer(const QImage& image,const QString&,const ProgressCallback&) override {++calls_.lesion;calls_.lesionInput=image;LesionResult r;for(int i=0;i<4;++i) r.channels[i].code=lesionCodes[i];return r;}
};
ModelStages stubs(Calls& calls,Quality quality) {
    ModelStages s;s.quality=std::make_unique<QualityStub>(calls,quality);s.restoration=std::make_unique<RestorationStub>(calls);s.grading=std::make_unique<GradeStub>(calls);s.lesion=std::make_unique<LesionStub>(calls);return s;
}
}
class InferenceTests:public QObject {
    Q_OBJECT
    ModelConfig production_;
    QJsonObject json_;
    void invalidConfig(QJsonObject json,const QString& expected) {
        QTemporaryDir dir;QVERIFY(dir.isValid());QFile file(dir.filePath("models.json"));QVERIFY(file.open(QIODevice::WriteOnly));
        json["checkpoints_directory"]=production_.checkpointsDirectory;file.write(QJsonDocument(json).toJson());file.close();
        try {ModelConfig::load(file.fileName());QFAIL("Invalid configuration was accepted");}
        catch(const std::exception& error) {QVERIFY2(QString::fromUtf8(error.what()).contains(expected),error.what());}
    }
private slots:
    void initTestCase() {
        QCoreApplication::setOrganizationName("RetinaGramValidation");QCoreApplication::setApplicationName("InferenceTests");QStandardPaths::setTestModeEnabled(true);
        production_=ModelConfig::load();QFile file(production_.file);QVERIFY(file.open(QIODevice::ReadOnly));json_=QJsonDocument::fromJson(file.readAll()).object();
    }
    void productionConfig() {
        QCOMPARE(production_.quality.adapter,QString("onnx_classification"));QCOMPARE(production_.quality.model,QString("iqa_int8.onnx"));
        QCOMPARE(production_.restoration.model,QString("nafnet_fp16.onnx"));QVERIFY(production_.restoration.input.dynamicSpatial);
        QCOMPARE(production_.grading.model,QString("grade_bf16_cam.pt"));QCOMPARE(production_.grading.input.dtype,TensorDtype::BFloat16);
        QCOMPARE(production_.lesion.model,QString("lesion_bf16_cam.pt"));QCOMPARE(production_.lesion.input.width,768);
        QCOMPARE(production_.quality.output.classes,QStringList({"Good","Usable","Reject"}));QVERIFY(production_.grading.camEnabled);QVERIFY(!production_.lesion.camEnabled);
    }
    void missingModel() {auto json=json_;auto stage=json["grading"].toObject();stage["model"]="missing_test_model.pt";json["grading"]=stage;invalidConfig(json,"required model is missing");}
    void invalidQualityClassCount() {auto json=json_;auto stage=json["iqa"].toObject();auto out=stage["output"].toObject();out["classes"]=QJsonArray{"Good","Reject"};stage["output"]=out;json["iqa"]=stage;invalidConfig(json,"expected 3 class labels but 2");}
    void missingNormalization() {auto json=json_;auto stage=json["grading"].toObject();auto in=stage["input"].toObject();auto norm=in["normalization"].toObject();norm.remove("std");in["normalization"]=norm;stage["input"]=in;json["grading"]=stage;invalidConfig(json,"missing required field 'std'");}
    void badLesionChannel() {auto json=json_;auto stage=json["lesion"].toObject();auto classes=stage["classes"].toArray();auto he=classes[1].toObject();he["channel"]=5;classes[1]=he;stage["classes"]=classes;json["lesion"]=stage;invalidConfig(json,"HE refers to channel 5");}
    void reorderedLesionMapping() {
        auto json=json_;auto stage=json["lesion"].toObject();auto classes=stage["classes"].toArray();
        for(int i=0;i<4;++i) {auto entry=classes[i].toObject();entry["channel"]=3-i;classes[i]=entry;}stage["classes"]=classes;json["lesion"]=stage;
        QTemporaryDir dir;QFile file(dir.filePath("models.json"));QVERIFY(file.open(QIODevice::WriteOnly));json["checkpoints_directory"]=production_.checkpointsDirectory;file.write(QJsonDocument(json).toJson());file.close();
        const auto config=ModelConfig::load(file.fileName());for(int i=0;i<4;++i) {QCOMPARE(config.lesionClasses[i].code,lesionCodes[i]);QCOMPARE(config.lesionClasses[i].channel,3-i);}
    }
    void routing_data() {QTest::addColumn<int>("quality");QTest::newRow("Good")<<0;QTest::newRow("Usable")<<1;QTest::newRow("Reject")<<2;}
    void routing() {
        QFETCH(int,quality);QTemporaryDir dir;QImage original(32,32,QImage::Format_RGB888);original.fill(QColor(100,110,120));const auto path=dir.filePath("scan.png");QVERIFY(original.save(path));
        Calls calls;ModelManager manager(stubs(calls,static_cast<Quality>(quality)));QStringList progress;const auto result=manager.analyzeImage("OS",path,[&](QString step){progress<<step;});
        QCOMPARE(calls.quality,1);QCOMPARE(calls.restoration,quality==1?1:0);QCOMPARE(calls.grade,quality==2?0:1);QCOMPARE(calls.lesion,quality==2?0:1);
        QCOMPARE(result.value("state").toString(),quality==2?QString("RECAPTURE_REQUIRED"):QString("COMPLETE"));
        if(quality==2) {QCOMPARE(result.value("grade").toInt(),-1);QVERIFY(result.value("restored_image_path").toString().isEmpty());QVERIFY(!progress.contains("GRADING"));}
        else {QCOMPARE(calls.gradeInput,calls.lesionInput);QCOMPARE(calls.gradeInput.pixelColor(0,0),quality==1?QColor(10,20,30):QColor(100,110,120));QCOMPARE(result.value("analysis_source").toString(),quality==1?QString("restored"):QString("original"));if(quality==1) QVERIFY(QFileInfo::exists(result.value("restored_image_path").toString()));}
    }
    void fullMaskAndDisplayFiltering() {
        QImage image(8,8,QImage::Format_RGB888);image.fill(Qt::black);std::array<std::vector<float>,4> values;SegmentationProbabilities planes;planes.width=8;planes.height=8;
        for(int i=0;i<4;++i) {values[i].assign(64,0);planes.channels[i]=values[i];}
        values[0][0]=0.5f;values[0][9]=0.8f; // 8-connected, including equality at threshold.
        auto classes=production_.lesionClasses;classes[0].minimumArea=3;
        QTemporaryDir dir;LesionPostprocessor post(classes,8);auto result=post.process(image,planes,dir.path(),{});
        QCOMPARE(result.channels[0].rawRegions.size(),size_t(1));QCOMPARE(result.channels[0].rawRegions[0].area,2);QVERIFY(result.channels[0].regions.empty());
        QCOMPARE(result.channels[0].binaryMask[0],uchar(1));QCOMPARE(result.channels[0].binaryMask[9],uchar(1));
    }
};
QTEST_GUILESS_MAIN(InferenceTests)
#include "InferenceTests.moc"
