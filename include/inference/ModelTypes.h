#pragma once

#include <QImage>
#include <QStringList>
#include <array>
#include <functional>
#include <memory>
#include <span>
#include <vector>

namespace retina::inference {
using ProgressCallback = std::function<void(QString)>;
inline const std::array<QString, 4> lesionCodes{"MA", "HE", "EX", "SE"};
enum class Quality { Good, Usable, Reject };
struct QualityResult {
    Quality quality = Quality::Reject;
    QString label;
    float confidence = 0;
    std::array<float, 3> probabilities{}; // Always Good, Usable, Reject.
};
struct RestorationResult { QImage image; qint64 forwardMs = 0; };
struct GradeResult {
    int grade = -1;
    float confidence = 0;
    std::array<float, 5> probabilities{}; // Always grades 0..4.
    QString camPath;
    QStringList warnings;
    qint64 forwardMs = 0, camMs = 0;
};
struct LesionRegion {
    QString code;
    int rank = 0, xMin = 0, yMin = 0, xMax = 0, yMax = 0, area = 0;
    int centerX = 0, centerY = 0;
    double centroidX = 0, centroidY = 0, modelArea = 0, meanProbability = 0;
    float maximumProbability = 0;
    std::vector<int> sourceIds;
};
struct LesionChannelResult {
    QString code, maskPath, probabilityPath, camPath;
    std::vector<uchar> binaryMask; // Full threshold mask, before display filtering.
    std::vector<LesionRegion> regions, rawRegions;
};
struct LesionResult {
    std::array<LesionChannelResult, 4> channels;
    QString overlayPath, heatmapPath;
    QStringList warnings;
    qint64 forwardAndTransferMs = 0;
};
// Borrowed FP32 CPU planes, in canonical MA/HE/EX/SE order. The adapter owns
// their storage for the duration of postprocessing; no runtime tensor leaks out.
struct SegmentationProbabilities {
    int width = 0, height = 0;
    std::array<std::span<const float>, 4> channels;
};
class IQualityModel { public: virtual ~IQualityModel() = default; virtual QualityResult infer(const QImage&) = 0; };
class IRestorationModel { public: virtual ~IRestorationModel() = default; virtual RestorationResult infer(const QImage&) = 0; };
class IGradingModel { public: virtual ~IGradingModel() = default; virtual GradeResult infer(const QImage&, const QString& directory) = 0; };
class ILesionModel { public: virtual ~ILesionModel() = default; virtual LesionResult infer(const QImage&, const QString& directory, const ProgressCallback&) = 0; };
struct ModelStages {
    std::unique_ptr<IQualityModel> quality;
    std::unique_ptr<IRestorationModel> restoration;
    std::unique_ptr<IGradingModel> grading;
    std::unique_ptr<ILesionModel> lesion;
    bool cuda = false, ortCuda = false;
};
} // namespace retina::inference
