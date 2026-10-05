#pragma once
#include "inference/ModelConfig.h"
#include "inference/ModelTypes.h"
namespace retina::inference {
// Creates and validates persistent adapters. Runtime headers remain private.
class ModelFactory final {
public:
    static ModelStages create(const ModelConfig& config, bool forceContractValidation = false);
};
}
