#include "core/AppPaths.h"
#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <stdexcept>

namespace retina::AppPaths {
namespace {
QString explicitConfig;
bool validRoot(const QString& path) {
    const QDir dir(path);
    return QFileInfo(dir.filePath("config/models.json")).isFile()
        && QFileInfo(dir.filePath("src/checkpoints")).isDir();
}
QString search(QString start) {
    QDir dir(start);
    for (int level = 0; level <= 5; ++level) {
        if (validRoot(dir.absolutePath())) return dir.canonicalPath();
        if (!dir.cdUp()) break;
    }
    return {};
}
}
QString applicationRoot() {
    if (qEnvironmentVariableIsSet("RETINAGRAM_ROOT")) {
        const QString root = qEnvironmentVariable("RETINAGRAM_ROOT");
        if (root.isEmpty() || !QDir::isAbsolutePath(root) || !validRoot(root))
            throw std::runtime_error(QString("Invalid RETINAGRAM_ROOT: %1\nExpected config/models.json and src/checkpoints/.").arg(root).toStdString());
        return QDir(root).canonicalPath();
    }
    const auto executableRoot = search(QCoreApplication::applicationDirPath());
    if (!executableRoot.isEmpty()) return executableRoot;
    const auto workingRoot = search(QDir::currentPath());
    if (!workingRoot.isEmpty()) return workingRoot;
    throw std::runtime_error(QString("Cannot locate RetinaGram application root.\nExpected config/models.json and src/checkpoints/.\nExecutable directory: %1\nWorking directory: %2\nSet RETINAGRAM_ROOT to a valid root if necessary.")
                             .arg(QCoreApplication::applicationDirPath(), QDir::currentPath()).toStdString());
}
QString configPath() {
    return explicitConfig.isEmpty() ? QDir(applicationRoot()).filePath("config/models.json") : explicitConfig;
}
QString checkpointsPath() { return QDir(applicationRoot()).filePath("src/checkpoints"); }
QString assetsPath(const QString& name) { return QDir(applicationRoot()).filePath(name.isEmpty() ? "assets" : "assets/" + name); }
void setModelConfigOverride(const QString& file) { explicitConfig = QFileInfo(file).absoluteFilePath(); }
}
