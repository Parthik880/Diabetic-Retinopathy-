#pragma once

#include <QObject>
#include <QPair>
#include <QQueue>
#include <QThread>
#include <QVariantMap>

#include <memory>
#include <atomic>
#include <condition_variable>
#include <mutex>

namespace retina { class MainWindow; }
class ModelManager;

class AnalysisWorker final : public QObject {
    Q_OBJECT
public:
    explicit AnalysisWorker(QObject* parent = nullptr);
    ~AnalysisWorker() override;
    void controlBatch(const QString &action);

public slots:
    void initialize();
    void analyze(const QString& eye, const QString& imagePath);
    void processBatch(const QString& inputDirectory, const QString& outputDirectory);
    void processBatchPlan(QVariantList images, QString outputDirectory, bool patientFolders);

signals:
    void initialized(bool ready, const QString& message);
    void progress(const QString& eye, const QString& stage);
    void completed(const QString& eye, const QVariantMap& result);
    void batchProgress(const QString& message);
    void batchFinished(const QString& message);
    void batchSnapshot(const QVariantMap& snapshot);
    void batchCapacity(const QVariantMap& capacity);

private:
    std::unique_ptr<ModelManager> models_;
    std::atomic<bool> batchPaused_{false};
    std::atomic<bool> batchCancelled_{false};
    std::mutex batchMutex_;
    std::condition_variable batchWake_;
};

class AnalysisController final : public QObject {
    Q_OBJECT
public:
    explicit AnalysisController(retina::MainWindow* window, QObject* parent = nullptr);
    ~AnalysisController() override;

private slots:
    void enqueueAnalysis(const QString& eye, const QString& imagePath);
    void onInitialized(bool ready, const QString& message);
    void onCompleted(const QString& eye, const QVariantMap& result);
    void saveReport(const QString& eye, const QString& destination);
    void saveBothReports(const QString& sessionId, const QString& destination);
    void saveHistoryReport(const QString& sessionId, const QString& eye, const QVariantMap& result, const QString& destination);
    void enqueueBatch(const QString& inputDirectory, const QString& outputDirectory);
    void enqueueBatchPlan(QVariantList images,QString outputDirectory,bool patientFolders);
    void controlBatch(QString action);
    void onBatchFinished(const QString& message);

private:
    void startNext();

    retina::MainWindow* window_;
    QThread workerThread_;
    AnalysisWorker* worker_;
    QQueue<QPair<QString, QString>> pending_;
    QMap<QString, QVariantMap> results_;
    bool ready_ = false;
    bool active_ = false;
    QString initializationError_;
};
