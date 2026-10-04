#include "app/AnalysisController.h"

#include "inference/ModelManager.h"
#include "image/ImageDecoder.h"
#include "image/EyeAssignment.h"
#include "ui/MainWindow.h"
#include "reporting/ScreeningReport.h"
#include "reporting/ReportBundle.h"

#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QDirIterator>
#include <QFileInfo>
#include <QFile>
#include <QImage>
#include <QJsonDocument>
#include <QMessageBox>
#include <QMetaObject>
#include <QRegularExpression>
#include <QStandardPaths>

#include <exception>
#include <algorithm>
#include <cmath>
#include <cuda_runtime_api.h>

AnalysisWorker::AnalysisWorker(QObject* parent) : QObject(parent) {}
AnalysisWorker::~AnalysisWorker() = default;

void AnalysisWorker::initialize() {
    try {
        models_ = std::make_unique<ModelManager>();
        const bool ready = models_->initialize();
        QVariantMap capacity{{"available",false}};
        int device=0; cudaDeviceProp properties{};
        if(qEnvironmentVariableIntValue("RETINAGRAM_FORCE_CPU")!=1 && cudaGetDevice(&device)==cudaSuccess && cudaGetDeviceProperties(&properties,device)==cudaSuccess) {
            double mb=properties.totalGlobalMem/(1024.0*1024.0);
            capacity={{"available",true},{"name",QString::fromUtf8(properties.name)},{"vram_mb",mb},{"max_batch_size",std::max(1,int(std::floor(0.006*mb+41.66)))}};
        }
        emit batchCapacity(capacity);
        emit initialized(ready, ready ? QString{} : models_->lastError());
    } catch (const std::exception& error) {
        emit initialized(false, QString::fromUtf8(error.what()));
    }
}

void AnalysisWorker::analyze(const QString& eye, const QString& imagePath) {
    QVariantMap result;
    try {
        if (!models_ || !models_->isReady()) {
            throw std::runtime_error("Inference models are unavailable.");
        }
        result = models_->analyzeImage(eye, imagePath, [this, eye](const QString& stage) {
            emit progress(eye, stage);
        });
    } catch (const std::exception& error) {
        result.insert(QStringLiteral("state"), QStringLiteral("FAILED"));
        result.insert(QStringLiteral("image_path"), imagePath);
        result.insert(QStringLiteral("error"), QString::fromUtf8(error.what()));
    }
    emit completed(eye, result);
}

void AnalysisWorker::processBatch(const QString& inputDirectory, const QString& outputDirectory) {
    if (!models_ || !models_->isReady()) {
        emit batchFinished(QStringLiteral("Batch failed: inference models are unavailable."));
        return;
    }
    const QStringList filters{QStringLiteral("*.jpg"), QStringLiteral("*.jpeg"), QStringLiteral("*.png"),
                              QStringLiteral("*.bmp"), QStringLiteral("*.tif"), QStringLiteral("*.tiff")};
    QStringList images;
    QDirIterator iterator(inputDirectory, filters, QDir::Files, QDirIterator::Subdirectories);
    while (iterator.hasNext()) images << iterator.next();
    images.sort(Qt::CaseInsensitive);
    if (images.isEmpty()) {
        emit batchFinished(QStringLiteral("Batch failed: no supported images were found."));
        return;
    }
    for (const QString& image : images) {
        const QFileInfo source(image);
        if (retina::eyeFromBatchPath(QDir(inputDirectory).relativeFilePath(image)).isEmpty()) {
            emit batchFinished(QStringLiteral("Batch failed: eye assignment is missing or ambiguous for %1. Label each file or its patient folder OS/OD (or LEFT/RIGHT).").arg(source.fileName()));
            return;
        }
    }
    QVariantList plan;
    for(const auto &image:images) {
        const QFileInfo source(image);
        const QString relative=QDir(inputDirectory).relativeFilePath(image);
        QString parent=QFileInfo(relative).path();
        if(parent==".") {
            QString upper=source.completeBaseName().toUpper();
            int eyeIndex=std::max(upper.lastIndexOf("_OS"),upper.lastIndexOf("_OD"));
            if(eyeIndex>0) parent=source.completeBaseName().left(eyeIndex);
        }
        plan.append(QVariantMap{{"source_path",image},{"eye",retina::eyeFromBatchPath(relative)},{"patient_id",parent}});
    }
    processBatchPlan(plan,outputDirectory,true);
}

