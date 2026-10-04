#include "inference/ModelManager.h"
#include "inference/ModelFactory.h"
#include "inference/ResultSerialization.h"
#include "inference/Preprocessing.h"
#include "image/ImageDecoder.h"
#include <QCoreApplication>
#include <QDir>
#include <QElapsedTimer>
#include <QFileInfo>
#include <QStandardPaths>
#include <QUuid>
#include <mutex>
#include <stdexcept>
using namespace retina::inference;
namespace {
QString errorText(const std::exception& error) {return QString::fromUtf8(error.what());}
QImage decodeImage(const QString& path) {
    QString reason;auto image=retina::loadImage(path,&reason);
    require(!image.isNull(),QString("Cannot decode image: %1 (%2)").arg(path,reason));return image;
}
QVariantMap emptyResult(const QString& imagePath) {
    return {
        {QStringLiteral("state"), QStringLiteral("FAILED")},
        {QStringLiteral("image_path"), imagePath},
        {QStringLiteral("analysis_image_path"), imagePath},
        {QStringLiteral("restored_image_path"), QString()},
        {QStringLiteral("quality"), QString()},
        {QStringLiteral("quality_confidence"), 0.0},
        {QStringLiteral("quality_probabilities"), QVariantList{}},
        {QStringLiteral("grade"), -1},
        {QStringLiteral("grade_confidence"), 0.0},
        {QStringLiteral("grade_probabilities"), QVariantList{}},
        {QStringLiteral("gradcam_path"), QString()},
        {QStringLiteral("lesion_overlay_path"), QString()},
        {QStringLiteral("lesion_counts"), QVariantMap{}},
        {QStringLiteral("regions"), QVariantList{}},
        {QStringLiteral("warnings"), QStringList{}},
        {QStringLiteral("error"), QString()}
    };
}


} // namespace
struct ModelManager::Impl {
    QString checkpointsDirectory,configurationFile,error;
    ModelStages stages;
    bool ready=false;
    mutable std::mutex mutex;
    Impl(QString directory,QString file):checkpointsDirectory(std::move(directory)),configurationFile(std::move(file)) {}
    explicit Impl(ModelStages models):stages(std::move(models)) {
        require(stages.quality&&stages.restoration&&stages.grading&&stages.lesion,"All four model stages must be supplied");ready=true;
    }
    bool initialize(bool forceContractValidation=false) {
        if(ready) return true;
        error.clear();
        try {
            const auto config=ModelConfig::load(configurationFile,checkpointsDirectory);
            stages=ModelFactory::create(config,forceContractValidation);ready=true;
        } catch(const std::exception& exception) {stages={};error=errorText(exception);ready=false;}
        return ready;
    }
};
ModelManager::ModelManager(QString checkpointsDirectory, QString configurationFile)
    : impl_(std::make_unique<Impl>(std::move(checkpointsDirectory),std::move(configurationFile))) {}
ModelManager::ModelManager(retina::inference::ModelStages stages)
    : impl_(std::make_unique<Impl>(std::move(stages))) {}

ModelManager::~ModelManager() = default;

bool ModelManager::initialize(bool forceContractValidation) {
    std::lock_guard guard(impl_->mutex);
    return impl_->initialize(forceContractValidation);
}

bool ModelManager::isReady() const {
    std::lock_guard guard(impl_->mutex);
    return impl_->ready;
}

bool ModelManager::isCudaAvailable() const {
    std::lock_guard guard(impl_->mutex);
    return impl_->stages.cuda;
}

QString ModelManager::lastError() const {
    std::lock_guard guard(impl_->mutex);
    return impl_->error;
}

