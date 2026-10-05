#pragma once
#include "inference/ModelTypes.h"
#include <QVariantMap>
namespace retina::inference {
// Only the application boundary converts canonical types to the legacy UI map.
QVariantMap lesionResultFields(const LesionResult& result);
}