void AnalysisWorker::controlBatch(const QString &action) {
    if(action=="pause") batchPaused_=true;
    else if(action=="resume") { batchPaused_=false; batchWake_.notify_all(); }
    else if(action=="cancel") { batchCancelled_=true; batchPaused_=false; batchWake_.notify_all(); }
    else if(action=="reset") { batchCancelled_=false; batchPaused_=false; }
}

void AnalysisWorker::processBatchPlan(QVariantList images,QString outputDirectory,bool patientFolders) {
    if(!models_ || !models_->isReady()) { emit batchFinished("Batch failed: inference models are unavailable."); return; }
    int complete=0,recapture=0,failed=0;
    for(int index=0;index<images.size();++index) {
        if(batchPaused_ && !batchCancelled_) {
            emit batchSnapshot(QVariantMap{{"state","Paused"},{"stage_label","Paused between images"}});
            std::unique_lock lock(batchMutex_);
            batchWake_.wait(lock,[this] { return !batchPaused_ || batchCancelled_; });
        }
        if(batchCancelled_) {
            emit batchSnapshot(QVariantMap{{"state","Cancelled"},{"stage_label","Batch cancelled"},{"counts",QVariantMap{{"processing",0}}}});
            emit batchFinished("Batch cancelled between images."); return;
        }
        const auto item=images[index].toMap(); const QString path=item.value("source_path").toString();
        const QFileInfo source(path); const QString eye=item.value("eye").toString();
        const bool reviewedPlan=item.contains("patient_folder");
        const QString group=item.value(patientFolders?"patient_folder":"anonymous_folder").toString();
        const QString destination=reviewedPlan?QDir(outputDirectory).filePath(group+(eye=="OS"?"/Left_OS":"/Right_OD")):patientFolders?QDir(outputDirectory).filePath(item.value("patient_id").toString()):outputDirectory;
        QString stem=source.completeBaseName();
        if(!patientFolders&&!reviewedPlan) stem=item.value("patient_id").toString()+"_"+eye+"_"+stem;
        auto update=[&](QString stage,int stageIndex,QString status="Processing") {
            emit batchSnapshot(QVariantMap{{"state","Processing"},{"source_path",path},{"eye_status",status},{"stage_label",stage},
                {"progress_percent",100.0*(index*4+stageIndex)/(images.size()*4)},
                {"counts",QVariantMap{{"completed",complete},{"processing",status=="Processing"?1:0},{"recapture_required",recapture},{"failed",failed}}}});
        };
        update("Preparing "+source.fileName(),0);
        emit batchProgress(QString("Batch %1/%2 · %3").arg(index+1).arg(images.size()).arg(source.fileName()));
        QVariantMap result;
        if(!QDir().mkpath(destination)) { ++failed; update("Output directory could not be created",4,"Failed"); continue; }
        try {
            result=models_->analyzeImage(eye,path,[&](QString stage) {
                int step=stage.contains("LESION")?3:stage.contains("GRAD")||stage.contains("GRADE")?2:1;
                update(stage,step);
            });
        } catch(const std::exception &error) { result={{"state","FAILED"},{"error",QString::fromUtf8(error.what())}}; }
        const QString state=result.value("state").toString();
        QFile file(QDir(destination).filePath(stem+"_analysis.json"));
        if(!file.open(QIODevice::WriteOnly)) { ++failed; update("Result could not be saved",4,"Failed"); continue; }
        file.write(QJsonDocument::fromVariant(result).toJson(QJsonDocument::Indented)); file.close();
        QString status;
        if(state=="COMPLETE") {
            if(retina::reporting::writePdf(QDir(destination).filePath(stem+"_report.pdf"),
                retina::reporting::withContext(result,{{"patientIdNumber",item.value("patient_id")},{"name",item.value("patient_name")}},eye,QDateTime::currentDateTime()))) { ++complete; status="Completed"; }
            else { ++failed; status="Failed"; }
        } else if(state=="RECAPTURE_REQUIRED") { ++recapture; status="Recapture Required"; }
        else { ++failed; status="Failed"; }
        update(status,4,status);
    }
    emit batchSnapshot(QVariantMap{{"state","Completed"},{"stage_label","Batch finished"},{"progress_percent",100},
        {"counts",QVariantMap{{"completed",complete},{"processing",0},{"recapture_required",recapture},{"failed",failed}}}});
    emit batchFinished(QString("Batch finished · %1 reports · %2 recapture · %3 failed · %4 images").arg(complete).arg(recapture).arg(failed).arg(images.size()));
}