QVariantMap ModelManager::analyzeImage(
    const QString& eye, const QString& imagePath,
    const std::function<void(QString)>& progress) {
    std::lock_guard guard(impl_->mutex);
    QVariantMap result = emptyResult(imagePath);
    result.insert(QStringLiteral("eye"), eye);
    result.insert(QStringLiteral("device"), impl_->stages.cuda ? QStringLiteral("CUDA") : QStringLiteral("CPU"));
    QStringList warnings;
    QVariantMap timings;
    QElapsedTimer stageTimer;
    try {
        require(impl_->initialize(), impl_->error);
        result.insert(QStringLiteral("device"), impl_->stages.cuda ? QStringLiteral("CUDA") : QStringLiteral("CPU"));
        result.insert(QStringLiteral("onnx_provider"), impl_->stages.ortCuda ? QStringLiteral("CUDA") : QStringLiteral("CPU"));
        const QFileInfo imageFile(imagePath);
        require(imageFile.isFile(), QStringLiteral("Image does not exist: %1").arg(imagePath));
        const QString extension = imageFile.suffix().toLower();
        require(QStringList{QStringLiteral("jpg"), QStringLiteral("jpeg"), QStringLiteral("png"),
                            QStringLiteral("bmp"), QStringLiteral("tif"), QStringLiteral("tiff")}.contains(extension),
            QStringLiteral("Unsupported image format: %1").arg(extension));
        require(imageFile.size() <= 20 * 1024 * 1024,
            QStringLiteral("Image exceeds the 20 MiB upload limit"));
        const QImage original = decodeImage(imageFile.absoluteFilePath());
        require(static_cast<qint64>(original.width()) * original.height() <= 16'000'000,
            QStringLiteral("Image exceeds the 16 megapixel limit"));
        result.insert(QStringLiteral("image_path"), imageFile.absoluteFilePath());
        result.insert(QStringLiteral("analysis_image_path"), imageFile.absoluteFilePath());
        result.insert(QStringLiteral("image_width"), original.width());
        result.insert(QStringLiteral("image_height"), original.height());

        if (progress) progress(QStringLiteral("IQA"));
        stageTimer.start();
        const auto qualityResult = impl_->stages.quality->infer(original);
        const int quality = static_cast<int>(qualityResult.quality);
        const auto& qualityScores = qualityResult.probabilities;
        timings.insert(QStringLiteral("iqa_ms"), stageTimer.elapsed());
        const std::array<QString, 3> qualityNames{
            QStringLiteral("Good"), QStringLiteral("Usable"), QStringLiteral("Reject")};
        result.insert(QStringLiteral("quality"), qualityNames[quality]);
        result.insert(QStringLiteral("quality_confidence"), qualityScores[quality]);
        QVariantList qualityProbabilities;
        for (float value : qualityScores) qualityProbabilities << value;
        result.insert(QStringLiteral("quality_probabilities"), qualityProbabilities);
        result.insert(QStringLiteral("analysis_source"), QStringLiteral("original"));

        if (quality == 2) {
            if (progress) progress(QStringLiteral("IQA_REJECTED"));
            warnings << QStringLiteral("IQA rejected this image. Recapture is required; restoration, grading, and lesion analysis were not run.");
            result.insert(QStringLiteral("state"), QStringLiteral("RECAPTURE_REQUIRED"));
            result.insert(QStringLiteral("warnings"), warnings);
            result.insert(QStringLiteral("timing_ms"), timings);
            return result;
        }

        if (progress) progress(quality == 0 ? QStringLiteral("IQA_GOOD") : QStringLiteral("IQA_USABLE"));
        QString baseOutput = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
        if (baseOutput.isEmpty()) baseOutput = QDir::tempPath();
        const QString runDirectory = QDir(baseOutput).filePath(
            QStringLiteral("runs/") + QUuid::createUuid().toString(QUuid::WithoutBraces));
        require(QDir().mkpath(runDirectory),
            QStringLiteral("Cannot create analysis directory: %1").arg(runDirectory));

        QImage analysis = original;
        if (quality == 1) {
            if (progress) progress(QStringLiteral("RESTORING"));
            stageTimer.restart();
            const auto restored = impl_->stages.restoration->infer(original);
            analysis = restored.image;
            timings.insert(QStringLiteral("nafnet_forward_ms"),restored.forwardMs);
            const QString restoredPath = savePng(analysis, runDirectory,
                QStringLiteral("restored.png"));
            result.insert(QStringLiteral("restored_image_path"), restoredPath);
            result.insert(QStringLiteral("analysis_image_path"), restoredPath);
            result.insert(QStringLiteral("analysis_source"), QStringLiteral("restored"));
            warnings << QStringLiteral("IQA marked the image usable; downstream models ran on the NAFNet-restored image.");
            timings.insert(QStringLiteral("nafnet_and_save_ms"), stageTimer.elapsed());
            if (progress) progress(QStringLiteral("RESTORATION_COMPLETE"));
        }

        if (progress) progress(QStringLiteral("GRADING"));
        stageTimer.restart();
        const auto grading = impl_->stages.grading->infer(analysis,runDirectory);
        const auto grade = grading.grade;
        const auto& gradeScores = grading.probabilities;
        const auto& gradeCamPath = grading.camPath;
        warnings.append(grading.warnings);
        timings.insert(QStringLiteral("grading_forward_ms"),grading.forwardMs);
        timings.insert(QStringLiteral("gradcam_generation_ms"),grading.camMs);
        result.insert(QStringLiteral("grade"), grade);
        result.insert(QStringLiteral("grade_confidence"), gradeScores[grade]);
        QVariantList gradeProbabilities;
        for (float value : gradeScores) gradeProbabilities << value;
        result.insert(QStringLiteral("grade_probabilities"), gradeProbabilities);
        result.insert(QStringLiteral("gradcam_path"), gradeCamPath);
        timings.insert(QStringLiteral("grading_and_cam_ms"), stageTimer.elapsed());

        if (progress) progress(QStringLiteral("LESION_ANALYSIS"));
        stageTimer.restart();
        const auto lesions = impl_->stages.lesion->infer(analysis,runDirectory,progress);
        const auto fields = lesionResultFields(lesions);
        for(auto it=fields.begin();it!=fields.end();++it) result.insert(it.key(),it.value());
        warnings.append(lesions.warnings);
        timings.insert(QStringLiteral("lesion_forward_and_transfer_ms"),lesions.forwardAndTransferMs);
        timings.insert(QStringLiteral("lesions_and_visualization_ms"), stageTimer.elapsed());
        warnings << QStringLiteral("Lesion region scores are mean pixel probabilities, not clinical confidence or severity.");
        if (progress) progress(QStringLiteral("PREPARING_RESULTS"));
        result.insert(QStringLiteral("warnings"), warnings);
        result.insert(QStringLiteral("timing_ms"), timings);
        result.insert(QStringLiteral("state"), QStringLiteral("COMPLETE"));
        if (progress) progress(QStringLiteral("COMPLETE"));
    } catch (const std::exception& exception) {
        impl_->error = errorText(exception);
        result.insert(QStringLiteral("warnings"), warnings);
        result.insert(QStringLiteral("timing_ms"), timings);
        result.insert(QStringLiteral("state"), QStringLiteral("FAILED"));
        result.insert(QStringLiteral("error"), impl_->error);
        if (progress) progress(QStringLiteral("FAILED"));
    }
    return result;
}

