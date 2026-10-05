#pragma once
#include "inference/ModelConfig.h"
#include <QImage>
#include <vector>
#include <span>
namespace retina::inference {
QImage pillowBilinear(const QImage&, int width, int height);
std::vector<float> chwPixels(const QImage&, const InputConfig&);
std::vector<float> preprocess(const QImage&, const InputConfig&);
QImage fromChwPixels(const float*, int width, int height);
QString savePng(const QImage&, const QString& directory, const QString& filename);
QImage probabilityHeatmap(std::span<const float>, int width, int height);
void require(bool condition, const QString& message);
}