AnalysisController::AnalysisController(retina::MainWindow* window, QObject* parent)
    : QObject(parent), window_(window), worker_(new AnalysisWorker) {
    worker_->moveToThread(&workerThread_);
    connect(worker_,&AnalysisWorker::batchCapacity,window_,&retina::MainWindow::setBatchCapacity);
    connect(worker_,&AnalysisWorker::batchSnapshot,window_,&retina::MainWindow::setBatchSnapshot);
    connect(window_,&retina::MainWindow::batchPlanRequested,this,&AnalysisController::enqueueBatchPlan);
    connect(window_,&retina::MainWindow::batchControlRequested,this,&AnalysisController::controlBatch);
    connect(&workerThread_, &QThread::started, worker_, &AnalysisWorker::initialize);
    connect(&workerThread_, &QThread::finished, worker_, &QObject::deleteLater);
    connect(worker_, &AnalysisWorker::initialized, this, &AnalysisController::onInitialized);
    connect(worker_, &AnalysisWorker::progress, window_, &retina::MainWindow::setProgress);
    connect(worker_, &AnalysisWorker::completed, this, &AnalysisController::onCompleted);
    connect(worker_, &AnalysisWorker::batchProgress, window_, &retina::MainWindow::setBatchStatus);
    connect(worker_, &AnalysisWorker::batchFinished, this, &AnalysisController::onBatchFinished);
    connect(window_, &retina::MainWindow::analyzeRequested,
            this, &AnalysisController::enqueueAnalysis);
    connect(window_, &retina::MainWindow::reportRequested,
            this, &AnalysisController::saveReport);
    connect(window_, &retina::MainWindow::bothReportsRequested,
            this, &AnalysisController::saveBothReports);
    connect(window_, &retina::MainWindow::historyReportDownloadRequested,
            this, &AnalysisController::saveHistoryReport);
    connect(window_, &retina::MainWindow::batchRequested,
            this, &AnalysisController::enqueueBatch);
    window_->setBusy(true);
    workerThread_.start();
}

AnalysisController::~AnalysisController() {
    worker_->controlBatch("cancel");
    workerThread_.quit();
    workerThread_.wait();
}

void AnalysisController::enqueueAnalysis(const QString& eye, const QString& imagePath) {
    if (eye != QStringLiteral("OS") && eye != QStringLiteral("OD")) {
        window_->setEyeError(eye, QStringLiteral("Unsupported eye selection."));
        return;
    }
    if (imagePath.isEmpty()) {
        window_->setEyeError(eye, QStringLiteral("Choose a retinal image first."));
        return;
    }
    if (!ready_ && !initializationError_.isEmpty()) {
        window_->setEyeError(eye, initializationError_);
        return;
    }
    pending_.enqueue(qMakePair(eye, imagePath));
    window_->setBusy(true);
    startNext();
}

void AnalysisController::onInitialized(bool ready, const QString& message) {
    ready_ = ready;
    initializationError_ = message;
    if (ready_) {
        window_->setStatus(QStringLiteral("Native models ready for analysis."));
        if (pending_.isEmpty()) window_->setBusy(false);
        startNext();
    } else {
        const QString error = QStringLiteral("Model initialization failed: %1").arg(message);
        window_->setEyeError(QStringLiteral("OS"), error);
        window_->setEyeError(QStringLiteral("OD"), error);
        window_->setBusy(false);
        pending_.clear();
    }
}

void AnalysisController::startNext() {
    if (!ready_ || active_ || pending_.isEmpty()) return;
    active_ = true;
    const auto [eye, path] = pending_.dequeue();
    QMetaObject::invokeMethod(worker_, [worker = worker_, eye, path] {
        worker->analyze(eye, path);
    }, Qt::QueuedConnection);
}

