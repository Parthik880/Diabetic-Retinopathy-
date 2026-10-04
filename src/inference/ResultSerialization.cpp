#include "inference/ResultSerialization.h"
namespace retina::inference {
namespace {
QVariantMap regionMap(const LesionRegion& r) {
    QVariantList sources;for(int id:r.sourceIds) sources<<id;
    return {{"region_id",r.rank},{"class",r.code},{"lesion",r.code},{"source_component_ids",sources},
        {"x_min",r.xMin},{"y_min",r.yMin},{"x_max",r.xMax},{"y_max",r.yMax},{"width",r.xMax-r.xMin+1},{"height",r.yMax-r.yMin+1},
        {"center_x",r.centerX},{"center_y",r.centerY},{"centroid_x",r.centroidX},{"centroid_y",r.centroidY},
        {"area_pixels",r.area},{"area_model_pixels",r.modelArea},{"mean_probability",r.meanProbability},{"max_probability",r.maximumProbability},
        {"bbox_pixels",QVariantList{r.xMin,r.yMin,r.xMax,r.yMax}},{"center_pixels",QVariantList{r.centerX,r.centerY}}};
}
}
QVariantMap lesionResultFields(const LesionResult& result) {
    QVariantMap counts,masks,probabilities,cams;QVariantList regions,raw;QString defaultCam;
    for(const auto& c:result.channels) {
        counts[c.code]=static_cast<int>(c.regions.size());masks[c.code]=c.maskPath;probabilities[c.code]=c.probabilityPath;
        if(!c.camPath.isEmpty()) {cams[c.code]=c.camPath;if(defaultCam.isEmpty()) defaultCam=c.camPath;}
        for(const auto& r:c.regions) regions<<regionMap(r);
        for(const auto& r:c.rawRegions) raw<<regionMap(r);
    }
    return {{"lesion_overlay_path",result.overlayPath},{"lesion_counts",counts},{"regions",regions},{"raw_regions",raw},
        {"lesion_gradcam_paths",cams},{"lesion_probability_paths",probabilities},{"lesion_mask_paths",masks},
        {"lesion_gradcam_path",defaultCam},{"lesion_heatmap_path",result.heatmapPath}};
}
}
