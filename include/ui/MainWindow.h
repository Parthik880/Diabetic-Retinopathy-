#pragma once

#include <QDateTime>
#include <QImage>
#include <QMainWindow>
#include <QQueue>
#include <QVariantMap>
#include <QVector>

class QComboBox;
class QLabel;
class QPushButton;
class QScrollArea;
class QStackedWidget;
class QVBoxLayout;

namespace retina {

class MainWindow final : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);
    QVariantMap reportData(const QString &eye) const;
    bool rememberReportPath(const QString &sessionId, const QString &eye,
                            const QVariantMap &result, const QString &pdfPath);

public slots:
    void setBusy(bool busy);
    void setProgress(QString eye, QString stage);
    void setEyeResult(QString eye, QVariantMap result);
    void setEyeError(QString eye, QString message);
    void setPatient(QVariantMap patient);
    void setStatus(QString message);
    void setBatchStatus(QString message);
    void setBatchSnapshot(QVariantMap snapshot);
    void setBatchCapacity(QVariantMap capacity);
    void discoverBatch(QString directory);
    void setHistoryDownloadResult(QString eye, QString path, QString error);

signals:
    void analyzeRequested(QString eye, QString path);
    void reportRequested(QString eye, QString destination);
    void bothReportsRequested(QString sessionId, QString destination);
    void historyReportDownloadRequested(QString sessionId, QString eye, QVariantMap result, QString destination);
    void batchRequested(QString inputDirectory, QString outputDirectory);
    void batchPlanRequested(QVariantList images, QString outputDirectory, bool patientFolders);
    void batchControlRequested(QString action);
    void patientChanged(QVariantMap patient);

private:
    struct EyeState {
        QString imagePath;
        QDateTime capturedAt;
        QVariantMap result;
        QString stage;
        QString error;
    };
    struct PatientState {
        QVariantMap details;
        EyeState os;
        EyeState od;
    };
    struct HistoryEntry {
        PatientState patient;
        QDateTime savedAt;
    };
    static QString historySessionId(const HistoryEntry &entry);

    enum Page { Capture, Analysis, Compare, Report, History, Batch, Cloud, PageCount };
    enum View { GradeView, AttentionView, DetectionView, AnnotationView };

    void buildShell();
    void loadState();
    bool saveState() const;
    void recordHistory();
    void rebuildPage(Page page);
    void rebuildAll();
    void navigate(Page page);
    void refreshHeader();
    void updateCaptureAction();
    bool eventFilter(QObject *watched, QEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;
    void refreshResponsiveHeader();
    void registerPatient();
    void startNewSession();
    void chooseImage(QString eye);
    void requestAnalysis();
    void dispatchNextEye();
    void requestReport(QString eye);
    void requestHistoryReportDownload(const QString &sessionId, const QString &eye, const QVariantMap &result);
    QWidget *buildCapture();
    QWidget *buildAnalysis();
    QWidget *buildCompare();
    QWidget *buildReport();
    QWidget *buildHistory();
    QWidget *buildBatch();
    QWidget *buildCloud();
    QWidget *buildVisualization(QString eye, View view, bool compact = false);
    QWidget *buildEyeCard(QString eye);
    QWidget *buildPageFrame(const QString &title, const QString &subtitle, QVBoxLayout **content);
    QWidget *buildEmptyState(const QString &icon, const QString &title, const QString &message);
    QString assetPath(const QString &name) const;
    QString imagePath(const QString &eye) const;
    QString eyeName(const QString &eye) const;
    QString gradeText(const QVariantMap &result) const;
    QString resultState(const QString &eye) const;
    QVariantMap resultFor(const QString &eye) const;
    EyeState *eyeState(const QString &eye, int patientIndex = -1);
    const EyeState *eyeState(const QString &eye, int patientIndex = -1) const;
    QImage visualizationImage(const QString &eye, View view, bool compact) const;
    QList<QVariantMap> displayedRegions(const QVariantMap &result) const;
    QStringList availableLesionClasses(const QVariantMap &result) const;
    QString regionKey(const QVariantMap &region) const;

    QStackedWidget *pages_ = nullptr;
    QScrollArea *scrolls_[PageCount] = {};
    QPushButton *navButtons_[PageCount] = {};
    QComboBox *patientSelector_ = nullptr;
    QLabel *headerStatus_ = nullptr;
    QLabel *progressStatus_ = nullptr;
    QPushButton *analyzeButton_ = nullptr;
    QVector<PatientState> patients_;
    QVector<HistoryEntry> history_;
    int currentPatient_ = -1;
    int activePatient_ = -1;
    QString activeAnalysisEye_;
    QString activeEye_ = QStringLiteral("OS");
    QQueue<QString> analysisQueue_;
    bool busy_ = false;
    Page currentPage_ = Capture;
    View analysisView_ = GradeView;
    View compareView_ = GradeView;
    int opacity_ = 50;
    int topK_ = 25;
    QString regionClass_ = QStringLiteral("all");
    bool showCoordinates_ = false;
    bool showRawRegions_ = false;
    QString gradeMode_ = QStringLiteral("Overlay");
    QString attentionMode_ = QStringLiteral("Overlay");
    QString annotationMode_ = QStringLiteral("Overlay");
    QString attentionType_ = QStringLiteral("Probability");
    QString lesionClass_ = QStringLiteral("HE");
    QStringList enabledMaskClasses_ = {QStringLiteral("MA"),QStringLiteral("HE"),QStringLiteral("EX"),QStringLiteral("SE")};
    QString selectedRegion_;
    QPointF coordinateCursor_;
    bool hasCoordinateCursor_ = false;
    QString batchInput_;
    QString batchOutput_;
    QString batchStatus_;
    QVariantMap batchSnapshot_;
    QVariantMap batchCapacity_;
    QMap<QString,QString> batchSelections_;
    bool batchReviewed_ = false;
    bool showBatchPatients_ = false;
    bool batchPatientFolders_ = true;
    bool batchSkipUnresolved_ = true;
    QString historyQuery_;
    int historyDateFilter_ = 0;
    int historyEyeFilter_ = 0;
    int historyPage_ = 1;
    QString selectedHistoryPatientId_;
    QString historyNotice_;
    QString historyError_;
    QVariantMap historyReport_;
    QString stateLoadError_;
    int historyLayoutBreakpoint_ = -1;
};

} // namespace retina
