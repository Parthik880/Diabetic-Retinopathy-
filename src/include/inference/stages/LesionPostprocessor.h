#pragma once
#include "inference/ModelConfig.h"
#include "inference/ModelTypes.h"
namespace retina::inference {
class LesionPostprocessor final {
public:
    LesionPostprocessor(std::array<LesionClassConfig, 4> classes, double referenceSize);
    LesionResult process(const QImage&, const SegmentationProbabilities&,
                         const QString& directory, const ProgressCallback&) const;
private:
    std::array<LesionClassConfig, 4> classes_;
    double referenceSize_;
};
}
