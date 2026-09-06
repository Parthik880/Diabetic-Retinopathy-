export type StageState = "pending" | "running" | "complete" | "error";

export interface PipelineStage {
  id: string;
  number: number;
  label: string;
  description: string;
  state: StageState;
  error?: string | null;
}

export interface FeatureStage {
  id: string;
  label: string;
  layer: string;
  tensor_shape: number[];
  channels_total: number;
  channels_shown: number;
  images: string[];
  explanation: string;
}

export interface QualityResult {
  quality: string;
  confidence: number;
  probabilities: Record<string, number>;
  metric: string;
  device: string;
}

export interface RestorationResult {
  output_image_url: string;
  width: number;
  height: number;
  device: string;
  checkpoint: Record<string, unknown>;
}

export interface GradeResult {
  predicted_grade: number;
  confidence: number;
  probabilities: number[];
  device: string;
  gradcam_url?: string | null;
}

export interface LesionClassResult {
  detected: boolean;
  num_regions: number;
  image_percentage: number;
  probability_map_url?: string | null;
  mask_url?: string | null;
  total_valid_regions?: number;
}

export interface LesionRegion {
  rank: number;
  class_code: string;
  class_name: string;
  confidence: number;
  mean_probability: number;
  max_probability: number;
  center_pixels: [number, number];
  bbox_pixels: [number, number, number, number];
  bbox_normalized: [number, number, number, number];
  area_pixels: number;
  width: number;
  height: number;
  crop_url: string;
  download_name: string;
}

export interface LesionResult {
  classes: Record<string, LesionClassResult>;
  channel_order: string[];
  threshold: number;
  overlay_url: string;
  device: string;
  localization_note: string;
  regions: LesionRegion[];
  region_count: number;
  region_limit: number;
  confidence_method: string;
}

export interface AnalysisResult {
  session_id: string;
  device: string;
  input_image_url: string;
  stages: PipelineStage[];
  quality?: QualityResult | null;
  restoration?: RestorationResult | null;
  grade?: GradeResult | null;
  lesions?: LesionResult | null;
  features: Record<string, FeatureStage>;
  warnings: string[];
}

export interface ExplorerInternal {
  id: string;
  label: string;
  block_type: string;
}

export interface ExplorerBlock {
  id: string;
  label: string;
  group: string;
  block_type: string;
  description: string;
  internals: ExplorerInternal[];
}

export interface ExplorerArchitecture {
  id: "quality" | "restoration" | "grade" | "lesion";
  label: string;
  model_name: string;
  device: string;
  input: string;
  parameter_count: number;
  block_count: number;
  blocks: ExplorerBlock[];
}

export interface BlockVisualization {
  id: string;
  parent_id: string;
  label: string;
  block_type: string;
  tensor_shape: number[];
  channels: number;
  height: number;
  width: number;
  spatial: boolean;
  feature_map_url: string;
  activation_heatmap_url: string;
  feature_thumbnail_url: string;
  activation_thumbnail_url: string;
  feature_download_name: string;
  activation_download_name: string;
  channel_index?: number | null;
  feature_method: string;
  heatmap_method: string;
  input_shape: number[];
}

export interface GradeGradCAM {
  target_class: number;
  probabilities: number[];
  gradcam_url: string;
  method: string;
}

export interface LesionRegionResponse {
  regions: LesionRegion[];
  count: number;
  available_count: number;
  limit: number;
  confidence_method: string;
}
