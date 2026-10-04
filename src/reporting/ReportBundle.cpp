#include "reporting/ReportBundle.h"
#include "reporting/ScreeningReport.h"
#include "image/ImageDecoder.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QImageWriter>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QSaveFile>
#include <QSet>
#include <cmath>
#include <stdexcept>

namespace retina::reporting {
namespace {
const QStringList maskNames{"microaneurysm.png", "hemorrhage.png", "hard_exudate.png", "soft_exudate.png"};
void check(bool ok, const QString &message) {
    if (!ok) throw std::runtime_error(message.toStdString());
}
void finiteValues(const QVariant &value) {
    if (value.metaType().id() == QMetaType::Double || value.metaType().id() == QMetaType::Float)
        check(std::isfinite(value.toDouble()), "Analysis contains a non-finite numerical value.");
    else if (value.metaType().id() == QMetaType::QVariantMap)
        for (const auto &item : value.toMap()) finiteValues(item);
    else if (value.metaType().id() == QMetaType::QVariantList)
        for (const auto &item : value.toList()) finiteValues(item);
}
struct Sources {
    QVariantMap result;
    Data data;
    QImage original;
    QString restored, overlay;
    QVariantMap masks;
    explicit Sources(const QVariantMap &value) : result(value), data(value) {
        check(value.value("state") == "COMPLETE", "A completed eye analysis is required to export a report.");
        check(data.eye == "OS" || data.eye == "OD", "Report eye must be OS or OD.");
        check(QFileInfo(data.original).isFile(), "Original retinal image is unavailable.");
        QString reason;
        original = loadImage(data.original, &reason).convertToFormat(QImage::Format_RGB888);
        check(!original.isNull(), "Original retinal image cannot be decoded: " + reason);
        auto artifact = [](const QString &path, const QString &description) {
            if (!path.isEmpty()) {
                check(QFileInfo(path).isFile(), description + " is unavailable: " + path);
                check(!loadImage(path).isNull(), description + " cannot be decoded: " + path);
            }
            return path;
        };
        restored = artifact(value.value("restored_image_path").toString(), "Restored retinal image");
        check(value.value("analysis_source") != "restored" || !restored.isEmpty(), "The restored image used for analysis is unavailable.");
        overlay = artifact(data.overlay, "Lesion overlay");
        const auto paths = value.value("lesion_mask_paths").toMap();
        for (const auto &code : lesionCodes) {
            const auto path = artifact(paths.value(code).toString(), code + " prediction mask");
            if (!path.isEmpty()) masks[code] = path;
        }
        check(data.grade.isValid() && data.grade.toInt() >= 0 && data.grade.toInt() <= 4, "The completed report has no valid DR grade.");
    }
};
QVariantMap structuredResult(const Sources &source, const QDateTime &generatedAt) {
    const auto &data = source.data;
    const auto localTime = generatedAt.toLocalTime();
    QVariantMap patient;
    for (const auto &key : {"name", "id", "age", "gender", "eye", "scan_datetime", "referring_doctor"}) {
        const auto value = data.patient.value(key);
        if (value.isValid() && !value.isNull() && !value.toString().isEmpty()) patient[key] = value;
    }
    QVariantMap lesions;
    const auto counts = source.result.value("lesion_counts").toMap();
    for (int i = 0; i < 4; ++i) {
        const auto code = lesionCodes[i];
        // Legacy snapshots without a full mask may not prove absence. Keep that
        // unavailable, matching the PDF, rather than deriving it from UI Top-K.
        lesions[code] = QVariantMap{{"label", lesionNames[i]},
            {"detected", data.lesions[i] < 0 ? QVariant{} : QVariant(data.lesions[i] == 1)},
            {"region_count", counts.contains(code) ? QVariant(counts.value(code).toInt()) : QVariant{}},
            {"mask_file", source.masks.contains(code) ? QVariant("masks/" + maskNames[i]) : QVariant{}}};
    }
    QVariantMap result{{"report_id", data.runId}, {"patient", patient},
        {"image_quality", QVariantMap{{"class", data.quality}, {"confidence", source.result.value("quality_confidence")}, {"probabilities", source.result.value("quality_probabilities")}}},
        {"dr_grading", QVariantMap{{"grade", data.grade}, {"label", gradeLabel(data.grade)}, {"confidence", data.confidence}, {"probabilities", source.result.value("grade_probabilities")}}},
        {"lesions", lesions}, {"inference_device", data.device}, {"pipeline_state", source.result.value("state")},
        {"analysis_source", source.result.value("analysis_source")}, {"original_image_file", "original_fundus.jpg"},
        {"restored_image_file", source.restored.isEmpty() ? QVariant{} : QVariant("restored_fundus.png")},
        {"generated_at", localTime.toOffsetFromUtc(localTime.offsetFromUtc()).toString(Qt::ISODateWithMs)}};
    finiteValues(result);
    return result;
}
QString createRoot(const QDir &parent, const QString &patientName, const QDateTime &time) {
    const auto base = "RetinaGram_" + sanitizeWindowsName(patientName) + '_' + time.toLocalTime().toString("yyyyMMdd_HHmmss");
    for (int suffix = 1; suffix < 100000; ++suffix) {
        const auto name = suffix == 1 ? base : base + '_' + QString::number(suffix);
        // mkdir is exclusive, including two exports racing in the same second.
        if (parent.mkdir(name)) return parent.filePath(name);
        check(QFileInfo::exists(parent.filePath(name)), "Cannot create report directory in " + parent.absolutePath());
    }
    check(false, "Cannot allocate a unique report directory.");
    return {};
}
ReportExportResult writeEye(const QString &root, const Sources &source,
                           const QVariantMap &structured, const QDateTime &time) {
    const auto eyeName = source.data.eye == "OS" ? QString("Left_OS") : QString("Right_OD");
    check(QDir(root).mkdir(eyeName), "Cannot create report eye directory: " + eyeName);
    const QDir eye(QDir(root).filePath(eyeName));
    ReportExportResult result{root, eye.path(), eye.filePath("report.pdf"), {}};
    auto added = [&](const QString &relative) { result.files << eyeName + '/' + relative; };
    QImageWriter jpeg(eye.filePath("original_fundus.jpg"), "jpeg");
    jpeg.setQuality(95); jpeg.setOptimizedWrite(true);
    check(jpeg.write(source.original), "Cannot save original_fundus.jpg: " + jpeg.errorString());
    added("original_fundus.jpg");
    auto copy = [&](const QString &from, const QString &relative, const QString &description) {
        if (!from.isEmpty()) {
            check(QFile::copy(from, eye.filePath(relative)), "Cannot copy " + description + " to " + eye.filePath(relative));
            added(relative);
        }
    };
    copy(source.restored, "restored_fundus.png", "restored retinal image");
    copy(source.overlay, "lesion_overlay.png", "lesion overlay");
    QVariantMap bundleMasks;
    if (!source.masks.isEmpty()) check(eye.mkdir("masks"), "Cannot create masks directory.");
    for (int i = 0; i < 4; ++i) {
        const auto path = source.masks.value(lesionCodes[i]).toString();
        const auto relative = "masks/" + maskNames[i];
        copy(path, relative, lesionNames[i] + " mask");
        if (!path.isEmpty()) bundleMasks[lesionCodes[i]] = eye.filePath(relative);
    }
    QSaveFile json(eye.filePath("results.json"));
    check(json.open(QIODevice::WriteOnly), "Cannot write results.json: " + json.errorString());
    const auto bytes = QJsonDocument::fromVariant(structured).toJson(QJsonDocument::Indented);
    check(json.write(bytes) == bytes.size() && json.commit(), "Cannot write results.json: " + json.errorString());
    added("results.json");
    auto pdfResult = source.result;
    pdfResult["image_path"] = eye.filePath("original_fundus.jpg");
    pdfResult["restored_image_path"] = source.restored.isEmpty() ? QString{} : eye.filePath("restored_fundus.png");
    pdfResult["lesion_overlay_path"] = source.overlay.isEmpty() ? QString{} : eye.filePath("lesion_overlay.png");
    pdfResult["lesion_mask_paths"] = bundleMasks;
    check(writePdf(result.reportPath, pdfResult, time), "Cannot save report.pdf for " + eyeName + '.');
    added("report.pdf"); result.files.sort();
    return result;
}
} // namespace

QString sanitizeWindowsName(QString name) {
    name.remove(QRegularExpression("[<>:\"/\\\\|?*\\p{Cc}]"));
    name.remove(QRegularExpression("\\s+"));
    name.remove(QRegularExpression("^[ .]+|[ .]+$"));
    name = name.left(64);
    if (!name.isEmpty() && name.back().isHighSurrogate()) name.chop(1);
    name.remove(QRegularExpression("[ .]+$"));
    return name.isEmpty() ? QString("Patient") : name;
}
BilateralReportExportResult exportReportBundles(const QString &destination, const QList<QVariantMap> &results,
                                               const QDateTime &generatedAt) {
    check(QFileInfo(destination).isDir(), "Selected report destination does not exist.");
    check(!results.isEmpty(), "At least one completed eye report is required.");
    check(generatedAt.isValid(), "Report generation time is invalid.");
    const QDir parent(QFileInfo(destination).canonicalFilePath());
    QList<Sources> sources;
    QList<QVariantMap> structured;
    QSet<QString> eyes;
    for (const auto &result : results) {
        Sources source(result);
        check(!eyes.contains(source.data.eye), "Each eye may appear only once in an export.");
        if (!sources.isEmpty()) check(source.data.patient.value("id") == sources.first().data.patient.value("id") &&
            source.data.patient.value("name") == sources.first().data.patient.value("name"), "Bilateral reports must belong to the same patient.");
        eyes.insert(source.data.eye);
        structured << structuredResult(source, generatedAt);
        sources << std::move(source);
    }
    BilateralReportExportResult exported;
    exported.rootFolder = createRoot(parent, sources.first().data.patient.value("name").toString(), generatedAt);
    try {
        for (qsizetype i = 0; i < sources.size(); ++i) {
            const auto eye = writeEye(exported.rootFolder, sources[i], structured[i], generatedAt);
            exported.eyes << eye; exported.reportPaths << eye.reportPath; exported.files << eye.files;
        }
        exported.files.sort();
        return exported;
    } catch (const std::exception &error) {
        const bool removed = QDir(exported.rootFolder).removeRecursively();
        throw std::runtime_error((QString::fromUtf8(error.what()) +
            (removed ? QString{} : " Incomplete export could not be removed: " + exported.rootFolder)).toStdString());
    }
}
ReportExportResult exportReportBundle(const QString &destination, const QVariantMap &result, const QDateTime &generatedAt) {
    return exportReportBundles(destination, {result}, generatedAt).eyes.first();
}
} // namespace retina::reporting
