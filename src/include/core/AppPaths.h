#pragma once
#include <QString>

namespace retina::AppPaths {
// Project resources always use one dynamically discovered root. No build path
// is compiled into the application. The override is explicit CLI input only.
QString applicationRoot();
QString configPath();
QString checkpointsPath();
QString assetsPath(const QString& name = {});
void setModelConfigOverride(const QString& file);
}
