#pragma once

#include <QRegularExpression>
#include <QDir>
#include <QFileInfo>
#include <QString>
#include <QStringList>

namespace retina {
inline QString eyeFromPathLabel(const QString& label) {
    const QStringList tokens = label.toUpper().split(QRegularExpression(QStringLiteral("[^A-Z0-9]+")), Qt::SkipEmptyParts);
    const bool os = tokens.contains(QStringLiteral("OS")) || tokens.contains(QStringLiteral("LEFT"));
    const bool od = tokens.contains(QStringLiteral("OD")) || tokens.contains(QStringLiteral("RIGHT"));
    if (os == od) return {};
    return os ? QStringLiteral("OS") : QStringLiteral("OD");
}
inline QString eyeFromBatchPath(const QString& relativePath) {
    const QFileInfo file(relativePath);
    QString label = file.completeBaseName();
    if (file.path() != QLatin1String(".")) label += QLatin1Char('_') + file.dir().dirName();
    return eyeFromPathLabel(label);
}
}