void AnalysisController::onCompleted(const QString& eye, const QVariantMap& result) {
    active_ = false;
    results_.insert(eye, result);
    if (result.value(QStringLiteral("state")).toString() == QStringLiteral("FAILED")) {
        window_->setEyeError(eye, result.value(QStringLiteral("error")).toString());
    } else {
        window_->setEyeResult(eye, result);
    }
    if (pending_.isEmpty()) window_->setBusy(false);
    startNext();
}

void AnalysisController::enqueueBatch(const QString& inputDirectory, const QString& outputDirectory) {
    if (!ready_ || active_) {
        window_->setBatchStatus(QStringLiteral("Batch cannot start while model loading or another analysis is active."));
        return;
    }
    active_ = true;
    worker_->controlBatch("reset");
    window_->setBusy(true);
    QMetaObject::invokeMethod(worker_, [worker = worker_, inputDirectory, outputDirectory] {
        worker->processBatch(inputDirectory, outputDirectory);
    }, Qt::QueuedConnection);
}

void AnalysisController::enqueueBatchPlan(QVariantList images,QString outputDirectory,bool patientFolders) {
    if(!ready_||active_) { window_->setBatchSnapshot({{"state","Review"}}); window_->setBatchStatus("Batch failed: model loading or another analysis is active."); return; }
    active_=true; worker_->controlBatch("reset"); window_->setBusy(true);
    QMetaObject::invokeMethod(worker_,[worker=worker_,images,outputDirectory,patientFolders] { worker->processBatchPlan(images,outputDirectory,patientFolders); },Qt::QueuedConnection);
}
void AnalysisController::controlBatch(QString action) {
    worker_->controlBatch(action);
    window_->setBatchSnapshot({{"state",action=="pause"?"Pausing":action=="resume"?"Processing":"Cancelling"},{"stage_label",action=="pause"?"Pause requested; finishing current image":action=="resume"?"Resuming batch":"Cancel requested; finishing current image"}});
}

void AnalysisController::onBatchFinished(const QString& message) {
    active_ = false;
    window_->setBusy(false);
    window_->setBatchStatus(message);
    startNext();
}

void AnalysisController::saveReport(const QString& eye, const QString& destination) {
    const QVariantMap result = window_->reportData(eye);
    try {
        const auto exported=retina::reporting::exportReportBundle(destination,result);
        const bool persisted=window_->rememberReportPath({},eye,result,exported.reportPath);
        window_->setStatus("Report saved to: "+exported.rootFolder+(persisted?QString{}:" (History path could not be persisted.)"));
    } catch(const std::exception& error) {
        window_->setStatus("Report export failed: "+QString::fromUtf8(error.what()));
    }
}

void AnalysisController::saveBothReports(const QString& sessionId, const QString& destination) {
    const auto left=window_->reportData("OS"),right=window_->reportData("OD");
    try {
        const auto exported=retina::reporting::exportReportBundles(destination,{left,right});
        const bool leftSaved=window_->rememberReportPath(sessionId,"OS",left,exported.eyes[0].reportPath);
        const bool rightSaved=window_->rememberReportPath(sessionId,"OD",right,exported.eyes[1].reportPath);
        window_->setStatus("Both eye reports saved to: "+exported.rootFolder+(leftSaved&&rightSaved?QString{}:" (History paths could not be persisted.)"));
    } catch(const std::exception& error) {
        window_->setStatus("Report export failed: "+QString::fromUtf8(error.what()));
    }
}

void AnalysisController::saveHistoryReport(const QString& sessionId, const QString& eye,
                                           const QVariantMap& result, const QString& destination) {
    try {
        const auto exported=retina::reporting::exportReportBundle(destination,result);
        const bool persisted=window_->rememberReportPath(sessionId,eye,result,exported.reportPath);
        window_->setHistoryDownloadResult(eye,exported.rootFolder,persisted?QString{}:"Bundle saved to "+exported.rootFolder+", but the History path could not be persisted.");
    } catch(const std::exception& error) {
        window_->setHistoryDownloadResult(eye,{},QString::fromUtf8(error.what()));
    }
}
