#include "reporting/ReportBundle.h"
#include "reporting/ScreeningReport.h"
#include <QTest>
#include <QTemporaryDir>
#include <QFile>
#include <QDir>
#include <QImageReader>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QCryptographicHash>
#include <limits>

using namespace retina::reporting;
class ReportBundleTests : public QObject {
    Q_OBJECT
    QTemporaryDir sources_, fallbackOutput_;
    QVariantMap good_, usable_;
    QString output_;
    const QDateTime time_=QDateTime::fromString("2026-10-04T19:48:12+05:30",Qt::ISODate);
    QByteArray bytes(const QString &path) {
        QFile file(path); if(!file.open(QIODevice::ReadOnly)) return {}; return file.readAll();
    }
    QJsonObject json(const QString &eyeFolder) {
        return QJsonDocument::fromJson(bytes(QDir(eyeFolder).filePath("results.json"))).object();
    }
    void checkBundle(const ReportExportResult &exported,const QVariantMap &native,bool restored) {
        const QDir dir(exported.eyeFolder);
        QCOMPARE(exported.files.size(),restored?9:8);
        QCOMPARE(bytes(exported.reportPath).left(5),QByteArray("%PDF-"));
        const auto structured=json(exported.eyeFolder); QVERIFY(!structured.isEmpty());
        QCOMPARE(structured["patient"].toObject()["name"].toString(),QString("Birds"));
        QCOMPARE(structured["patient"].toObject()["id"].toString(),QString("RG-EXPORT-1"));
        QCOMPARE(structured["patient"].toObject()["eye"].toString(),native.value("report_patient").toMap().value("eye").toString());
        QCOMPARE(structured["image_quality"].toObject()["class"].toString(),native.value("quality").toString());
        QCOMPARE(structured["image_quality"].toObject()["confidence"].toDouble(),native.value("quality_confidence").toDouble());
        QCOMPARE(structured["dr_grading"].toObject()["grade"].toInt(),native.value("grade").toInt());
        QCOMPARE(structured["dr_grading"].toObject()["confidence"].toDouble(),native.value("grade_confidence").toDouble());
        QCOMPARE(structured["dr_grading"].toObject()["probabilities"].toArray(),QJsonArray::fromVariantList(native.value("grade_probabilities").toList()));
        QCOMPARE(structured["pipeline_state"].toString(),QString("COMPLETE"));
        QCOMPARE(structured["inference_device"].toString(),native.value("device").toString());
        QCOMPARE(structured["analysis_source"].toString(),native.value("analysis_source").toString());
        QVERIFY(QDateTime::fromString(structured["generated_at"].toString(),Qt::ISODateWithMs).isValid());
        QCOMPARE(structured["original_image_file"].toString(),QString("original_fundus.jpg"));
        QImageReader jpeg(dir.filePath("original_fundus.jpg")); QCOMPARE(jpeg.format(),QByteArray("jpeg"));
        const auto original=jpeg.read(); QVERIFY(!original.isNull()); QCOMPARE(original.size(),QImage(native.value("image_path").toString()).size());
        QCOMPARE(QFileInfo::exists(dir.filePath("restored_fundus.png")),restored);
        if(restored) {
            QCOMPARE(structured["restored_image_file"].toString(),QString("restored_fundus.png"));
            QCOMPARE(bytes(dir.filePath("restored_fundus.png")),bytes(native.value("restored_image_path").toString()));
        } else QVERIFY(structured["restored_image_file"].isNull());
        QCOMPARE(bytes(dir.filePath("lesion_overlay.png")),bytes(native.value("lesion_overlay_path").toString()));
        const QStringList codes{"MA","HE","EX","SE"},names{"microaneurysm.png","hemorrhage.png","hard_exudate.png","soft_exudate.png"};
        const Data report(native);
        for(int i=0;i<4;++i) {
            const auto relative="masks/"+names[i];const auto lesion=structured["lesions"].toObject()[codes[i]].toObject();
            QCOMPARE(lesion["mask_file"].toString(),relative); QCOMPARE(lesion["detected"].toBool(),report.lesions[i]==1);
            QCOMPARE(lesion["region_count"].toInt(),native.value("lesion_counts").toMap().value(codes[i]).toInt());
            QCOMPARE(bytes(dir.filePath(relative)),bytes(native.value("lesion_mask_paths").toMap().value(codes[i]).toString()));
            QCOMPARE(QImage(dir.filePath(relative)).size(),original.size());
        }
        const auto paths=dir.entryList(QDir::Files); QVERIFY(!paths.contains("grade_gradcam.png"));
        QVERIFY(!paths.contains("MA_probability.png"));
    }
private slots:
    void initTestCase() {
        QVERIFY(sources_.isValid()); QVERIFY(fallbackOutput_.isValid());
        output_=qEnvironmentVariable("RETINAGRAM_REPORT_OUTPUT",fallbackOutput_.path()); QVERIFY(QDir().mkpath(output_));
        auto read=[&](const char *environment) {return QJsonDocument::fromJson(bytes(qEnvironmentVariable(environment))).toVariant().toMap();};
        good_=read("RETINAGRAM_GOOD_RESULT"); usable_=read("RETINAGRAM_USABLE_RESULT");
        if(good_.isEmpty()||usable_.isEmpty()) {
            QImage image(32,24,QImage::Format_RGB888);image.fill(QColor(110,80,30));const auto original=sources_.filePath("scan.png");QVERIFY(image.save(original));
            QImage mask(image.size(),QImage::Format_Grayscale8);mask.fill(0);mask.setPixelColor(0,0,Qt::white);
            QVariantMap masks;for(const auto &code:lesionCodes) {const auto path=sources_.filePath(code+".png");QVERIFY(mask.save(path));masks[code]=path;}
            good_={{"state","COMPLETE"},{"image_path",original},{"quality","Good"},{"quality_confidence",0.97},{"quality_probabilities",QVariantList{0.97,0.02,0.01}},
                {"grade",3},{"grade_confidence",0.93},{"grade_probabilities",QVariantList{0.01,0.01,0.04,0.93,0.01}},
                {"device","CPU"},{"analysis_source","original"},{"lesion_overlay_path",original},{"lesion_mask_paths",masks},
                {"lesion_counts",QVariantMap{{"MA",1},{"HE",1},{"EX",1},{"SE",1}}}};
            usable_=good_;usable_["quality"]="Usable";usable_["analysis_source"]="restored";usable_["restored_image_path"]=original;
        }
        const QVariantMap patient{{"name","Birds"},{"patientIdNumber","RG-EXPORT-1"},{"age",58},{"gender","Female"}};
        good_=withContext(good_,patient,"OD",time_); usable_=withContext(usable_,patient,"OS",time_);
    }
    void safeNames() {
        QCOMPARE(sanitizeWindowsName("  ..Birds < > : \" / \\ | ? * \t. "),QString("Birds"));
        QCOMPARE(sanitizeWindowsName("<>:\"/\\|?* \n..."),QString("Patient"));
        QCOMPARE(sanitizeWindowsName(QString(90,'A')).size(),64);
    }
    void goodSingleEye() {checkBundle(exportReportBundle(output_,good_,time_),good_,false);}
    void usableSingleEye() {checkBundle(exportReportBundle(output_,usable_,time_.addSecs(1)),usable_,true);}
    void bilateral() {
        const auto exported=exportReportBundles(output_,{usable_,good_},time_.addSecs(2));
        QCOMPARE(exported.eyes.size(),2);QCOMPARE(exported.files.size(),17);
        QCOMPARE(QDir(exported.rootFolder).entryList(QDir::Dirs|QDir::NoDotAndDotDot),QStringList({"Left_OS","Right_OD"}));
        checkBundle(exported.eyes[0],usable_,true);checkBundle(exported.eyes[1],good_,false);
    }
    void collisionPreservesPrevious() {
        QTemporaryDir parent;const auto a=exportReportBundle(parent.path(),good_,time_);const auto old=bytes(a.reportPath);
        const auto b=exportReportBundle(parent.path(),good_,time_);QCOMPARE(b.rootFolder,a.rootFolder+"_2");QCOMPARE(bytes(a.reportPath),old);
    }
    void fullMaskIndependentOfDisplayCount() {
        auto value=good_;value["lesion_counts"]=QVariantMap{{"MA",0},{"HE",0},{"EX",0},{"SE",0}};
        QTemporaryDir parent;const auto exported=exportReportBundle(parent.path(),value,time_);
        for(const auto &code:lesionCodes) {
            const auto lesion=json(exported.eyeFolder)["lesions"].toObject()[code].toObject();
            QCOMPARE(lesion["detected"].toBool(),Data(good_).lesions[lesionCodes.indexOf(code)]==1);QCOMPARE(lesion["region_count"].toInt(),0);
        }
    }
    void invalidExportsLeaveNoRoot() {
        QTemporaryDir parent;
        auto invalid=[&](QList<QVariantMap> results,QString expected) {
            try {exportReportBundles(parent.path(),results,time_);QFAIL("Invalid export was accepted");}
            catch(const std::exception &error) {QVERIFY2(QString::fromUtf8(error.what()).contains(expected),error.what());}
            QVERIFY(QDir(parent.path()).entryList(QDir::Dirs|QDir::NoDotAndDotDot).isEmpty());
        };
        auto bad=usable_;bad["state"]="FAILED";invalid({good_,bad},"completed");
        bad=good_;bad["image_path"]=parent.filePath("missing.png");invalid({bad},"Original retinal image");
        bad=good_;bad["grade_confidence"]=std::numeric_limits<double>::quiet_NaN();invalid({bad},"non-finite");
        invalid({good_,good_},"only once");
        try {exportReportBundle(parent.filePath("missing"),good_,time_);QFAIL("Missing destination accepted");}
        catch(const std::exception &error) {QVERIFY(QString::fromUtf8(error.what()).contains("destination"));}
    }
};
QTEST_MAIN(ReportBundleTests)
#include "ReportBundleTests.moc"
