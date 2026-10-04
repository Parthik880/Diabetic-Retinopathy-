#include "inference/stages/LesionPostprocessor.h"
#include "inference/Preprocessing.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>
namespace retina::inference {
namespace {
constexpr std::array<std::array<int,3>,4> colors{{{255,45,45},{255,126,34},{255,224,32},{35,210,255}}};
struct Region {
    int id = 0;
    int xMin = std::numeric_limits<int>::max(), yMin = std::numeric_limits<int>::max();
    int xMax = -1, yMax = -1;
    int area = 0;
    double xSum = 0, ySum = 0, probabilitySum = 0;
    float maximum = 0;
    std::vector<int> pixels;
    std::vector<int> sourceIds;

    void add(int pixel, int width, float probability) {
        const int x = pixel % width, y = pixel / width;
        xMin = std::min(xMin, x); yMin = std::min(yMin, y);
        xMax = std::max(xMax, x); yMax = std::max(yMax, y);
        ++area; xSum += x; ySum += y;
        probabilitySum += probability;
        maximum = std::max(maximum, probability);
        pixels.push_back(pixel);
    }
};

int findRoot(std::vector<int>& parent, int value) {
    while (parent[value] != value) {
        parent[value] = parent[parent[value]];
        value = parent[value];
    }
    return value;
}

std::vector<Region> sourceRegions(const float* probabilities, int width, int height,
                                  std::vector<int>& labels, std::vector<uchar>& binary, float threshold) {
    const int total = width * height;
    labels.assign(total, 0);
    binary.assign(total, 0);
    std::vector<Region> regions;
    std::vector<int> queue;
    for (int start = 0; start < total; ++start) {
        if (!std::isfinite(probabilities[start])) throw std::runtime_error("Lesion probability is not finite");
        if (probabilities[start] < threshold || labels[start] != 0) continue;
        Region region;
        region.id = static_cast<int>(regions.size()) + 1;
        region.sourceIds.push_back(region.id);
        queue.clear();
        queue.push_back(start);
        labels[start] = region.id;
        for (size_t head = 0; head < queue.size(); ++head) {
            const int pixel = queue[head];
            region.add(pixel, width, probabilities[pixel]);
            binary[pixel] = 1;
            const int x = pixel % width, y = pixel / width;
            for (int dy = -1; dy <= 1; ++dy) {
                const int yy = y + dy;
                if (yy < 0 || yy >= height) continue;
                for (int dx = -1; dx <= 1; ++dx) {
                    const int xx = x + dx;
                    if (xx < 0 || xx >= width || (dx == 0 && dy == 0)) continue;
                    const int neighbor = yy * width + xx;
                    if (probabilities[neighbor] >= threshold && labels[neighbor] == 0) {
                        labels[neighbor] = region.id;
                        queue.push_back(neighbor);
                    }
                }
            }
        }
        regions.push_back(std::move(region));
    }
    return regions;
}

std::vector<Region> displayedRegions(std::vector<Region>& raw, const std::vector<int>& labels,
                                     int width, int height, const LesionClassConfig& config, double referenceSize) {
    const int minimum = std::max(1, static_cast<int>(std::ceil(
        config.minimumArea * static_cast<double>(width) * height / (referenceSize * referenceSize))));
    std::vector<int> parent(raw.size() + 1);
    std::iota(parent.begin(), parent.end(), 0);
    std::vector<bool> retained(raw.size() + 1, false);
    for (const Region& region : raw) retained[region.id] = region.area >= minimum;
    if (config.mergeDistance > 0.0) {
        const int radiusX = static_cast<int>(std::ceil(config.mergeDistance * width / referenceSize));
        const int radiusY = static_cast<int>(std::ceil(config.mergeDistance * height / referenceSize));
        const double scaleX = referenceSize / width, scaleY = referenceSize / height;
        for (const Region& region : raw) {
            if (!retained[region.id]) continue;
            for (int pixel : region.pixels) {
                const int x = pixel % width, y = pixel / width;
                for (int dy = -radiusY; dy <= radiusY; ++dy) {
                    const int yy = y + dy;
                    if (yy < 0 || yy >= height) continue;
                    for (int dx = -radiusX; dx <= radiusX; ++dx) {
                        const int xx = x + dx;
                        if (xx < 0 || xx >= width) continue;
                        if (std::hypot(dx * scaleX, dy * scaleY) > config.mergeDistance) continue;
                        const int neighbor = labels[yy * width + xx];
                        if (neighbor <= region.id || !retained[neighbor]) continue;
                        const int a = findRoot(parent, region.id), b = findRoot(parent, neighbor);
                        if (a != b) parent[std::max(a, b)] = std::min(a, b);
                    }
                }
            }
        }
    }
    std::vector<Region> grouped(raw.size() + 1);
    std::vector<bool> present(raw.size() + 1, false);
    for (const Region& region : raw) {
        if (!retained[region.id]) continue;
        const int root = findRoot(parent, region.id);
        Region& combined = grouped[root];
        if (!present[root]) {
            combined = region;
            combined.pixels.clear(); // Display regions do not change the full threshold mask.
            present[root] = true;
        } else {
            combined.id = std::min(combined.id, region.id);
            combined.xMin = std::min(combined.xMin, region.xMin);
            combined.yMin = std::min(combined.yMin, region.yMin);
            combined.xMax = std::max(combined.xMax, region.xMax);
            combined.yMax = std::max(combined.yMax, region.yMax);
            combined.area += region.area;
            combined.xSum += region.xSum;
            combined.ySum += region.ySum;
            combined.probabilitySum += region.probabilitySum;
            combined.maximum = std::max(combined.maximum, region.maximum);
            combined.sourceIds.push_back(region.id);
        }
    }
    std::vector<Region> displayed;
    for (size_t root = 1; root < grouped.size(); ++root) {
        if (present[root] && grouped[root].probabilitySum / grouped[root].area >= 0.5)
            displayed.push_back(std::move(grouped[root]));
    }
    std::sort(displayed.begin(), displayed.end(), [](const Region& a, const Region& b) {
        if (a.area != b.area) return a.area > b.area;
        const double aMean = a.probabilitySum / a.area, bMean = b.probabilitySum / b.area;
        if (aMean != bMean) return aMean > bMean;
        return a.id < b.id;
    });
    return displayed;
}


LesionRegion canonicalRegion(const Region& r,int width,int height,const QString& code,int rank,double referenceSize) {
    return {code,rank,r.xMin,r.yMin,r.xMax,r.yMax,r.area,
        static_cast<int>(std::nearbyint(r.xSum/r.area)),static_cast<int>(std::nearbyint(r.ySum/r.area)),
        r.xSum/r.area,r.ySum/r.area,r.area*referenceSize*referenceSize/(width*height),
        r.probabilitySum/r.area,r.maximum,r.sourceIds};
}
}
LesionPostprocessor::LesionPostprocessor(std::array<LesionClassConfig,4> classes,double referenceSize)
    :classes_(std::move(classes)),referenceSize_(referenceSize) {}
LesionResult LesionPostprocessor::process(const QImage& image,const SegmentationProbabilities& probabilities,
                                          const QString& directory,const ProgressCallback& progress) const {
    const int width=image.width(),height=image.height(),pixelCount=width*height;
    require(probabilities.width==width&&probabilities.height==height,"Lesion probability dimensions do not match the image");
    QImage overlay=image.convertToFormat(QImage::Format_RGB888);
    std::vector<float> combined(pixelCount,0.0f);
    LesionResult result;
    if(progress) progress("LESION_MASK_PROCESSING");
    for(int i=0;i<4;++i) {
        const auto map=probabilities.channels[i];
        require(map.size()==static_cast<size_t>(pixelCount),"Lesion probability plane has an unexpected size");
        auto& channel=result.channels[i]; channel.code=classes_[i].code;
        std::vector<int> labels;
        auto raw=sourceRegions(map.data(),width,height,labels,channel.binaryMask,classes_[i].threshold);
        if(progress) progress("LESION_REGION_EXTRACTION");
        const auto displayed=displayedRegions(raw,labels,width,height,classes_[i],referenceSize_);
        for(const auto& region:raw) channel.rawRegions.push_back(canonicalRegion(region,width,height,channel.code,region.id,referenceSize_));
        for(size_t j=0;j<displayed.size();++j) channel.regions.push_back(canonicalRegion(displayed[j],width,height,channel.code,static_cast<int>(j)+1,referenceSize_));
        for(int pixel=0;pixel<pixelCount;++pixel) combined[pixel]=std::max(combined[pixel],map[pixel]);
        QImage mask(width,height,QImage::Format_Grayscale8);
        for(int y=0;y<height;++y) { auto* row=mask.scanLine(y); for(int x=0;x<width;++x) row[x]=channel.binaryMask[static_cast<size_t>(y)*width+x]?255:0; }
        channel.maskPath=savePng(mask,directory,channel.code+"_mask.png");
        channel.probabilityPath=savePng(probabilityHeatmap(map,width,height),directory,channel.code+"_probability.png");
        const auto& color=colors[i];
        for(int y=0;y<height;++y) { auto* row=overlay.scanLine(y); for(int x=0;x<width;++x) {
            if(!channel.binaryMask[static_cast<size_t>(y)*width+x]) continue;
            for(int c=0;c<3;++c) row[3*x+c]=static_cast<uchar>(std::clamp(std::nearbyint(row[3*x+c]*0.55+color[c]*0.45),0.0,255.0));
        }}
    }
    result.overlayPath=savePng(overlay,directory,"lesion_overlay.png");
    result.heatmapPath=savePng(probabilityHeatmap(combined,width,height),directory,"lesion_probability.png");
    return result;
}
} // namespace retina::inference
