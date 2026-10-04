#pragma once

#include <QDateTime>
#include <QVariantMap>

namespace retina::reporting {
struct ReportExportResult {
    QString rootFolder, eyeFolder, reportPath;
    QStringList files; // Portable paths relative to rootFolder.
};
struct BilateralReportExportResult {
    QString rootFolder;
    QList<ReportExportResult> eyes;
    QStringList reportPaths, files;
};

QString sanitizeWindowsName(QString name);
// Export saved results only. Throws a descriptive std::runtime_error on failure;
// a failed operation removes only its newly created report root.
ReportExportResult exportReportBundle(const QString &destination, const QVariantMap &result,
                                     const QDateTime &generatedAt = QDateTime::currentDateTime());
BilateralReportExportResult exportReportBundles(const QString &destination,
                                               const QList<QVariantMap> &results,
                                               const QDateTime &generatedAt = QDateTime::currentDateTime());
} // namespace retina::reporting
