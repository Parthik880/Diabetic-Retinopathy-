#include "reporting/ScreeningReport.h"
#include "reporting/ReportBundle.h"
#include "app/AnalysisController.h"
#include "inference/ModelManager.h"
#include "inference/ModelConfig.h"
#include "ui/MainWindow.h"
#include "core/AppPaths.h"

#include <QApplication>
#include <QCoreApplication>
#include <QElapsedTimer>
#include <QDir>
#include <QFileInfo>
#include <QFontDatabase>
#include <QFile>
#include <QStandardPaths>
#include <QPushButton>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QTimer>
#include <QTextStream>
#include <stdexcept>
#include <vector>
#include <cuda_runtime_api.h>
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#endif

namespace {
QJsonObject memorySnapshot() {
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS_EX counters{};
    counters.cb = sizeof(counters);
    if (GetProcessMemoryInfo(GetCurrentProcess(), reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&counters), sizeof(counters))) {
        return {{QStringLiteral("working_set_bytes"), static_cast<double>(counters.WorkingSetSize)},
                {QStringLiteral("peak_working_set_bytes"), static_cast<double>(counters.PeakWorkingSetSize)}};
    }
#endif
    return {};
}

QJsonObject gpuMemorySnapshot() {
    size_t freeBytes = 0, totalBytes = 0;
    if (cudaMemGetInfo(&freeBytes, &totalBytes) != cudaSuccess) return {};
    return {{QStringLiteral("free_bytes"), static_cast<double>(freeBytes)},
            {QStringLiteral("total_bytes"), static_cast<double>(totalBytes)},
            {QStringLiteral("used_bytes"), static_cast<double>(totalBytes - freeBytes)}};
}
int analyzeFromCommandLine(int argc, char* argv[]) {
    QCoreApplication application(argc, argv);
    QCoreApplication::setOrganizationName(QStringLiteral("RetinaGram"));
    QCoreApplication::setApplicationName(QStringLiteral("RetinaGram"));
    const QStringList arguments = application.arguments();
    if (arguments.size() != 3) {
        QTextStream(stderr) << "Usage: RetinaGram.exe --analyze <image-path>\n";
        return 2;
    }
    ModelManager models;
    QElapsedTimer timer;
    timer.start();
    if (!models.initialize()) {
        QTextStream(stderr) << "Model initialization failed: " << models.lastError() << '\n';
        return 3;
    }
    const qint64 startupMs = timer.elapsed();
    timer.restart();
    QVariantMap result = models.analyzeImage(QStringLiteral("OS"), arguments[2]);
    const qint64 analysisMs = timer.elapsed();
    result.insert(QStringLiteral("model_initialization_ms"), startupMs);
    result.insert(QStringLiteral("analysis_ms"), analysisMs);
    QTextStream(stdout) << QJsonDocument::fromVariant(result).toJson(QJsonDocument::Indented);
    return result.value(QStringLiteral("state")).toString() == QStringLiteral("FAILED") ? 4 : 0;
}

