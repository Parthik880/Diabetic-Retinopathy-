#include "inference/Preprocessing.h"
#include <QColor>
#include <QDir>
#include <QFileInfo>
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace retina::inference {
void require(bool condition,const QString& message) { if(!condition) throw std::runtime_error(message.toStdString()); }
std::vector<std::vector<std::pair<int, float>>> resizeWeights(int source, int target) {
    const double ratio = static_cast<double>(source) / target;
    const double filterScale = std::max(1.0, ratio);
    std::vector<std::vector<std::pair<int, float>>> weights(target);
    for (int out = 0; out < target; ++out) {
        const double center = (out + 0.5) * ratio;
        const int first = std::max(0, static_cast<int>(std::floor(center - filterScale + 0.5)));
        const int last = std::min(source, static_cast<int>(std::floor(center + filterScale + 0.5)));
        double sum = 0.0;
        for (int i = first; i < last; ++i) {
            const double distance = std::abs((i - center + 0.5) / filterScale);
            const float w = static_cast<float>(std::max(0.0, 1.0 - distance));
            if (w > 0.0f) {
                weights[out].emplace_back(i, w);
                sum += w;
            }
        }
        require(sum > 0.0, QStringLiteral("Image resize failed to find source pixels"));
        for (auto& entry : weights[out]) entry.second = static_cast<float>(entry.second / sum);
    }
    return weights;
}

QImage pillowBilinear(const QImage& source, int width, int height) {
    require(width > 0 && height > 0, QStringLiteral("Invalid resize dimensions"));
    if (source.width() == width && source.height() == height) return source;
    const QImage rgb = source.convertToFormat(QImage::Format_RGB888);
    const auto horizontal = resizeWeights(rgb.width(), width);
    const auto vertical = resizeWeights(rgb.height(), height);
    QImage intermediate(width, rgb.height(), QImage::Format_RGB888);
    for (int y = 0; y < rgb.height(); ++y) {
        const auto* src = rgb.constScanLine(y);
        auto* dst = intermediate.scanLine(y);
        for (int x = 0; x < width; ++x) {
            for (int c = 0; c < 3; ++c) {
                double value = 0;
                for (const auto& [input, weight] : horizontal[x]) value += src[3 * input + c] * weight;
                dst[3 * x + c] = static_cast<uchar>(std::clamp(std::lround(value), 0L, 255L));
            }
        }
    }
    QImage output(width, height, QImage::Format_RGB888);
    for (int y = 0; y < height; ++y) {
        auto* dst = output.scanLine(y);
        for (int x = 0; x < width; ++x) {
            for (int c = 0; c < 3; ++c) {
                double value = 0;
                for (const auto& [input, weight] : vertical[y]) {
                    value += intermediate.constScanLine(input)[3 * x + c] * weight;
                }
                dst[3 * x + c] = static_cast<uchar>(std::clamp(std::lround(value), 0L, 255L));
            }
        }
    }
    return output;
}

std::vector<float> chwPixels(const QImage& image, const InputConfig& config) {
    const int height = image.height(), width = image.width();
    std::vector<float> result(static_cast<size_t>(3) * height * width);
    for (int y = 0; y < height; ++y) {
        const auto* row = image.constScanLine(y);
        for (int x = 0; x < width; ++x) {
            for (int channel = 0; channel < 3; ++channel) {
                float value = static_cast<float>(row[3 * x + channel]) / 255.0f;
                if (config.normalize) value = (value - config.mean[channel]) / config.std[channel];
                result[(static_cast<size_t>(channel) * height + y) * width + x] = value;
            }
        }
    }
    return result;
}

QImage fromChwPixels(const float* pixels, int width, int height) {
    QImage image(width, height, QImage::Format_RGB888);
    for (int y = 0; y < height; ++y) {
        auto* row = image.scanLine(y);
        for (int x = 0; x < width; ++x) {
            for (int channel = 0; channel < 3; ++channel) {
                const float value = std::clamp(pixels[(static_cast<size_t>(channel) * height + y) * width + x], 0.0f, 1.0f);
                row[3 * x + channel] = static_cast<uchar>(std::clamp(std::nearbyint(value * 255.0f), 0.0f, 255.0f));
            }
        }
    }
    return image;
}

QColor jet(float value) {
    const float x = std::clamp(value, 0.0f, 1.0f);
    const auto channel = [](float t) { return static_cast<int>(std::lround(255.0f * std::clamp(t, 0.0f, 1.0f))); };
    return QColor(channel(1.5f - std::abs(4.0f * x - 3.0f)),
                  channel(1.5f - std::abs(4.0f * x - 2.0f)),
                  channel(1.5f - std::abs(4.0f * x - 1.0f)));
}

QString savePng(const QImage& image, const QString& directory, const QString& filename) {
    require(QDir().mkpath(directory), QStringLiteral("Cannot create output directory: %1").arg(directory));
    const QString path = QDir(directory).filePath(filename);
    require(image.save(path, "PNG"), QStringLiteral("Cannot write image: %1").arg(path));
    return QFileInfo(path).absoluteFilePath();
}


std::vector<float> preprocess(const QImage& image,const InputConfig& config) {
    return chwPixels(pillowBilinear(image,config.width,config.height),config);
}
QImage probabilityHeatmap(std::span<const float> values,int width,int height) {
    require(values.size()==static_cast<size_t>(width)*height,"Probability map has an unexpected shape");
    QImage image(width,height,QImage::Format_RGB888);
    for(int y=0;y<height;++y) {
        auto* row=image.scanLine(y);
        for(int x=0;x<width;++x) {
            const QColor color=jet(values[static_cast<size_t>(y)*width+x]);
            row[3*x]=static_cast<uchar>(color.red()); row[3*x+1]=static_cast<uchar>(color.green()); row[3*x+2]=static_cast<uchar>(color.blue());
        }
    }
    return image;
}
} // namespace retina::inference
