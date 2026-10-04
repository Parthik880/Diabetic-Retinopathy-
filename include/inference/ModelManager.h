#pragma once

#include "inference/ModelTypes.h"
#include <QVariantMap>
#include <QString>

#include <functional>
#include <memory>

// Orchestrates persistent typed stages and the original application's analysis
// routing. Call analyzeImage from a worker thread, never the GUI thread.
class ModelManager final {
public:
    explicit ModelManager(QString checkpointsDirectory = {}, QString configurationFile = {});
    explicit ModelManager(retina::inference::ModelStages stages);
    ~ModelManager();

    ModelManager(const ModelManager&) = delete;
    ModelManager& operator=(const ModelManager&) = delete;

    bool initialize(bool forceContractValidation = false);
    bool isReady() const;
    bool isCudaAvailable() const;
    QString lastError() const;

    // Returns state, image_path, analysis_image_path, restored_image_path,
    // quality, quality_confidence, quality_probabilities, grade,
    // grade_confidence, grade_probabilities, gradcam_path,
    // lesion_overlay_path, lesion_counts, regions, warnings, and error.
    // Terminal state is COMPLETE, RECAPTURE_REQUIRED, or FAILED.
    QVariantMap analyzeImage(
        const QString& eye,
        const QString& imagePath,
        const std::function<void(QString)>& progress = {});

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
