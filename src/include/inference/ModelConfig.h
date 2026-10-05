#pragma once
#include <QStringList>
#include <array>

namespace retina::inference {
enum class TensorDtype { Float32, Float16, BFloat16 };
struct InputConfig {
    int width = 0, height = 0;
    bool dynamicSpatial = false, normalize = false;
    TensorDtype dtype = TensorDtype::Float32;
    std::array<float, 3> mean{}, std{};
    QString name;
    QStringList acceptedDtypes;
};
struct OutputConfig {
    bool probabilities = false, tuple = false;
    int scoresIndex = 0, activationsIndex = 1;
    QString name;
    QStringList classes;
};
struct StageConfig {
    QString stage, adapter, model, path;
    InputConfig input;
    OutputConfig output;
    bool camEnabled = false;
    QString camEnvironment;
};
struct LesionClassConfig {
    QString code;
    int channel = 0;
    float threshold = 0.5f;
    double minimumArea = 0, mergeDistance = 0;
};
struct ModelConfig {
    QString file, checkpointsDirectory, applicationRoot;
    StageConfig quality, restoration, grading, lesion;
    std::array<LesionClassConfig, 4> lesionClasses; // Canonical order, mapping in channel.
    double postprocessingReferenceSize = 768;
    static QString defaultPath();
    static ModelConfig load(QString file = {}, QString checkpointsDirectory = {});
};
QString dtypeName(TensorDtype dtype);
} // namespace retina::inference