int benchmarkFromCommandLine(int argc, char* argv[]) {
    QCoreApplication application(argc, argv);
    QCoreApplication::setOrganizationName(QStringLiteral("RetinaGram"));
    QCoreApplication::setApplicationName(QStringLiteral("RetinaGram"));
    const QStringList arguments = application.arguments();
    if (arguments.size() != 4) {
        QTextStream(stderr) << "Usage: RetinaGram.exe --benchmark <image-path> <iterations>\n";
        return 2;
    }
    bool valid = false;
    const int iterations = arguments[3].toInt(&valid);
    if (!valid || iterations < 1 || iterations > 20) return 2;
    ModelManager models;
    QElapsedTimer timer;
    timer.start();
    if (!models.initialize()) {
        QTextStream(stderr) << "Model initialization failed: " << models.lastError() << '\n';
        return 3;
    }
    const qint64 initializationMs = timer.elapsed();
    const QJsonObject idleMemory = memorySnapshot();
    const QJsonObject idleGpuMemory = gpuMemorySnapshot();
    QJsonArray runs;
    for (int index = 0; index < iterations; ++index) {
        timer.restart();
        const QVariantMap result = models.analyzeImage(QStringLiteral("OS"), arguments[2]);
        QJsonObject item = QJsonObject::fromVariantMap({
            {QStringLiteral("index"), index},
            {QStringLiteral("analysis_ms"), timer.elapsed()},
            {QStringLiteral("state"), result.value(QStringLiteral("state"))},
            {QStringLiteral("quality"), result.value(QStringLiteral("quality"))},
            {QStringLiteral("grade"), result.value(QStringLiteral("grade"))},
            {QStringLiteral("timing_ms"), result.value(QStringLiteral("timing_ms"))},
            {QStringLiteral("device"), result.value(QStringLiteral("device"))},
            {QStringLiteral("onnx_provider"), result.value(QStringLiteral("onnx_provider"))},
            {QStringLiteral("error"), result.value(QStringLiteral("error"))}
        });
        item.insert(QStringLiteral("memory"), memorySnapshot());
        item.insert(QStringLiteral("gpu_memory"), gpuMemorySnapshot());
        runs.append(item);
        if (result.value(QStringLiteral("state")).toString() == QStringLiteral("FAILED")) {
            QTextStream(stdout) << QJsonDocument(QJsonObject{
                {QStringLiteral("model_initialization_ms"), initializationMs},
                {QStringLiteral("idle_memory"), idleMemory},
                {QStringLiteral("idle_gpu_memory"), idleGpuMemory},
                {QStringLiteral("runs"), runs}}).toJson(QJsonDocument::Indented);
            return 4;
        }
    }
    QTextStream(stdout) << QJsonDocument(QJsonObject{
        {QStringLiteral("model_initialization_ms"), initializationMs},
        {QStringLiteral("idle_memory"), idleMemory},
        {QStringLiteral("idle_gpu_memory"), idleGpuMemory},
        {QStringLiteral("runs"), runs}}).toJson(QJsonDocument::Indented);
    return 0;
}

int batchFromCommandLine(int argc, char* argv[]) {
    QApplication application(argc, argv);
    QCoreApplication::setOrganizationName(QStringLiteral("RetinaGram"));
    QCoreApplication::setApplicationName(QStringLiteral("RetinaGram"));
    QStringList fontDirectories;
    try { fontDirectories.append(retina::AppPaths::assetsPath("fonts")); }
    catch(const std::exception& error) { QTextStream(stderr)<<error.what()<<'\n';return 3; }
    for (const QString& directory : fontDirectories) {
        if (!QFileInfo::exists(QDir(directory).filePath(QStringLiteral("Manrope-Regular.ttf")))) continue;
        QFontDatabase::addApplicationFont(QDir(directory).filePath(QStringLiteral("Manrope-Regular.ttf")));
        QFontDatabase::addApplicationFont(QDir(directory).filePath(QStringLiteral("Manrope-Bold.ttf")));
        break;
    }
    if (application.arguments().size() != 4) {
        QTextStream(stderr) << "Usage: RetinaGram.exe --batch <input-folder> <output-folder>\n";
        return 2;
    }
    AnalysisWorker worker;
    bool ready = false;
    QString message;
    QObject::connect(&worker, &AnalysisWorker::initialized, &application,
                     [&ready, &message](bool ok, const QString& text) { ready = ok; message = text; });
    QObject::connect(&worker, &AnalysisWorker::batchFinished, &application,
                     [&message](const QString& text) { message = text; });
    worker.initialize();
    if (!ready) {
        QTextStream(stderr) << "Model initialization failed: " << message << '\n';
        return 3;
    }
    worker.processBatch(application.arguments()[2], application.arguments()[3]);
    QTextStream(stdout) << message << '\n';
    return message.startsWith(QStringLiteral("Batch finished")) ? 0 : 4;
}
}

int main(int argc, char* argv[]) {
    // Strip the explicit advanced option before existing CLI mode dispatch.
    // Global RETINAGRAM_MODEL_CONFIG is intentionally ignored.
    std::vector<char*> filtered{argv[0]};
    bool configSpecified=false;
    for(int index=1;index<argc;++index) {
        if(QString::fromLocal8Bit(argv[index])=="--model-config") {
            if(configSpecified||index+1>=argc||QString::fromLocal8Bit(argv[index+1]).startsWith("--")) {
                QTextStream(stderr)<<"Usage: --model-config <file> (once)\n"; return 2;
            }
            retina::AppPaths::setModelConfigOverride(QString::fromLocal8Bit(argv[++index])); configSpecified=true;
        } else filtered.push_back(argv[index]);
    }
    argc=static_cast<int>(filtered.size()); filtered.push_back(nullptr); argv=filtered.data();
    if((argc==2||argc==5)&&(QString::fromLocal8Bit(argv[1])=="--validate-models"||QString::fromLocal8Bit(argv[1])=="--model-info")) {
        QCoreApplication application(argc,argv);
        QCoreApplication::setOrganizationName("RetinaGram"); QCoreApplication::setApplicationName("RetinaGram");
        try {
            if(argc==5) qputenv("RETINAGRAM_INTERNAL_CONTRACT_CACHE",QByteArray(argv[4]));
            const auto config=retina::inference::ModelConfig::load(argc==5?QString::fromLocal8Bit(argv[2]):QString{},argc==5?QString::fromLocal8Bit(argv[3]):QString{});
            if(application.arguments()[1]=="--model-info") {
                QTextStream out(stdout);
                out<<"Application root: "<<config.applicationRoot<<"\nConfiguration: "<<config.file<<'\n';
                for(const auto* stage:{&config.quality,&config.restoration,&config.grading,&config.lesion}) {
                    out<<stage->stage<<"\n  Adapter: "<<stage->adapter<<"\n  File: "<<stage->model<<"\n  Path: "<<stage->path<<"\n  Exists: "<<(QFileInfo(stage->path).isFile()?"yes":"no")<<"\n  Input: ";
                    if(stage->input.dynamicSpatial) out<<"1x3xHxW, dynamic spatial";
                    else out<<"1x3x"<<stage->input.height<<'x'<<stage->input.width<<", "<<retina::inference::dtypeName(stage->input.dtype);
                    out<<"\n"; if(!stage->output.classes.isEmpty()) out<<"  Classes: "<<stage->output.classes.join(", ")<<'\n';
                }
                for(const auto& lesion:config.lesionClasses) out<<"  Lesion "<<lesion.code<<": channel "<<lesion.channel<<'\n';
                return 0;
            }
            ModelManager models(config.checkpointsDirectory,config.file);
            if(!models.initialize(true)) {QTextStream(stderr)<<"Model validation failed: "<<models.lastError()<<'\n';return 3;}
            QTextStream(stdout)<<"IQA ............ OK\nRestoration .... OK\nGrading ........ OK\nLesion ......... OK\nModel configuration valid.\n";
            return 0;
        } catch(const std::exception& error) {QTextStream(stderr)<<error.what()<<'\n';return 3;}
    }
    if (argc > 1 && QString::fromLocal8Bit(argv[1]) == QStringLiteral("--analyze")) {
        return analyzeFromCommandLine(argc, argv);
    }
    if (argc > 1 && QString::fromLocal8Bit(argv[1]) == QStringLiteral("--benchmark")) {
        return benchmarkFromCommandLine(argc, argv);
    }
    if (argc > 1 && QString::fromLocal8Bit(argv[1]) == QStringLiteral("--batch")) {
        return batchFromCommandLine(argc, argv);
    }
    QApplication application(argc, argv);
    QCoreApplication::setOrganizationName(QStringLiteral("RetinaGram"));
    QCoreApplication::setApplicationName(QStringLiteral("RetinaGram"));
    application.setApplicationDisplayName(QStringLiteral("RetinaGram GPU"));
    const QStringList uiArguments=application.arguments();
    const bool validation=uiArguments.contains(QStringLiteral("--result"))||uiArguments.contains(QStringLiteral("--batch-input"));
    if(validation) {
        QStandardPaths::setTestModeEnabled(true);
        QCoreApplication::setOrganizationName(QStringLiteral("RetinaGramValidation"));
        QCoreApplication::setApplicationName(QStringLiteral("Screenshot-%1").arg(QCoreApplication::applicationPid()));
    }
    if(uiArguments.size() == 6 && (uiArguments[1] == "--export-report" || uiArguments[1] == "--export-report-bundle")) {
        QFile resultFile(uiArguments[2]),patientFile(uiArguments[4]);
        if(!resultFile.open(QIODevice::ReadOnly)||!patientFile.open(QIODevice::ReadOnly)) return 6;
        const auto result=QJsonDocument::fromJson(resultFile.readAll()).toVariant().toMap();
        const auto patient=QJsonDocument::fromJson(patientFile.readAll()).toVariant().toMap();
        const auto eye=uiArguments[5];
        if(result.value("state")!="COMPLETE" || (eye!="OS"&&eye!="OD")) return 6;
        const auto context=retina::reporting::withContext(result,patient,eye,QFileInfo(resultFile).lastModified());
        if(uiArguments[1] == "--export-report-bundle") try {
            const auto exported=retina::reporting::exportReportBundle(uiArguments[3],context);
            QTextStream(stdout)<<QJsonDocument::fromVariant(QVariantMap{{"folder",exported.rootFolder},{"eye_folder",exported.eyeFolder},{"report",exported.reportPath},{"files",exported.files}}).toJson(QJsonDocument::Indented);
            return 0;
        } catch(const std::exception& error) {QTextStream(stderr)<<error.what()<<'\n';return 5;}
        return retina::reporting::writePdf(uiArguments[3],context)?0:5;
    }
    if(uiArguments.size() == 6 && uiArguments[1] == "--export-both-bundles") {
        auto read=[](const QString& path) {QFile file(path);if(!file.open(QIODevice::ReadOnly)) throw std::runtime_error("Cannot read report input JSON");return QJsonDocument::fromJson(file.readAll()).toVariant().toMap();};
        try {
            const auto patient=read(uiArguments[5]);
            const auto left=retina::reporting::withContext(read(uiArguments[2]),patient,"OS",QFileInfo(uiArguments[2]).lastModified());
            const auto right=retina::reporting::withContext(read(uiArguments[3]),patient,"OD",QFileInfo(uiArguments[3]).lastModified());
            const auto exported=retina::reporting::exportReportBundles(uiArguments[4],{left,right});
            QTextStream(stdout)<<QJsonDocument::fromVariant(QVariantMap{{"folder",exported.rootFolder},{"reports",exported.reportPaths},{"files",exported.files}}).toJson(QJsonDocument::Indented);
            return 0;
        } catch(const std::exception& error) {QTextStream(stderr)<<error.what()<<'\n';return 5;}
    }
    try { retina::AppPaths::applicationRoot(); }
    catch(const std::exception& error) { QTextStream(stderr)<<error.what()<<'\n'; return 3; }
    retina::MainWindow window;
    AnalysisController controller(&window);
    window.show();
    if (application.arguments().size() >= 3 &&
        application.arguments()[1] == QStringLiteral("--screenshot")) {
        const QString destination = application.arguments()[2];
        QStringList selections;
        QString requestedView;
        const QStringList arguments = application.arguments();
        for (int index = 3; index < arguments.size(); ++index) {
            if (arguments[index] == QLatin1String("--result") && index + 1 < arguments.size()) {
                QFile file(arguments[++index]);
                if(!file.open(QIODevice::ReadOnly)) return 6;
                const QVariantMap result=QJsonDocument::fromJson(file.readAll()).toVariant().toMap();
                if(result.isEmpty()) return 6;
                QVariantMap patient{{"name","UI Validation Patient"},{"patientIdNumber","RH-TEST"}};
                const int patientArg=arguments.indexOf("--patient");
                if(patientArg>=0 && patientArg+1<arguments.size()) {
                    QFile metadata(arguments[patientArg+1]); if(!metadata.open(QIODevice::ReadOnly)) return 6;
                    patient=QJsonDocument::fromJson(metadata.readAll()).toVariant().toMap();
                }
                window.setPatient(patient);
                const int eyeArg=arguments.indexOf("--eye");
                window.setEyeResult(eyeArg>=0 && arguments.value(eyeArg+1)=="OD"?"OD":"OS",result);
            } else if (arguments[index] == QLatin1String("--batch-input") && index + 1 < arguments.size()) {
                window.discoverBatch(arguments[++index]);
            } else if ((arguments[index]=="--patient" || arguments[index]=="--eye") && index+1<arguments.size()) {
                ++index;
            } else if (arguments[index] == QLatin1String("--view") && index + 1 < arguments.size()) {
                requestedView=arguments[++index];
            } else if (arguments[index] == QLatin1String("--size") && index + 1 < arguments.size()) {
                const QStringList dimensions = arguments[++index].split(QLatin1Char('x'));
                if (dimensions.size() != 2 || dimensions[0].toInt() < 800 || dimensions[1].toInt() < 650) {
                    QTextStream(stderr) << "Invalid screenshot size; use WIDTHxHEIGHT (minimum 800x650).\n";
                    return 6;
                }
                window.resize(dimensions[0].toInt(), dimensions[1].toInt());
            } else {
                QString selection = arguments[index].trimmed();
                selection.remove(QLatin1Char('"'));
                selections.append(selection);
            }
        }
        if (!selections.isEmpty()) {
            QTimer::singleShot(2800, &window, [&window, page = selections[0], &application] {
                for (QPushButton *button : window.findChildren<QPushButton*>()) {
                    if (button->accessibleName() == page || button->text() == page) {
                        button->click();
                        return;
                    }
                }
                QTextStream(stderr) << "Screenshot page not found: " << page << '\n';
                application.exit(6);
            });
        }
        if (selections.size() >= 2) {
            const QString eye = selections[1];
            QTimer::singleShot(3100, &window, [&window, eye] {
                const QString target = eye == QLatin1String("OD") ? QStringLiteral("OD (Right)") : QStringLiteral("OS (Left)");
                for (QPushButton* button : window.findChildren<QPushButton*>()) {
                    if (button->text() == target) { button->click(); break; }
                }
            });
        }
        if(!requestedView.isEmpty()) {
            QTimer::singleShot(3300,&window,[&window,requestedView,&application] {
                for(auto *button:window.findChildren<QPushButton*>()) {
                    if(button->isVisible()&&(button->text()==requestedView||button->accessibleName()==requestedView||button->accessibleName().startsWith("Report eye: "+requestedView))) { button->click(); return; }
                }
                QTextStream(stderr)<<"Screenshot view not found: "<<requestedView<<'\n'; application.exit(6);
            });
        }
        QTimer::singleShot(!requestedView.isEmpty() || selections.size() >= 2 ? 3900 : 3200, &window, [&window, destination, &application] {
            if (!window.grab().save(destination)) {
                QTextStream(stderr) << "Could not save screenshot: " << destination << '\n';
                application.exit(5);
                return;
            }
            application.quit();
        });
    }
    return application.exec();
}
