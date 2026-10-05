#include "ui/MainWindow.h"
#include "image/EyeAssignment.h"
#include "image/ImageDecoder.h"
#include "ui/UiComponents.h"
#include "reporting/ScreeningReport.h"
#include <QAbstractItemView>

#include <QApplication>
#include <QAction>
#include <QCheckBox>
#include <QComboBox>
#include <QCryptographicHash>
#include <QCoreApplication>
#include "core/AppPaths.h"
#include <QDesktopServices>
#include <QDialog>
#include <QDialogButtonBox>
#include <QEvent>
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QJsonDocument>
#include <QFontDatabase>
#include <QFormLayout>
#include <QFrame>
#include <QGridLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QImageReader>
#include <QLabel>
#include <QLineEdit>
#include <QLocale>
#include <QMessageBox>
#include <QMenu>
#include <QPainter>
#include <QPushButton>
#include <QRandomGenerator>
#include <QResizeEvent>
#include <QScrollArea>
#include <QScrollBar>
#include <QSaveFile>
#include <QSignalBlocker>
#include <QSlider>
#include <QSpinBox>
#include <QStackedWidget>
#include <QStyle>
#include <QStandardPaths>
#include <QTableWidget>
#include <QTextEdit>
#include <QUrl>
#include <QUuid>
#include <QVBoxLayout>
#include <algorithm>

namespace retina {
namespace {

constexpr auto kPrimary = "#005227";
constexpr auto kMuted = "#3f4940";
constexpr auto kOutline = "#becabd";
constexpr auto kError = "#ba1a1a";

class PatientSelector final : public QComboBox {
public:
    QSize sizeHint() const override { return {300,44}; }
    void showPopup() override {
        QComboBox::showPopup();
        view()->setMinimumWidth(0);
        view()->window()->setFixedWidth(qBound(300,width()+2,340));
        view()->setTextElideMode(Qt::ElideRight);
    }
};

class HistoryStickySlot final : public QWidget {
public:
    HistoryStickySlot(QWidget *panel, QScrollArea *scrollArea, QWidget *parent = nullptr)
        : QWidget(parent), panel_(panel), scrollArea_(scrollArea) {
        panel_->setParent(this);
        panel_->setMinimumHeight(420);
        connect(scrollArea_->verticalScrollBar(), &QScrollBar::valueChanged, this, [this] { placePanel(); });
    }

    QSize sizeHint() const override { return QSize(500, qMax(420, panel_->sizeHint().height())); }
    QSize minimumSizeHint() const override { return QSize(390, 420); }

protected:
    void resizeEvent(QResizeEvent *event) override {
        QWidget::resizeEvent(event);
        placePanel();
    }

private:
    void placePanel() {
        if (!panel_ || !scrollArea_ || !scrollArea_->widget()) return;
        const int baseY = mapTo(scrollArea_->widget(), QPoint(0, 0)).y();
        const int height = qMin(this->height(), qMax(420, panel_->sizeHint().height()));
        const int maxOffset = qMax(0, this->height() - height);
        const int offset = qBound(0, scrollArea_->verticalScrollBar()->value() + 96 - baseY, maxOffset);
        panel_->setGeometry(0, offset, width(), height);
    }

    QWidget *panel_ = nullptr;
    QScrollArea *scrollArea_ = nullptr;
};

QLabel *label(const QString &text, int points = 11, bool bold = false, const QString &color = {}) {
    auto *result = new QLabel(text);
    result->setWordWrap(true);
    auto font = result->font();
    font.setPointSize(points);
    font.setBold(bold);
    if (bold && points >= 16) {
        font.setFamily(QStringLiteral("Manrope"));
        font.setWeight(QFont::ExtraBold);
    }
    result->setFont(font);
    if (!color.isEmpty()) result->setStyleSheet(QStringLiteral("color: %1;").arg(color));
    return result;
}

QFrame *card() {
    auto *result = new QFrame;
    result->setObjectName(QStringLiteral("Card"));
    result->setFrameShape(QFrame::NoFrame);
    return result;
}

QPushButton *button(const QString &text, bool primary = false) {
    auto *result = new QPushButton(text);
    result->setObjectName(primary ? QStringLiteral("PrimaryButton") : QStringLiteral("SecondaryButton"));
    result->setMinimumHeight(44);
    result->setCursor(Qt::PointingHandCursor);
    return result;
}

QVBoxLayout *column(QWidget *widget, int margin = 20, int spacing = 14) {
    auto *layout = new QVBoxLayout(widget);
    layout->setContentsMargins(margin, margin, margin, margin);
    layout->setSpacing(spacing);
    return layout;
}

QString percent(const QVariant &value) {
    if (!value.isValid() || value.isNull()) return QStringLiteral("Unavailable");
    const double number = value.toDouble();
    return QString::number(number <= 1.0 ? number * 100.0 : number, 'f', 1) + '%';
}

QString textOr(const QVariantMap &map, const QString &key, const QString &fallback) {
    const QString value = map.value(key).toString().trimmed();
    return value.isEmpty() ? fallback : value;
}

QString valueString(const QVariantMap &map, const QString &key, const QString &fallback = QStringLiteral("—")) {
    const QVariant value = map.value(key);
    return value.isValid() && !value.isNull() && !value.toString().isEmpty() ? value.toString() : fallback;
}

void addLabeledValue(QGridLayout *layout, int row, int col, const QString &name, const QString &value) {
    auto *box = new QWidget;
    auto *inside = column(box, 0, 2);
    inside->addWidget(label(name.toUpper(), 9, true, kMuted));
    inside->addWidget(label(value, 12, true));
    layout->addWidget(box, row, col);
}

} // namespace

MainWindow::MainWindow(QWidget *parent) : QMainWindow(parent) {
    setWindowTitle(QStringLiteral("RetinaGram GPU"));
    resize(1440, 960);
    setMinimumSize(800, 650);
    for (const QString &font : {QStringLiteral("Atkinson-Regular.ttf"), QStringLiteral("Atkinson-Bold.ttf"),
                                QStringLiteral("Manrope-Regular.ttf"), QStringLiteral("Manrope-Bold.ttf"),
                                QStringLiteral("MaterialSymbols.ttf")}) {
        QFontDatabase::addApplicationFont(assetPath(QStringLiteral("fonts/") + font));
    }
    setFont(QFont(QStringLiteral("Atkinson Hyperlegible Next"), 10));
    setStyleSheet(QStringLiteral(R"(
        QMainWindow, QWidget#Shell, QScrollArea, QScrollArea > QWidget > QWidget { background: #f6fbf3; color: #181d18; }
        QDialog { background: #f6fbf3; color: #181d18; }
        QLabel, QCheckBox, QRadioButton { color: #181d18; }
        QFrame#Card { background: #ffffff; border: 1px solid #becabd; border-radius: 12px; }
        QFrame#SoftCard { background: #f0f5ed; border: 1px solid #becabd; border-radius: 12px; }
        QFrame#Header { background: #ffffff; border-bottom: 1px solid #becabd; }
        QWidget#NavContainer { background: #f0f5ed; border-radius: 12px; }
        QPushButton#NavButton { background: transparent; color: #3f4940; border: 0; border-radius: 8px; font-weight: 700; }
        QPushButton#NavButton:hover { background: #dfe4dc; }
        QPushButton#NavButton[active="true"] { background: #005227; color: white; }
        QPushButton#NavButton[active="true"] QLabel { color: white; }
        QPushButton#PrimaryButton { background: #005227; color: white; border: 1px solid #005227; border-radius: 10px; padding: 8px 16px; font-weight: 700; font-size: 12px; }
        QPushButton#PrimaryButton:hover { background: #006d36; }
        QPushButton#SecondaryButton { background: white; color: #005227; border: 1px solid #6f7a6f; border-radius: 10px; padding: 8px 16px; font-weight: 700; font-size: 12px; }
        QPushButton#SecondaryButton:hover { background: #f0f5ed; }
        QPushButton:disabled { background: #dfe4dc; color: #6f7a6f; border-color: #dfe4dc; }
        QPushButton#PrimaryButton:disabled, QPushButton#SecondaryButton:disabled { background: #dfe4dc; color: #6f7a6f; border-color: #dfe4dc; }
        QLineEdit, QComboBox, QSpinBox, QTextEdit { background: white; color: #181d18; border: 1px solid #6f7a6f; border-radius: 8px; padding: 8px 12px; min-height: 32px; font-size: 12px; }
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border: 2px solid #005227; }
        QTableWidget { background: white; color: #181d18; gridline-color: #becabd; border: 1px solid #becabd; }
        QHeaderView::section { background: #f0f5ed; color: #3f4940; border: 0; border-bottom: 1px solid #becabd; padding: 10px; font-weight: 700; font-size: 11px; }
        QSlider::groove:horizontal { background: #dfe4dc; height: 6px; border-radius: 3px; }
        QSlider::sub-page:horizontal { background: #005227; height: 6px; border-radius: 3px; }
        QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; border: 1px solid #6f7a6f; border-radius: 3px; background: white; }
        QCheckBox::indicator:checked, QRadioButton::indicator:checked { background: #005227; border: 3px solid #9bf6b1; }
        QRadioButton::indicator { border-radius: 8px; }
        QSlider::handle:horizontal { background: #005227; width: 16px; margin: -5px 0; border-radius: 8px; }
        QComboBox#PatientSelector { background: #f0f5ed; border: 1px solid #becabd; border-radius: 12px; padding: 6px 12px; min-height: 32px; }
        QComboBox#PatientSelector::drop-down { border: none; width: 24px; }
        QComboBox#EyeSelector { background: #f0f5ed; border: 1px solid #becabd; border-radius: 8px; padding: 6px 28px 6px 12px; min-height: 20px; font-size: 14px; }
        QComboBox#EyeSelector::drop-down { border: none; width: 24px; }
        QScrollBar:vertical { background: #f0f5ed; width: 6px; margin: 0; }
        QScrollBar::handle:vertical { background: #becabd; min-height: 24px; border-radius: 3px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    )"));
    setStyleSheet(styleSheet() + QStringLiteral(
        "QComboBox::drop-down { border: none; width: 24px; }"
        "QComboBox::down-arrow { image: url(\"%1\"); width: 12px; height: 8px; }").arg(assetPath(QStringLiteral("chevron-down.xpm"))));
    setStyleSheet(styleSheet()+QStringLiteral(
        "QCheckBox::indicator:checked { image:url(\"%1\"); background:#005227; border:1px solid #005227; }"
        "QCheckBox::indicator:disabled { background:#dfe4dc; border-color:#becabd; }"
        "QCheckBox::indicator:checked:disabled { background:#dfe4dc; border-color:#becabd; }").arg(assetPath(QStringLiteral("check.xpm"))));
    buildShell();
    loadState();
    rebuildAll();
    navigate(Capture);
}

QString MainWindow::assetPath(const QString &name) const {
    return AppPaths::assetsPath(name);
}

void MainWindow::buildShell() {
    auto *shell = new QWidget;
    shell->setObjectName(QStringLiteral("Shell"));
    auto *root = new QVBoxLayout(shell);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    auto *header = new QFrame;
    header->setObjectName(QStringLiteral("Header"));
    header->setFixedHeight(72);
    auto *headerLayout = new QHBoxLayout(header);
    headerLayout->setContentsMargins(24, 0, 24, 0);
    headerLayout->addStretch();
    auto *headerInner = new QWidget;
    headerInner->setMaximumWidth(1600);
    headerLayout->addWidget(headerInner, 1);
    headerLayout->addStretch();
    auto *top = new QHBoxLayout(headerInner);
    top->setContentsMargins(0, 8, 0, 8);
    top->setSpacing(8);
    auto *brand = new QWidget;
    auto *brandRow = new QHBoxLayout(brand);
    brandRow->setContentsMargins(0, 0, 0, 0);
    brandRow->setSpacing(12);
    auto *logo = new QLabel;
    logo->setFixedSize(44, 44);
    const QPixmap logoImage(assetPath(QStringLiteral("logo.jpeg")));
    if (!logoImage.isNull()) logo->setPixmap(logoImage.scaled(44, 44, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation));
    logo->setStyleSheet(QStringLiteral("border-radius: 13px;"));
    brandRow->addWidget(logo);
    auto *brandText = new QWidget;
    auto *brandColumn = column(brandText, 0, 1);
    auto *brandName = label(QStringLiteral("RetinaGram GPU"), 14, true, kPrimary);
    auto brandFont = brandName->font();
    brandFont.setFamily(QStringLiteral("Manrope"));
    brandFont.setPixelSize(19);
    brandName->setFont(brandFont);
    brandName->setWordWrap(false);
    brandColumn->addWidget(brandName);
    auto *brandSubtitle = label(QStringLiteral("AI Retinal Screening"), 8, true, kMuted);
    brandSubtitle->setWordWrap(false);
    brandColumn->addWidget(brandSubtitle);
    brandRow->addWidget(brandText);
    top->addWidget(brand);

    const QStringList names = {QStringLiteral("Capture"), QStringLiteral("Analysis"), QStringLiteral("Compare"),
                               QStringLiteral("Report"), QStringLiteral("History"), QStringLiteral("Batch Analysis")};
    const QStringList icons = {QStringLiteral("add_a_photo"), QStringLiteral("analytics"), QStringLiteral("compare"),
                               QStringLiteral("description"), QStringLiteral("history"), QStringLiteral("stacks")};
    auto *nav = new QWidget;
    nav->setObjectName(QStringLiteral("NavContainer"));
    auto *navRow = new QHBoxLayout(nav);
    navRow->setContentsMargins(4, 4, 4, 4);
    navRow->setSpacing(4);
    for (int index = 0; index < names.size(); ++index) {
        auto *item = new QPushButton;
        item->setObjectName(QStringLiteral("NavButton"));
        item->setFixedHeight(40);
        item->setAccessibleName(names[index]);
        item->setCursor(Qt::PointingHandCursor);
        auto *itemLayout = new QHBoxLayout(item);
        itemLayout->setContentsMargins(12, 6, 12, 6);
        itemLayout->setSpacing(6);
        auto *iconLabel = new QLabel(icons[index]);
        QFont iconFont(QStringLiteral("Material Symbols Outlined"));
        iconFont.setPixelSize(18);
        iconLabel->setFont(iconFont);
        iconLabel->setAttribute(Qt::WA_TransparentForMouseEvents);
        iconLabel->setStyleSheet(QStringLiteral("color: #3f4940;"));
        itemLayout->addWidget(iconLabel);
        auto *textLabel = new QLabel(names[index]);
        textLabel->setObjectName(QStringLiteral("NavText"));
        QFont navFont(QStringLiteral("Manrope"), 10, QFont::Bold);
        navFont.setPixelSize(14);
        textLabel->setFont(navFont);
        textLabel->setWordWrap(false);
        textLabel->setAttribute(Qt::WA_TransparentForMouseEvents);
        textLabel->setStyleSheet(QStringLiteral("color: #3f4940;"));
        itemLayout->addWidget(textLabel);
        item->setFixedWidth(itemLayout->sizeHint().width());
        item->setProperty("desktopWidth",item->width());
        item->setProperty("index", index);
        connect(item, &QPushButton::clicked, this, [this, index] { navigate(static_cast<Page>(index)); });
        navButtons_[index] = item;
        navRow->addWidget(item);
    }
    navButtons_[Cloud] = nullptr;
    top->addStretch();
    top->addWidget(nav);
    top->addStretch();

    patientSelector_ = new PatientSelector;
    patientSelector_->setObjectName(QStringLiteral("PatientSelector"));
    patientSelector_->setMinimumWidth(280);
    patientSelector_->setFixedHeight(44);
    patientSelector_->setSizePolicy(QSizePolicy::Fixed,QSizePolicy::Fixed);
    patientSelector_->setMaximumWidth(340);
    patientSelector_->setStyleSheet("QComboBox#PatientSelector { background:#f0f5ed; border:1px solid #becabd; border-radius:12px; padding:0 28px 0 12px; min-height:0; font-size:14px; font-weight:700; } QComboBox QAbstractItemView { background:white; color:#181d18; border:1px solid #becabd; selection-background-color:#e5eae2; selection-color:#005227; padding:4px; }");
    patientSelector_->setToolTip(QStringLiteral("Current patient"));
    patientSelector_->setAccessibleName(QStringLiteral("Current patient"));
    connect(patientSelector_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this](int index) {
        if (index < 0 || index >= patients_.size() || busy_) return;
        currentPatient_ = index;
        selectedRegion_.clear();
        activeEye_ = QStringLiteral("OS");
        emit patientChanged(patients_[index].details);
        rebuildAll();
    });
    top->addWidget(patientSelector_);

    auto *cloud = button(QStringLiteral("Cloud Sync"), true);
    cloud->setObjectName(QStringLiteral("CloudSyncButton"));
    cloud->setMinimumHeight(40);
    cloud->setStyleSheet(QStringLiteral(
        "QPushButton#CloudSyncButton { background: #005227; color: white; border: 1px solid #005227; border-radius: 8px; padding: 8px 14px; font-weight: 700; font-size: 11px; }"
        "QPushButton#CloudSyncButton:hover { background: #006d36; }"
    ));
    connect(cloud, &QPushButton::clicked, this, [this] { navigate(Cloud); });
    top->addWidget(cloud);
    root->addWidget(header);

    pages_ = new QStackedWidget;
    for (int index = 0; index < PageCount; ++index) {
        auto *scroll = new QScrollArea;
        scroll->setWidgetResizable(true);
        scroll->setFrameShape(QFrame::NoFrame);
        scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        scrolls_[index] = scroll;
        pages_->addWidget(scroll);
    }
    root->addWidget(pages_, 1);
    pages_->installEventFilter(this);
    analyzeButton_ = button(QStringLiteral("Analyze Retinal Images"), true);
    analyzeButton_->setParent(pages_);
    analyzeButton_->setFixedHeight(56);
    analyzeButton_->setStyleSheet(QStringLiteral(
        "QPushButton { background: #005227; color: white; border: 1px solid #005227; border-radius: 12px; padding: 0 32px; font-size: 18px; font-weight: 700; }"
        "QPushButton:hover { background: #006d36; }"
        "QPushButton:disabled { background: #dfe4dc; color: #6f7a6f; border-color: #dfe4dc; }"));
    connect(analyzeButton_, &QPushButton::clicked, this, &MainWindow::requestAnalysis);
    progressStatus_ = new QLabel;
    progressStatus_->setContentsMargins(24, 8, 24, 8);
    progressStatus_->setStyleSheet(QStringLiteral("background: #f0f5ed; color: #005227; border-top: 1px solid #becabd; font-size: 11px; font-weight: 600;"));
    root->addWidget(progressStatus_);
    headerStatus_ = progressStatus_;
    setCentralWidget(shell);
    refreshHeader();
}

void MainWindow::refreshHeader() {
    const QSignalBlocker block(patientSelector_);
    patientSelector_->clear();
    for (const auto &patient : patients_) {
        patientSelector_->addItem(ui::buttonIcon("person"), QStringLiteral("#%1 - %2").arg(valueString(patient.details, QStringLiteral("patientIdNumber")),
                                                          valueString(patient.details, QStringLiteral("name"))));
    }
    patientSelector_->setEnabled(currentPatient_ >= 0 && !busy_);
    if (currentPatient_ >= 0) patientSelector_->setCurrentIndex(currentPatient_);
    if (headerStatus_->text().isEmpty()) headerStatus_->setText(QStringLiteral("Offline screening · Local native application"));
    for (int index = 0; index < PageCount; ++index) {
        auto *item = navButtons_[index];
        // Cloud is a page with a separate header action, not a center nav button.
        if (!item) continue;
        item->setProperty("active", index == currentPage_);
        item->style()->unpolish(item);
        item->style()->polish(item);
        for (auto *child : item->findChildren<QLabel*>()) {
            child->setStyleSheet(index == currentPage_ ? QStringLiteral("color: white;") : QStringLiteral("color: #3f4940;"));
        }
    }
    updateCaptureAction();
    refreshResponsiveHeader();
}

void MainWindow::navigate(Page page) {
    if (page != Report) historyReport_.clear();
    if (page == History) rebuildPage(History);
    currentPage_ = page;
    pages_->setCurrentIndex(page);
    for (int index = 0; index < PageCount; ++index) {
        auto *item = navButtons_[index];
        if (!item) continue; // Cloud has a separate header action.
        item->setProperty("active", index == page);
        item->style()->unpolish(item);
        item->style()->polish(item);
        for (auto *child : item->findChildren<QLabel*>()) {
            child->setStyleSheet(index == page ? QStringLiteral("color: white;") : QStringLiteral("color: #3f4940;"));
        }
    }
    updateCaptureAction();
}

void MainWindow::updateCaptureAction() {
    if (!analyzeButton_) return;
    analyzeButton_->setText(busy_ ? QStringLiteral("Analyzing retinal images…") : QStringLiteral("Analyze Retinal Images"));
    analyzeButton_->setEnabled(!busy_);
    analyzeButton_->adjustSize();
    analyzeButton_->move(pages_->width() - analyzeButton_->width() - 32,
                         pages_->height() - analyzeButton_->height() - 32);
    analyzeButton_->setVisible(currentPage_ == Capture && currentPatient_ >= 0);
    analyzeButton_->raise();
}

bool MainWindow::eventFilter(QObject *watched, QEvent *event) {
    if (watched == pages_ && event->type() == QEvent::Resize) updateCaptureAction();
    return QMainWindow::eventFilter(watched, event);
}

void MainWindow::refreshResponsiveHeader() {
    if(!patientSelector_) return;
    patientSelector_->setVisible(currentPatient_>=0 && width()>=1024);
    for(auto *button:navButtons_) if(button) {
        if(auto *text=button->findChild<QLabel*>(QStringLiteral("NavText"))) text->setVisible(width()>=1280);
        button->setFixedWidth(width()>=1280?button->property("desktopWidth").toInt():44);
    }
}
void MainWindow::resizeEvent(QResizeEvent *event) {
    QMainWindow::resizeEvent(event);
    refreshResponsiveHeader();
    if(scrolls_[Report] && event->oldSize().width()>0 && (event->oldSize().width()>=768)!=(width()>=768)) rebuildPage(Report);
    const auto batchBreakpoint=[](int w) { return w>=1024?2:w>=768?1:0; };
    if(scrolls_[Batch] && event->oldSize().width()>0 && batchBreakpoint(event->oldSize().width())!=batchBreakpoint(width())) rebuildPage(Batch);
    const int historyBreakpoint = width() >= 1120 ? 1 : 0;
    if (historyLayoutBreakpoint_ >= 0 && historyLayoutBreakpoint_ != historyBreakpoint) rebuildPage(History);
    historyLayoutBreakpoint_ = historyBreakpoint;
}

void MainWindow::rebuildPage(Page page) {
    QWidget *old = scrolls_[page]->takeWidget();
    if (old) old->deleteLater();
    QWidget *pageWidget = nullptr;
    switch (page) {
    case Capture: pageWidget = buildCapture(); break;
    case Analysis: pageWidget = buildAnalysis(); break;
    case Compare: pageWidget = buildCompare(); break;
    case Report: pageWidget = buildReport(); break;
    case History: pageWidget = buildHistory(); break;
    case Batch: pageWidget = buildBatch(); break;
    case Cloud: pageWidget = buildCloud(); break;
    default: break;
    }
    scrolls_[page]->setWidget(pageWidget);
    if (page == Capture) updateCaptureAction();
}

void MainWindow::rebuildAll() {
    refreshHeader();
    for (int index = 0; index < PageCount; ++index) rebuildPage(static_cast<Page>(index));
    saveState();
}

bool MainWindow::saveState() const {
    if (!stateLoadError_.isEmpty()) return false;
    auto eyeMap = [](const EyeState &eye) -> QVariantMap {
        return {{QStringLiteral("imagePath"), eye.imagePath}, {QStringLiteral("capturedAt"), eye.capturedAt.toString(Qt::ISODateWithMs)}, {QStringLiteral("result"), eye.result},
                {QStringLiteral("stage"), eye.stage}, {QStringLiteral("error"), eye.error}};
    };
    auto patientMap = [&](const PatientState &patient) -> QVariantMap {
        return {{QStringLiteral("details"), patient.details},
                {QStringLiteral("os"), eyeMap(patient.os)}, {QStringLiteral("od"), eyeMap(patient.od)}};
    };
    QVariantList patients;
    for (const auto &patient : patients_) patients << patientMap(patient);
    QVariantList history;
    for (const auto &entry : history_) {
        history << QVariantMap{{QStringLiteral("patient"), patientMap(entry.patient)},
                               {QStringLiteral("savedAt"), entry.savedAt.toString(Qt::ISODateWithMs)}};
    }
    const QString folder = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    if (folder.isEmpty() || !QDir().mkpath(folder)) return false;
    QSaveFile file(QDir(folder).filePath(QStringLiteral("session.json")));
    if (!file.open(QIODevice::WriteOnly)) return false;
    const auto bytes=QJsonDocument::fromVariant(QVariantMap{
        {QStringLiteral("patients"), patients}, {QStringLiteral("history"), history},
        {QStringLiteral("currentPatient"), currentPatient_}}).toJson(QJsonDocument::Indented);
    return file.write(bytes)==bytes.size() && file.commit();
}

void MainWindow::loadState() {
    const QString folder = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    QFile file(QDir(folder).filePath(QStringLiteral("session.json")));
    if (!file.open(QIODevice::ReadOnly)) return;
    QJsonParseError parse{};
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &parse);
    if (parse.error != QJsonParseError::NoError || !document.isObject()) {
        stateLoadError_ = QStringLiteral("The local session file could not be read. The saved file was left unchanged.");
        return;
    }
    const QVariantMap saved = document.toVariant().toMap();
    auto eyeStateFromMap = [](const QVariantMap &map) -> EyeState {
        return {map.value(QStringLiteral("imagePath")).toString(),
                QDateTime::fromString(map.value(QStringLiteral("capturedAt")).toString(), Qt::ISODateWithMs),
                map.value(QStringLiteral("result")).toMap(),
                map.value(QStringLiteral("stage")).toString(),
                map.value(QStringLiteral("error")).toString()};
    };
    auto patientFromMap = [&](const QVariantMap &map) -> PatientState {
        return {map.value(QStringLiteral("details")).toMap(),
                eyeStateFromMap(map.value(QStringLiteral("os")).toMap()),
                eyeStateFromMap(map.value(QStringLiteral("od")).toMap())};
    };
    for (const QVariant &item : saved.value(QStringLiteral("patients")).toList())
        patients_.append(patientFromMap(item.toMap()));
    for (const QVariant &item : saved.value(QStringLiteral("history")).toList()) {
        const QVariantMap map = item.toMap();
        history_.append({patientFromMap(map.value(QStringLiteral("patient")).toMap()),
                         QDateTime::fromString(map.value(QStringLiteral("savedAt")).toString(), Qt::ISODateWithMs)});
    }
    const int index = saved.value(QStringLiteral("currentPatient"), -1).toInt();
    currentPatient_ = index >= 0 && index < patients_.size() ? index : (patients_.isEmpty() ? -1 : 0);
}

QString MainWindow::historySessionId(const HistoryEntry &entry) {
    const QString source = QStringLiteral("%1|%2|%3|%4")
        .arg(entry.patient.details.value("patientIdNumber").toString(),
             entry.savedAt.toString(Qt::ISODateWithMs), entry.patient.os.imagePath, entry.patient.od.imagePath);
    const auto digest = QCryptographicHash::hash(source.toUtf8(), QCryptographicHash::Sha256).toHex().left(12);
    return "local-" + QString::fromLatin1(digest);
}

bool MainWindow::rememberReportPath(const QString &sessionId, const QString &eye,
                                   const QVariantMap &result, const QString &pdfPath) {
    if ((eye != "OS" && eye != "OD") || !QFileInfo(pdfPath).isFile()) return false;
    const auto identity = result.value("report_patient").toMap().value("id").toString();
    auto matches = [&](const PatientState &patient, const EyeState &scan, const QDateTime &fallback) {
        const auto context = reporting::withContext(scan.result, patient.details, eye,
            scan.capturedAt.isValid() ? scan.capturedAt : fallback, scan.imagePath);
        return context.value("report_patient").toMap().value("id").toString() == identity &&
               context.value("run_id") == result.value("run_id");
    };
    for (auto &entry : history_) {
        auto &scan = eye == "OS" ? entry.patient.os : entry.patient.od;
        if ((!sessionId.isEmpty() && historySessionId(entry) == sessionId) ||
            (sessionId.isEmpty() && matches(entry.patient, scan, entry.savedAt)))
            scan.result["report_path"] = pdfPath;
    }
    for (auto &patient : patients_) {
        auto &scan = eye == "OS" ? patient.os : patient.od;
        if (matches(patient, scan, {})) scan.result["report_path"] = pdfPath;
    }
    if (!historyReport_.isEmpty() && (sessionId.isEmpty() || historyReport_.value("sessionId") == sessionId)) {
        const auto key = eye == "OS" ? QString("os") : QString("od");
        auto stored = historyReport_.value(key).toMap();
        if (stored.value("run_id") == result.value("run_id")) {
            stored["report_path"] = pdfPath; historyReport_[key] = stored;
        }
    }
    return saveState();
}

void MainWindow::recordHistory() {
    if (currentPatient_ < 0 || currentPatient_ >= patients_.size()) return;
    const PatientState &patient = patients_[currentPatient_];
    const QString id = patient.details.value(QStringLiteral("patientIdNumber")).toString();
    for (int index = history_.size() - 1; index >= 0; --index) {
        auto &entry = history_[index];
        if (entry.patient.details.value(QStringLiteral("patientIdNumber")).toString() == id &&
            entry.patient.os.imagePath == patient.os.imagePath &&
            entry.patient.od.imagePath == patient.od.imagePath) {
            entry.patient = patient;
            entry.savedAt = QDateTime::currentDateTime();
            return;
        }
    }
    history_.append({patient, QDateTime::currentDateTime()});
}

QWidget *MainWindow::buildPageFrame(const QString &title, const QString &subtitle, QVBoxLayout **content) {
    auto *outer = new QWidget;
    outer->setObjectName(QStringLiteral("PageFrameRoot"));
    auto *out = new QVBoxLayout(outer);
    out->setContentsMargins(0, 24, 0, 96);
    out->setSpacing(0);
    auto *page = new QWidget;
    page->setObjectName(QStringLiteral("PageFrame"));
    page->setMaximumWidth(1280);
    auto *body = column(page, 0, 24);
    body->setContentsMargins(24, 0, 24, 0);
    auto *center = new QHBoxLayout;
    center->setContentsMargins(0, 0, 0, 0);
    center->addStretch();
    center->addWidget(page, 1);
    center->addStretch();
    out->addLayout(center);
    out->addStretch();
    if (!title.isEmpty()) {
        auto *heading = label(title, 28, true);
        QFont headingFont(QStringLiteral("Manrope"), 22, QFont::ExtraBold);
        headingFont.setPixelSize(30);
        heading->setFont(headingFont);
        heading->setStyleSheet(QStringLiteral("letter-spacing: -0.02em;"));
        body->addWidget(heading);
    }
    if (!subtitle.isEmpty()) body->addWidget(label(subtitle, 11, false, kMuted));
    *content = body;
    return outer;
}

QWidget *MainWindow::buildEmptyState(const QString &icon, const QString &title, const QString &message) {
    auto *box = card();
    auto *inside = column(box, 48, 16);
    inside->addWidget(label(icon, 40, true, kPrimary), 0, Qt::AlignHCenter);
    auto *heading = label(title, 22, true);
    QFont emptyHeadingFont(QStringLiteral("Manrope"), 18, QFont::ExtraBold);
    emptyHeadingFont.setPixelSize(24);
    heading->setFont(emptyHeadingFont);
    heading->setStyleSheet(QStringLiteral("letter-spacing: -0.02em;"));
    heading->setAlignment(Qt::AlignCenter);
    heading->setMaximumWidth(640);
    inside->addWidget(heading, 0, Qt::AlignHCenter);
    auto *description = label(message, 11, false, kMuted);
    description->setAlignment(Qt::AlignCenter);
    description->setMinimumSize(600, 48);
    description->setMaximumWidth(640);
    inside->addWidget(description, 0, Qt::AlignHCenter);
    return box;
}

MainWindow::EyeState *MainWindow::eyeState(const QString &eye, int patientIndex) {
    if (patientIndex < 0) patientIndex = currentPatient_;
    if (patientIndex < 0 || patientIndex >= patients_.size()) return nullptr;
    return eye == QLatin1String("OD") ? &patients_[patientIndex].od : &patients_[patientIndex].os;
}

const MainWindow::EyeState *MainWindow::eyeState(const QString &eye, int patientIndex) const {
    if (patientIndex < 0) patientIndex = currentPatient_;
    if (patientIndex < 0 || patientIndex >= patients_.size()) return nullptr;
    return eye == QLatin1String("OD") ? &patients_[patientIndex].od : &patients_[patientIndex].os;
}

QVariantMap MainWindow::resultFor(const QString &eye) const {
    const auto *state = eyeState(eye);
    return state ? state->result : QVariantMap{};
}

QString MainWindow::resultState(const QString &eye) const {
    const auto *state = eyeState(eye);
    if (!state) return {};
    if (!state->error.isEmpty()) return QStringLiteral("FAILED");
    if (!state->result.isEmpty()) return state->result.value(QStringLiteral("state")).toString();
    return state->imagePath.isEmpty() ? QStringLiteral("Pending capture") : QStringLiteral("Ready for analysis");
}

QString MainWindow::eyeName(const QString &eye) const {
    return eye == QLatin1String("OD") ? QStringLiteral("Right Eye (OD)") : QStringLiteral("Left Eye (OS)");
}

QString MainWindow::imagePath(const QString &eye) const {
    const auto *state = eyeState(eye);
    if (!state) return {};
    return textOr(state->result, QStringLiteral("analysis_image_path"),
                  textOr(state->result, QStringLiteral("image_path"), state->imagePath));
}

QString MainWindow::gradeText(const QVariantMap &result) const {
    const QVariant grade = result.value(QStringLiteral("grade"));
    return grade.isValid() && !grade.isNull() && grade.toInt() >= 0
        ? QStringLiteral("DR grade %1").arg(grade.toString())
        : QStringLiteral("DR grade unavailable");
}

void MainWindow::setPatient(QVariantMap patient) {
    const QString id = textOr(patient, QStringLiteral("patientIdNumber"), patient.value(QStringLiteral("id")).toString());
    int index = -1;
    for (int i = 0; i < patients_.size(); ++i) {
        if (textOr(patients_[i].details, QStringLiteral("patientIdNumber"), patients_[i].details.value(QStringLiteral("id")).toString()) == id) {
            index = i;
            break;
        }
    }
    if (index < 0) {
        patients_.append(PatientState{patient});
        index = patients_.size() - 1;
    } else {
        patients_[index].details = patient;
    }
    currentPatient_ = index;
    rebuildAll();
}

void MainWindow::setStatus(QString message) {
    headerStatus_->setText(message);
}

void MainWindow::setBatchStatus(QString message) {
    batchStatus_ = message;
    setStatus(message);
    rebuildPage(Batch);
}

void MainWindow::setBusy(bool busy) {
    busy_ = busy;
    refreshHeader();
    if (!busy_) {
        activeAnalysisEye_.clear();
        activePatient_ = -1;
        dispatchNextEye();
    }
    rebuildPage(Capture);
    rebuildPage(Report);
    rebuildPage(Batch);
}

void MainWindow::setProgress(QString eye, QString stage) {
    if (auto *state = eyeState(eye, activePatient_)) state->stage = stage;
    busy_ = true;
    activeAnalysisEye_ = eye;
    progressStatus_->setText(QStringLiteral("%1 · %2").arg(eyeName(eye), stage));
    rebuildPage(Capture);
    rebuildPage(Report);
    rebuildPage(Batch);
}

void MainWindow::setEyeResult(QString eye, QVariantMap result) {
    selectedRegion_.clear();
    hasCoordinateCursor_ = false;
    if (auto *state = eyeState(eye, activePatient_)) {
        const auto details = patients_[activePatient_ >= 0 ? activePatient_ : currentPatient_].details;
        if (result.value("scan_datetime").toString().isEmpty()) {
            const QString storedTime = details.value("scan_datetime").toString();
            result["scan_datetime"] = state->capturedAt.isValid() ? state->capturedAt.toString(Qt::ISODate)
                : !storedTime.isEmpty() ? storedTime : QDateTime::currentDateTime().toString(Qt::ISODate);
        }
        result = reporting::withContext(result, details, eye);
        state->result = result;
        state->error = result.value(QStringLiteral("error")).toString();
        state->stage = result.value(QStringLiteral("state")).toString() == QLatin1String("RECAPTURE_REQUIRED")
                           ? QStringLiteral("Recapture required") : QStringLiteral("Analysis complete");
    }
    progressStatus_->setText(QStringLiteral("%1 · %2").arg(eyeName(eye), resultState(eye)));
    recordHistory();
    rebuildAll();
}

void MainWindow::setEyeError(QString eye, QString message) {
    if (auto *state = eyeState(eye, activePatient_)) {
        state->error = message;
        state->stage = QStringLiteral("Analysis failed");
    }
    progressStatus_->setText(QStringLiteral("%1 · Analysis failed: %2").arg(eyeName(eye), message));
    rebuildAll();
}

void MainWindow::registerPatient() {
    QDialog dialog(this);
    dialog.setWindowTitle(QStringLiteral("New Patient Registration"));
    dialog.setMinimumWidth(580);
    auto *layout = column(&dialog, 22, 12);
    layout->addWidget(label(QStringLiteral("New Patient Registration"), 19, true, kPrimary));
    layout->addWidget(label(QStringLiteral("Patient demographics, clinical history and initial screening study"), 10, false, kMuted));
    auto *form = new QFormLayout;
    auto *name = new QLineEdit;
    auto *mrn = new QLineEdit(QStringLiteral("RH-%1").arg(QRandomGenerator::global()->bounded(1000, 10000)));
    auto *age = new QSpinBox;
    age->setRange(1, 120);
    age->setValue(54);
    auto *gender = new QComboBox;
    gender->addItems({QStringLiteral("Female"), QStringLiteral("Male"), QStringLiteral("Other")});
    auto *phone = new QLineEdit;
    auto *email = new QLineEdit;
    auto *years = new QSpinBox;
    years->setRange(0, 70);
    auto *hba1c = new QLineEdit;
    auto *pressure = new QLineEdit;
    form->addRow(QStringLiteral("Full name *"), name);
    form->addRow(QStringLiteral("Medical Record Number"), mrn);
    form->addRow(QStringLiteral("Age"), age);
    form->addRow(QStringLiteral("Gender"), gender);
    form->addRow(QStringLiteral("Phone"), phone);
    form->addRow(QStringLiteral("Email"), email);
    form->addRow(QStringLiteral("Diabetes duration (years)"), years);
    form->addRow(QStringLiteral("HbA1c baseline"), hba1c);
    form->addRow(QStringLiteral("Blood pressure"), pressure);
    layout->addLayout(form);
    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel | QDialogButtonBox::Save);
    buttons->button(QDialogButtonBox::Save)->setText(QStringLiteral("Register & Begin Screening"));
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    connect(buttons, &QDialogButtonBox::accepted, &dialog, [&] {
        if (name->text().trimmed().isEmpty()) {
            QMessageBox::warning(&dialog, QStringLiteral("Full name required"), QStringLiteral("Enter the patient's full name."));
            return;
        }
        dialog.accept();
    });
    layout->addWidget(buttons);
    if (dialog.exec() != QDialog::Accepted) return;
    QVariantMap details{{QStringLiteral("id"), mrn->text().trimmed()}, {QStringLiteral("patientIdNumber"), mrn->text().trimmed()},
                        {QStringLiteral("name"), name->text().trimmed()}, {QStringLiteral("age"), age->value()},
                        {QStringLiteral("gender"), gender->currentText()}, {QStringLiteral("phone"), phone->text().trimmed()},
                        {QStringLiteral("email"), email->text().trimmed()}, {QStringLiteral("diabeticHistoryYears"), years->value()},
                        {QStringLiteral("hba1c"), hba1c->text().trimmed()}, {QStringLiteral("bloodPressure"), pressure->text().trimmed()}};
    setPatient(details);
    emit patientChanged(details);
    navigate(Capture);
}

void MainWindow::startNewSession() {
    if (currentPatient_ < 0 || busy_) return;
    auto &patient = patients_[currentPatient_];
    const bool hasData = !patient.os.imagePath.isEmpty() || !patient.od.imagePath.isEmpty() ||
                         !patient.os.result.isEmpty() || !patient.od.result.isEmpty();
    if (hasData) {
        if (QMessageBox::question(this, QStringLiteral("Start a new session?"),
                                  QStringLiteral("The current scan session will be kept in History before a new session is created."),
                                  QMessageBox::Cancel | QMessageBox::Ok, QMessageBox::Cancel) != QMessageBox::Ok) return;
        recordHistory();
    }
    patient.os = {};
    patient.od = {};
    activeEye_ = QStringLiteral("OS");
    setStatus(QStringLiteral("New scan session started for #%1 (%2).").arg(
        valueString(patient.details, QStringLiteral("patientIdNumber")), valueString(patient.details, QStringLiteral("name"))));
    rebuildAll();
    navigate(Capture);
}

void MainWindow::chooseImage(QString eye) {
    if (currentPatient_ < 0 || busy_) return;
    const QString path = QFileDialog::getOpenFileName(this, QStringLiteral("Capture / Import Retinal Scan (%1)").arg(eyeName(eye)),
                                                       {}, QStringLiteral("Retinal images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;All files (*)"));
    if (path.isEmpty()) return;
    const QFileInfo file(path);
    if (file.size() > 20 * 1024 * 1024) {
        QMessageBox::warning(this, QStringLiteral("Image too large"), QStringLiteral("Choose an image no larger than 20 MiB."));
        return;
    }
    QString reason;
    const QImage selected = loadImage(path, &reason);
    if (selected.isNull() || static_cast<qint64>(selected.width()) * selected.height() > 16'000'000) {
        QMessageBox::warning(this, QStringLiteral("Image unavailable"),
            selected.isNull() ? QStringLiteral("This image could not be decoded: %1").arg(reason)
                              : QStringLiteral("Choose an image no larger than 16 megapixels."));
        return;
    }
    const QString localRoot = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    const QString imports = QDir(localRoot).filePath(QStringLiteral("imports"));
    if (localRoot.isEmpty() || !QDir().mkpath(imports)) {
        QMessageBox::warning(this, QStringLiteral("Import failed"), QStringLiteral("The local scan folder could not be created."));
        return;
    }
    const QString stored = QDir(imports).filePath(QUuid::createUuid().toString(QUuid::WithoutBraces)
        + QStringLiteral(".") + file.suffix().toLower());
    if (!QFile::copy(path, stored)) {
        QMessageBox::warning(this, QStringLiteral("Import failed"), QStringLiteral("The retinal image could not be copied into local storage."));
        return;
    }
    auto *state = eyeState(eye);
    *state = {};
    state->imagePath = stored;
    state->capturedAt = QDateTime::currentDateTime();
    activeEye_ = eye;
    setStatus(QStringLiteral("%1 image ready for analysis.").arg(eyeName(eye)));
    rebuildAll();
    navigate(Capture);
}

void MainWindow::requestAnalysis() {
    if (currentPatient_ < 0 || busy_) return;
    analysisQueue_.clear();
    for (const QString &eye : {QStringLiteral("OS"), QStringLiteral("OD")}) {
        const auto *state = eyeState(eye);
        if (state && !state->imagePath.isEmpty() && state->result.value(QStringLiteral("state")).toString() != QLatin1String("COMPLETE"))
            analysisQueue_.enqueue(eye);
    }
    if (analysisQueue_.isEmpty()) {
        QMessageBox::information(this, QStringLiteral("No scans to analyze"),
                                 QStringLiteral("Select at least one retinal image, or replace an already analyzed image."));
        return;
    }
    dispatchNextEye();
}

void MainWindow::dispatchNextEye() {
    if (busy_ || analysisQueue_.isEmpty() || currentPatient_ < 0) return;
    const QString eye = analysisQueue_.dequeue();
    auto *state = eyeState(eye);
    if (!state || state->imagePath.isEmpty()) return;
    activeAnalysisEye_ = eye;
    activePatient_ = currentPatient_;
    state->error.clear();
    state->stage = QStringLiteral("Queued for analysis");
    busy_ = true;
    progressStatus_->setText(QStringLiteral("%1 · Queued for analysis").arg(eyeName(eye)));
    rebuildPage(Capture);
    emit analyzeRequested(eye, state->imagePath);
}

void MainWindow::requestReport(QString eye) {
    if (resultFor(eye).value(QStringLiteral("state")).toString() != QLatin1String("COMPLETE")) return;
    const QString destination = QFileDialog::getExistingDirectory(this, QStringLiteral("Choose RetinaGram report destination"));
    if (!destination.isEmpty()) emit reportRequested(eye, destination);
}

QWidget *MainWindow::buildEyeCard(QString eye) {
    const auto *state = eyeState(eye);
    auto *panel = card();
    panel->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    panel->setMinimumWidth(360);
    auto *layout = column(panel, 0, 0);
    auto *head = new QFrame;
    head->setObjectName(QStringLiteral("SoftCard"));
    auto *headRow = new QHBoxLayout(head);
    headRow->setContentsMargins(24, 24, 24, 24);
    auto *headText = new QWidget;
    auto *headColumn = column(headText, 0, 4);
    auto *eyeTitle = label(eyeName(eye), 18, true);
    auto eyeFont = eyeTitle->font();
    eyeFont.setPixelSize(24);
    eyeTitle->setFont(eyeFont);
    eyeTitle->setWordWrap(false);
    headColumn->addWidget(eyeTitle);
    headColumn->addWidget(label(eye == QLatin1String("OS") ? QStringLiteral("Oculus Sinister") : QStringLiteral("Oculus Dexter"), 11, false, kMuted));
    headRow->addWidget(headText, 1);
    const QString status = resultState(eye);
    const bool warning = status == QLatin1String("RECAPTURE_REQUIRED") || status == QLatin1String("FAILED");
    const QString statusText = status == QLatin1String("COMPLETE") ? QStringLiteral("Complete")
        : status == QLatin1String("RECAPTURE_REQUIRED") ? QStringLiteral("Recapture required")
        : status == QLatin1String("FAILED") ? QStringLiteral("Failed") : status;
    auto *pill = label(statusText, 9, true, warning ? kError : kPrimary);
    pill->setWordWrap(false);
    pill->setStyleSheet(QStringLiteral("color: %1; background: %2; border: 1px solid %1; border-radius: 12px; padding: 4px 12px; font-weight: 700;")
                            .arg(warning ? kError : kPrimary, warning ? QStringLiteral("#ffdad6") : QStringLiteral("#e7f7e9")));
    pill->setFixedSize(pill->sizeHint());
    headRow->addWidget(pill, 0, Qt::AlignVCenter);
    layout->addWidget(head);
    auto *body = new QWidget;
    body->setMinimumHeight(380);
    body->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    auto *bodyColumn = column(body, 40, 12);
    bodyColumn->setAlignment(Qt::AlignCenter);
    if (state && !state->imagePath.isEmpty()) {
        auto *picture = new QLabel;
        picture->setObjectName(QStringLiteral("CapturePreview"));
        picture->setFixedSize(320, 320);
        picture->setAlignment(Qt::AlignCenter);
        picture->setStyleSheet(QStringLiteral("background: #000000; border: 2px solid #6f7a6f; border-radius: 10px;"));
        const QImage image = loadImage(state->imagePath);
        if (!image.isNull()) {
            QPixmap pixmap = QPixmap::fromImage(image);
            picture->setPixmap(pixmap.scaled(316, 316, Qt::KeepAspectRatio, Qt::SmoothTransformation));
        }
        bodyColumn->addWidget(picture, 0, Qt::AlignHCenter);
        auto *actions = new QHBoxLayout;
        actions->setSpacing(8);
        actions->addStretch();
        auto *replace = button(QStringLiteral("Retake / Replace Image"));
        replace->setFixedHeight(32);
        replace->setStyleSheet(QStringLiteral(
            "QPushButton#SecondaryButton { background: white; color: #005227; border: 1px solid #6f7a6f; border-radius: 8px; padding: 4px 10px; font-weight: 700; font-size: 12px; }"
            "QPushButton#SecondaryButton:hover { background: #f0f5ed; }"
        ));
        connect(replace, &QPushButton::clicked, this, [this, eye] { chooseImage(eye); });
        actions->addWidget(replace);
        auto *inspect = button(QStringLiteral("View in Analysis"));
        inspect->setFixedHeight(32);
        inspect->setStyleSheet(QStringLiteral(
            "QPushButton#SecondaryButton { background: white; color: #005227; border: 1px solid #6f7a6f; border-radius: 8px; padding: 4px 10px; font-weight: 700; font-size: 12px; }"
            "QPushButton#SecondaryButton:hover { background: #f0f5ed; }"
        ));
        connect(inspect, &QPushButton::clicked, this, [this, eye] {
            activeEye_ = eye;
            rebuildPage(Analysis);
            navigate(Analysis);
        });
        actions->addWidget(inspect);
        actions->addStretch();
        bodyColumn->addLayout(actions);
        const QVariant quality = state->result.value(QStringLiteral("quality_confidence"));
        bodyColumn->addWidget(label(QStringLiteral("IQA class confidence: %1   ·   %2")
                                      .arg(quality.isValid() ? percent(quality) : QStringLiteral("Not assessed"),
                                           textOr(state->result, QStringLiteral("quality"), QStringLiteral("Not assessed"))),
                                  10, false, kMuted));
        if (!state->error.isEmpty()) bodyColumn->addWidget(label(state->error, 11, true, kError));
    } else {
        auto *capture = button(QStringLiteral("＋  Tap to Capture Image"));
        capture->setAccessibleName(capture->text());
        capture->setText({});
        capture->setFixedHeight(320);
        capture->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        capture->setStyleSheet(QStringLiteral(
            "QPushButton { background: #ffffff; border: 2px dashed #6f7a6f; border-radius: 12px; color: #3f4940; font-size: 19px; font-weight: 700; } "
            "QPushButton:hover { border-color: #005227; color: #005227; background: #f0f5ed; }"
        ));
        connect(capture, &QPushButton::clicked, this, [this, eye] { chooseImage(eye); });
        auto *captureContents = column(capture, 16, 16);
        captureContents->addStretch();
        auto *camera = new QLabel(QStringLiteral("photo_camera"));
        QFont cameraFont(QStringLiteral("Material Symbols Outlined"));
        cameraFont.setPixelSize(64);
        camera->setFont(cameraFont);
        camera->setAttribute(Qt::WA_TransparentForMouseEvents);
        captureContents->addWidget(camera, 0, Qt::AlignHCenter);
        auto *captureTitle = label(QStringLiteral("Tap to Capture Image"), 14, true);
        captureTitle->setWordWrap(false);
        captureTitle->setAttribute(Qt::WA_TransparentForMouseEvents);
        captureContents->addWidget(captureTitle, 0, Qt::AlignHCenter);
        auto *captureHint = label(eye == QLatin1String("OS")
            ? QStringLiteral("Supports 45°–50° fundus camera or digital file import")
            : QStringLiteral("Right Eye (OD) fundus image"), 9, false, kMuted);
        captureHint->setWordWrap(false);
        captureHint->setAttribute(Qt::WA_TransparentForMouseEvents);
        captureContents->addWidget(captureHint, 0, Qt::AlignHCenter);
        captureContents->addStretch();
        bodyColumn->addWidget(capture);
    }
    layout->addWidget(body, 1);
    return panel;
}

QWidget *MainWindow::buildCapture() {
    QVBoxLayout *content = nullptr;
    auto *outer = buildPageFrame(QString(), QString(), &content);
    content->setSpacing(16);
    if (currentPatient_ < 0) {
        content->addStretch();
        content->addWidget(buildEmptyState(QStringLiteral("◎"), QStringLiteral("Begin a retinal screening session"),
                                           QStringLiteral("Register the patient, upload the available left and/or right fundus images, then run the eye-scoped analysis.")));
        auto *registerButton = button(QStringLiteral("Register patient"), true);
        registerButton->setMinimumHeight(48);
        registerButton->setStyleSheet(QStringLiteral(
            "QPushButton#PrimaryButton { background: #005227; color: white; border: 1px solid #005227; border-radius: 12px; padding: 12px 28px; font-weight: 700; font-size: 14px; }"
            "QPushButton#PrimaryButton:hover { background: #006d36; }"
        ));
        connect(registerButton, &QPushButton::clicked, this, &MainWindow::registerPatient);
        content->addWidget(registerButton, 0, Qt::AlignHCenter);
        content->addStretch();
        return outer;
    }
    const auto &patient = patients_[currentPatient_];
    auto *header = new QFrame;
    header->setObjectName(QStringLiteral("HistoryHeader"));
    header->setFrameShape(QFrame::NoFrame);
    auto *headRow = new QHBoxLayout(header);
    headRow->setContentsMargins(0, 0, 0, 8);
    headRow->setSpacing(16);
    auto *titles = new QWidget;
    auto *titlesColumn = column(titles, 0, 6);
    auto *titleRow = new QHBoxLayout;
    titleRow->setContentsMargins(0, 0, 0, 0);
    titleRow->setSpacing(10);
    auto *mainTitle = label(QStringLiteral("Patient Intake & Image Capture"), 22, true);
    QFont titleFont(QStringLiteral("Manrope"), 22, QFont::ExtraBold);
    titleFont.setPixelSize(30);
    mainTitle->setFont(titleFont);
    mainTitle->setWordWrap(false);
    mainTitle->setStyleSheet(QStringLiteral("letter-spacing: -0.02em;"));
    titleRow->addWidget(mainTitle, 0, Qt::AlignVCenter);
    auto *badge = new QLabel(QStringLiteral("Active Session"));
    badge->setFont(QFont(QStringLiteral("Manrope"), 9, QFont::Bold));
    badge->setStyleSheet(QStringLiteral("color: #005227; background: #e7f7e9; border: 1px solid #005227; border-radius: 4px; padding: 2px 10px;"));
    badge->setFixedSize(badge->sizeHint());
    titleRow->addWidget(badge, 0, Qt::AlignVCenter);
    titleRow->addStretch();
    titlesColumn->addLayout(titleRow);
    titlesColumn->addWidget(label(QStringLiteral("Patient: %1 · Age: %2 · MRN: #%3 · HbA1c: %4")
                                      .arg(valueString(patient.details, QStringLiteral("name")),
                                           valueString(patient.details, QStringLiteral("age")),
                                           valueString(patient.details, QStringLiteral("patientIdNumber")),
                                           valueString(patient.details, QStringLiteral("hba1c"))), 12, false, kMuted));
    headRow->addWidget(titles, 1);
    auto *actions = new QWidget;
    auto *actionsLayout = new QHBoxLayout(actions);
    actionsLayout->setContentsMargins(0, 0, 0, 0);
    actionsLayout->setSpacing(10);
    // Study Date
    const QDate studyDate = QDate::currentDate();
    QString studyDateStr = studyDate.toString(QStringLiteral("MMM d, yyyy"));
    auto *studyDateWidget = new QLabel(QStringLiteral("Study Date: %1").arg(studyDateStr));
    studyDateWidget->setFont(QFont(QStringLiteral("Manrope"), 10, QFont::Bold));
    studyDateWidget->setStyleSheet(QStringLiteral("color: #3f4940; background: #f0f5ed; border: 1px solid #becabd; border-radius: 8px; padding: 8px 12px;"));
    studyDateWidget->setFixedHeight(36);
    actionsLayout->addWidget(studyDateWidget);
    auto *session = button(QStringLiteral("New Session"));
    session->setEnabled(!busy_);
    session->setMinimumHeight(40);
    session->setStyleSheet(QStringLiteral(
        "QPushButton#SecondaryButton { background: white; color: #005227; border: 1px solid #6f7a6f; border-radius: 10px; padding: 8px 16px; font-weight: 700; font-size: 12px; }"
        "QPushButton#SecondaryButton:hover { background: #f0f5ed; }"
    ));
    connect(session, &QPushButton::clicked, this, &MainWindow::startNewSession);
    actionsLayout->addWidget(session);
    auto *newPatient = button(QStringLiteral("New Patient"), true);
    newPatient->setMinimumHeight(40);
    newPatient->setStyleSheet(QStringLiteral(
        "QPushButton#PrimaryButton { background: #005227; color: white; border: 1px solid #005227; border-radius: 10px; padding: 8px 16px; font-weight: 700; font-size: 12px; }"
        "QPushButton#PrimaryButton:hover { background: #006d36; }"
    ));
    connect(newPatient, &QPushButton::clicked, this, &MainWindow::registerPatient);
    actionsLayout->addWidget(newPatient);
    headRow->addWidget(actions);
    content->addWidget(header);
    auto *divider = new QFrame;
    divider->setFixedHeight(2);
    divider->setStyleSheet(QStringLiteral("background: #becabd;"));
    content->addWidget(divider);

    if (busy_) {
        auto *progress = card();
        auto *inside = column(progress, 20, 10);
        const bool loadingModels = activeAnalysisEye_.isEmpty();
        inside->addWidget(label(loadingModels ? QStringLiteral("Loading inference models")
                                              : QStringLiteral("Analyzing patient retinal images"), 18, true));
        inside->addWidget(label(loadingModels ? QStringLiteral("Preparing native CUDA and model sessions")
            : QStringLiteral("%1 · %2").arg(eyeName(activeAnalysisEye_),
                eyeState(activeAnalysisEye_, activePatient_) ? eyeState(activeAnalysisEye_, activePatient_)->stage : QString()),
            11, true, kPrimary));
        auto *steps = label(QStringLiteral("Image loaded  →  Image quality  →  Restoration if needed  →  DR grading  →  Lesion inference  →  Region extraction  →  Results"),
                            11, false, kMuted);
        inside->addWidget(steps);
        content->addWidget(progress);
    }
    auto *eyeSelect = new QHBoxLayout;
    eyeSelect->setContentsMargins(0, 0, 0, 0);
    eyeSelect->addWidget(label(QStringLiteral("View eye:"), 11, true));
    auto *eyeCombo = new QComboBox;
    eyeCombo->setObjectName(QStringLiteral("EyeSelector"));
    eyeCombo->setAccessibleName(QStringLiteral("View eye"));
    eyeCombo->setFixedSize(160, 32);
    eyeCombo->addItem(QStringLiteral("Left (OS)"), QStringLiteral("OS"));
    eyeCombo->addItem(QStringLiteral("Right (OD)"), QStringLiteral("OD"));
    eyeCombo->setCurrentIndex(activeEye_ == QLatin1String("OD") ? 1 : 0);
    connect(eyeCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this](int index) { activeEye_ = index == 1 ? QStringLiteral("OD") : QStringLiteral("OS"); });
    eyeSelect->addWidget(eyeCombo);
    eyeSelect->addStretch();
    content->addLayout(eyeSelect);

    auto *eyes = new QHBoxLayout;
    eyes->setSpacing(32);
    eyes->addWidget(buildEyeCard(QStringLiteral("OS")), 1);
    eyes->addWidget(buildEyeCard(QStringLiteral("OD")), 1);
    content->addLayout(eyes);

    if (patient.os.result.value(QStringLiteral("state")).toString() == QLatin1String("COMPLETE") ||
        patient.od.result.value(QStringLiteral("state")).toString() == QLatin1String("COMPLETE")) {
        auto *finished = card();
        auto *row = new QHBoxLayout(finished);
        row->setContentsMargins(20, 16, 20, 16);
        row->addWidget(label(QStringLiteral("Retinal Analysis Complete"), 17, true, kPrimary), 1);
        auto *open = button(QStringLiteral("View Report"), true);
        open->setMinimumHeight(44);
        open->setStyleSheet(QStringLiteral(
            "QPushButton#PrimaryButton { background: #005227; color: white; border: 1px solid #005227; border-radius: 10px; padding: 10px 20px; font-weight: 700; font-size: 12px; }"
            "QPushButton#PrimaryButton:hover { background: #006d36; }"
        ));
        connect(open, &QPushButton::clicked, this, [this] { navigate(Report); });
        row->addWidget(open);
        content->addWidget(finished);
    }
    content->addSpacing(16); // 16 px layout spacing + 16 px = pc-gpu's 32 px margin.
    auto *protocol = card();
    protocol->setObjectName(QStringLiteral("SoftCard"));
    auto *protocolColumn = column(protocol, 24, 12);
    auto *protocolTitle = new QHBoxLayout;
    protocolTitle->setContentsMargins(0, 0, 0, 0);
    protocolTitle->setSpacing(10);
    auto *checkIcon = new QLabel(QStringLiteral("fact_check"));
    checkIcon->setFont(QFont(QStringLiteral("Material Symbols Outlined"), 24));
    checkIcon->setStyleSheet(QStringLiteral("color: #005227;"));
    protocolTitle->addWidget(checkIcon);
    auto *protocolLabel = label(QStringLiteral("Standard Retinal Imaging Protocol"), 17, true);
    QFont protocolFont(QStringLiteral("Manrope"), 14, QFont::Bold);
    protocolFont.setPixelSize(18);
    protocolLabel->setFont(protocolFont);
    protocolLabel->setWordWrap(false);
    protocolTitle->addWidget(protocolLabel);
    protocolTitle->addStretch();
    protocolColumn->addLayout(protocolTitle);
    auto *protocolSteps = new QHBoxLayout;
    protocolSteps->setSpacing(16);
    for (const auto &step : {QStringLiteral("✓  Ensure 45° field centered on the fovea / macula"),
                            QStringLiteral("✓  Minimal pupil diameter ≥ 3.5mm without excessive glare"),
                            QStringLiteral("✓  Automatic focus lock verified (Focus Metric > 0.90)")}) {
        auto *stepLabel = label(step, 10, false, kMuted);
        stepLabel->setMinimumHeight(40);
        stepLabel->setAlignment(Qt::AlignTop);
        protocolSteps->addWidget(stepLabel, 1);
    }
    protocolColumn->addLayout(protocolSteps);
    content->addWidget(protocol);
    return outer;
}

QWidget *MainWindow::buildCompare() {
    QVBoxLayout *content = nullptr;
    const QString patientLabel = currentPatient_ >= 0
                                     ? QStringLiteral("Patient #%1 · %2 · Two independent scans")
                                           .arg(valueString(patients_[currentPatient_].details, QStringLiteral("patientIdNumber")),
                                                valueString(patients_[currentPatient_].details, QStringLiteral("name")))
                                     : QString();
    auto *outer = buildPageFrame(QStringLiteral("Left Eye vs Right Eye"), patientLabel, &content);
    if (currentPatient_ < 0) {
        content->addWidget(buildEmptyState(QStringLiteral("◎"), QStringLiteral("No patient selected"),
                                           QStringLiteral("Register a patient and capture eye images first.")));
        return outer;
    }
    auto *controls = new QHBoxLayout;
    controls->addWidget(label(QStringLiteral("Comparison View"), 10, true));
    auto *view = new QComboBox;
    view->addItems({QStringLiteral("Grade Grad-CAM"), QStringLiteral("Lesion Heatmap"),
                    QStringLiteral("Lesion Detection"), QStringLiteral("Lesion Annotation")});
    view->setCurrentIndex(compareView_);
    connect(view, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this](int index) {
        compareView_ = static_cast<View>(index);
        rebuildPage(Compare);
    });
    controls->addWidget(view);
    controls->addWidget(label(QStringLiteral("Synchronized for OS and OD"), 9, false, kMuted));
    controls->addStretch();
    content->addLayout(controls);

    auto *panels = new QHBoxLayout;
    panels->setSpacing(18);
    for (const QString &eye : {QStringLiteral("OS"), QStringLiteral("OD")}) {
        auto *eyePanel = new QWidget;
        auto *eyeColumn = column(eyePanel, 0, 12);
        auto *head = new QHBoxLayout;
        head->addWidget(label(eye == QLatin1String("OS") ? QStringLiteral("OS · Left Eye") : QStringLiteral("OD · Right Eye"), 17, true), 1);
        auto *inspect = button(QStringLiteral("Inspect %1").arg(eye));
        connect(inspect, &QPushButton::clicked, this, [this, eye] {
            activeEye_ = eye;
            rebuildPage(Analysis);
            navigate(Analysis);
        });
        head->addWidget(inspect);
        eyeColumn->addLayout(head);
        eyeColumn->addWidget(buildVisualization(eye, compareView_, true));
        const QVariantMap result = resultFor(eye);
        auto *metrics = card();
        auto *grid = new QGridLayout(metrics);
        grid->setContentsMargins(17, 17, 17, 17);
        addLabeledValue(grid, 0, 0, QStringLiteral("Predicted DR grade"), valueString(result, QStringLiteral("grade"), QStringLiteral("Unavailable")));
        addLabeledValue(grid, 0, 1, QStringLiteral("Grade class confidence"), percent(result.value(QStringLiteral("grade_confidence"))));
        addLabeledValue(grid, 1, 0, QStringLiteral("IQA"), textOr(result, QStringLiteral("quality"), QStringLiteral("Not assessed")));
        addLabeledValue(grid, 1, 1, QStringLiteral("IQA class confidence"), percent(result.value(QStringLiteral("quality_confidence"))));
        auto *counts = label(QStringLiteral("Lesions: %1").arg(result.value(QStringLiteral("lesion_counts")).toMap().isEmpty()
                                                            ? QStringLiteral("Not assessed")
                                                            : QStringLiteral("%1 classes reported").arg(result.value(QStringLiteral("lesion_counts")).toMap().size())),
                             9, false, kMuted);
        grid->addWidget(counts, 2, 0, 1, 2);
        eyeColumn->addWidget(metrics);
        panels->addWidget(eyePanel, 1);
    }
    content->addLayout(panels);

    auto *summary = card();
    auto *summaryColumn = column(summary, 20, 9);
    summaryColumn->addWidget(label(QStringLiteral("Bilateral Analysis"), 17, true));
    const QVariantMap os = resultFor(QStringLiteral("OS"));
    const QVariantMap od = resultFor(QStringLiteral("OD"));
    const QVariant left = os.value(QStringLiteral("grade"));
    const QVariant right = od.value(QStringLiteral("grade"));
    QString verdict;
    if (!left.isValid() || left.isNull() || !right.isValid() || right.isNull())
        verdict = QStringLiteral("Analyze both eyes to compare predicted DR grades.");
    else if (left.toInt() == right.toInt()) verdict = QStringLiteral("Both eyes have the same predicted DR grade (%1).").arg(left.toInt());
    else verdict = QStringLiteral("Higher predicted DR grade: %1.").arg(left.toInt() > right.toInt()
                                                                            ? QStringLiteral("Left eye (OS)") : QStringLiteral("Right eye (OD)"));
    summaryColumn->addWidget(label(verdict, 12, true, kPrimary));
    summaryColumn->addWidget(label(QStringLiteral("This compares model outputs only. No progression, treatment or management conclusion is inferred."), 9, false, kMuted));
    auto *report = button(QStringLiteral("Open Report"));
    connect(report, &QPushButton::clicked, this, [this] { navigate(Report); });
    summaryColumn->addWidget(report, 0, Qt::AlignLeft);
    content->addWidget(summary);
    return outer;
}

QWidget *MainWindow::buildHistory() {
    QVBoxLayout *content = nullptr;
    auto *outer = buildPageFrame(QString(), QString(), &content);
    auto *page = outer->findChild<QWidget*>(QStringLiteral("PageFrame"));
    page->setMaximumWidth(1600);
    content->setContentsMargins(width() >= 1024 ? 24 : 16, 0, width() >= 1024 ? 24 : 16, 0);

    struct PatientGroup {
        QString id;
        QString name;
        QVector<int> allSessions;
        QVector<int> matchingSessions;
        QDateTime latest;
        bool os = false;
        bool od = false;
    };
    const auto completedEyes = [](const PatientState &patient) {
        return qMakePair(patient.os.result.value(QStringLiteral("state")).toString() == QLatin1String("COMPLETE"),
                         patient.od.result.value(QStringLiteral("state")).toString() == QLatin1String("COMPLETE"));
    };
    const auto matchesDate = [this](const HistoryEntry &entry) {
        if (historyDateFilter_ == 0) return true;
        if (!entry.savedAt.isValid()) return false;
        const QDateTime now = QDateTime::currentDateTime();
        if (historyDateFilter_ == 1) return entry.savedAt.toLocalTime().date() == now.date();
        const qint64 age = entry.savedAt.msecsTo(now);
        const qint64 limit = (historyDateFilter_ == 2 ? 7LL : 30LL) * 24 * 60 * 60 * 1000;
        return age >= 0 && age <= limit;
    };

    QMap<QString, QVector<int>> sessionsByPatient;
    for (int index = 0; index < history_.size(); ++index) {
        const auto &entry = history_[index];
        const QString id = valueString(entry.patient.details, QStringLiteral("patientIdNumber"),
                                        entry.patient.details.value(QStringLiteral("id")).toString());
        sessionsByPatient[id].append(index);
    }
    QVector<PatientGroup> groups;
    const QString query = historyQuery_.trimmed();
    for (auto it = sessionsByPatient.cbegin(); it != sessionsByPatient.cend(); ++it) {
        PatientGroup group;
        group.id = it.key();
        group.allSessions = it.value();
        std::stable_sort(group.allSessions.begin(), group.allSessions.end(), [this](int left, int right) {
            return history_[left].savedAt > history_[right].savedAt;
        });
        if (group.allSessions.isEmpty()) continue;
        const auto &latest = history_[group.allSessions.first()];
        group.name = valueString(latest.patient.details, QStringLiteral("name"));
        group.latest = latest.savedAt;
        if (!query.isEmpty() && !QStringLiteral("%1 %2").arg(group.name, group.id).contains(query, Qt::CaseInsensitive)) continue;
        for (int index : group.allSessions) {
            const auto eyes = completedEyes(history_[index].patient);
            const bool eyeMatches = historyEyeFilter_ == 0 ||
                (historyEyeFilter_ == 1 && eyes.first) || (historyEyeFilter_ == 2 && eyes.second) ||
                (historyEyeFilter_ == 3 && eyes.first && eyes.second);
            if (!eyeMatches || !matchesDate(history_[index])) continue;
            group.matchingSessions.append(index);
            group.os = group.os || eyes.first;
            group.od = group.od || eyes.second;
        }
        if (group.matchingSessions.isEmpty()) continue;
        groups.append(group);
    }
    std::stable_sort(groups.begin(), groups.end(), [](const PatientGroup &left, const PatientGroup &right) {
        return left.latest > right.latest;
    });
    const int pageCount = qMax(1, (groups.size() + 9) / 10);
    historyPage_ = qBound(1, historyPage_, pageCount);

    auto *header = new QWidget;
    auto *headerLayout = new QHBoxLayout(header);
    headerLayout->setContentsMargins(0, 0, 0, 0);
    headerLayout->setSpacing(12);
    auto *heading = new QWidget;
    auto *headingLayout = column(heading, 0, 4);
    auto *title = label(QStringLiteral("Scan History"), 22, true);
    QFont titleFont(QStringLiteral("Manrope"), 22, QFont::ExtraBold);
    titleFont.setPixelSize(30);
    title->setFont(titleFont);
    title->setStyleSheet(QStringLiteral("letter-spacing: -0.03em; color: #181d18;"));
    headingLayout->addWidget(title);
    headingLayout->addWidget(label(QStringLiteral("Patients and all of their locally stored screening sessions."), 10, false, kMuted));
    headerLayout->addWidget(heading, 1, Qt::AlignVCenter);
    auto *count = label(QStringLiteral("%1 %2 · %3 %4")
                            .arg(groups.size()).arg(groups.size() == 1 ? QStringLiteral("patient") : QStringLiteral("patients"))
                            .arg(history_.size()).arg(history_.size() == 1 ? QStringLiteral("session") : QStringLiteral("sessions")),
                        9, true, kPrimary);
    count->setObjectName(QStringLiteral("HistorySummary"));
    count->setWordWrap(false);
    headerLayout->addWidget(count, 0, Qt::AlignRight | Qt::AlignVCenter);
    content->addWidget(header);
    auto *headerDivider = new QFrame;
    headerDivider->setObjectName(QStringLiteral("HistoryHeaderDivider"));
    headerDivider->setFrameShape(QFrame::HLine);
    headerDivider->setFrameShadow(QFrame::Plain);
    headerDivider->setLineWidth(2);
    headerDivider->setMidLineWidth(0);
    headerDivider->setStyleSheet(QStringLiteral("color: #becabd;"));
    content->addWidget(headerDivider);
    content->addSpacing(24);

    auto *filters = new QFrame;
    filters->setObjectName(QStringLiteral("HistoryFilters"));
    filters->setStyleSheet(QStringLiteral("QFrame#HistoryFilters { background: #f0f5ed; border: 1px solid #becabd; border-radius: 12px; }"));
    auto *filterRow = new QGridLayout(filters);
    filterRow->setContentsMargins(16, 16, 16, 16);
    filterRow->setHorizontalSpacing(10);
    filterRow->setVerticalSpacing(10);
    QFont iconFont(QStringLiteral("Material Symbols Outlined"));
    iconFont.setPixelSize(20);
    auto *searchBox = new QFrame;
    searchBox->setObjectName(QStringLiteral("HistorySearchField"));
    searchBox->setStyleSheet(QStringLiteral("QFrame#HistorySearchField { background: white; border: 1px solid #becabd; border-radius: 8px; }"));
    auto *searchRow = new QHBoxLayout(searchBox);
    searchRow->setContentsMargins(10, 0, 10, 0);
    searchRow->setSpacing(8);
    auto *searchIcon = new QLabel;
    QPixmap searchPixmap(20, 20);
    searchPixmap.fill(Qt::transparent);
    {
        QPainter painter(&searchPixmap);
        painter.setRenderHint(QPainter::Antialiasing);
        painter.setPen(QPen(QColor(kMuted), 2));
        painter.drawEllipse(QRect(2, 2, 11, 11));
        painter.drawLine(QPoint(12, 12), QPoint(18, 18));
    }
    searchIcon->setPixmap(searchPixmap);
    searchIcon->setAlignment(Qt::AlignCenter);
    searchIcon->setFixedWidth(20);
    auto *search = new QLineEdit;
    search->setObjectName(QStringLiteral("HistorySearch"));
    search->setPlaceholderText(QStringLiteral("Search by patient name or ID"));
    search->setText(historyQuery_);
    search->setMinimumHeight(44);
    search->setStyleSheet(QStringLiteral("QLineEdit#HistorySearch { background: transparent; border: 0; padding: 5px 3px; min-height: 28px; font-size: 13px; }"));
    searchRow->addWidget(searchIcon);
    searchRow->addWidget(search, 1);
    auto *date = new QComboBox;
    date->setObjectName(QStringLiteral("HistoryDateFilter"));
    date->addItems({QStringLiteral("All dates"), QStringLiteral("Today"), QStringLiteral("Last 7 days"), QStringLiteral("Last 30 days")});
    date->setCurrentIndex(historyDateFilter_);
    date->setMinimumHeight(44);
    auto *eye = new QComboBox;
    eye->setObjectName(QStringLiteral("HistoryEyeFilter"));
    eye->addItems({QStringLiteral("All eyes"), QStringLiteral("Left (OS)"), QStringLiteral("Right (OD)"), QStringLiteral("Both")});
    eye->setCurrentIndex(historyEyeFilter_);
    eye->setMinimumHeight(44);
    const QString comboStyle = QStringLiteral("QComboBox { background: white; border: 1px solid #becabd; border-radius: 8px; padding: 6px 28px 6px 12px; min-width: 116px; font-size: 12px; font-weight: 700; } QComboBox::drop-down { border: 0; width: 24px; }");
    date->setStyleSheet(comboStyle);
    eye->setStyleSheet(comboStyle);
    filterRow->addWidget(searchBox, 0, 0);
    filterRow->addWidget(date, 0, 1);
    filterRow->addWidget(eye, 0, 2);
    filterRow->setColumnStretch(0, 1);
    content->addWidget(filters);
    content->addSpacing(20);

    if (!historyNotice_.isEmpty()) {
        auto *notice = label(historyNotice_, 10, true, kPrimary);
        notice->setObjectName(QStringLiteral("HistoryDownloadNotice"));
        notice->setStyleSheet(QStringLiteral("color: #005227; background: #e7f7e9; border: 1px solid #9ccea7; border-radius: 10px; padding: 10px 14px;"));
        content->addWidget(notice);
        content->addSpacing(12);
    }
    const QString shownError = !historyError_.isEmpty() ? historyError_ : stateLoadError_;
    if (!shownError.isEmpty()) {
        auto *error = label(shownError, 10, true, kError);
        error->setObjectName(QStringLiteral("HistoryError"));
        error->setStyleSheet(QStringLiteral("color: #ba1a1a; background: #ffdad6; border: 1px solid #e5aaa4; border-radius: 10px; padding: 10px 14px;"));
        content->addWidget(error);
        content->addSpacing(12);
    }

    auto *split = new QWidget;
    split->setObjectName(QStringLiteral("HistoryMasterDetail"));
    auto *splitLayout = new QGridLayout(split);
    splitLayout->setContentsMargins(0, 0, 0, 0);
    splitLayout->setHorizontalSpacing(20);
    splitLayout->setVerticalSpacing(16);
    auto *tableCard = new QFrame;
    tableCard->setObjectName(QStringLiteral("HistoryPatientTableCard"));
    tableCard->setStyleSheet(QStringLiteral("QFrame#HistoryPatientTableCard { background: white; border: 1px solid #becabd; border-radius: 12px; }"));
    auto *tableLayout = new QVBoxLayout(tableCard);
    tableLayout->setContentsMargins(0, 0, 0, 0);
    tableLayout->setSpacing(0);
    if (groups.isEmpty()) {
        tableCard->setFixedHeight(270);
        auto *empty = new QWidget;
        auto *emptyLayout = column(empty, 36, 8);
        emptyLayout->setAlignment(Qt::AlignCenter);
        auto *historyIcon = label(QStringLiteral("history"), 28, false, kPrimary);
        historyIcon->setFont(iconFont);
        historyIcon->setAlignment(Qt::AlignCenter);
        emptyLayout->addWidget(historyIcon, 0, Qt::AlignCenter);
        auto *emptyTitle = label(QStringLiteral("No patients found"), 14, true);
        emptyTitle->setAlignment(Qt::AlignCenter);
        emptyLayout->addWidget(emptyTitle);
        auto *emptyMessage = label(QStringLiteral("Try changing the search or filters."), 10, false, kMuted);
        emptyMessage->setAlignment(Qt::AlignCenter);
        emptyLayout->addWidget(emptyMessage);
        empty->setMinimumHeight(270);
        tableLayout->addWidget(empty);
    } else {
        auto *table = new QTableWidget;
        table->setObjectName(QStringLiteral("PatientHistoryTable"));
        const int first = (historyPage_ - 1) * 10;
        const int rowCount = qMin(10, groups.size() - first);
        table->setRowCount(rowCount);
        table->setColumnCount(6);
        table->setHorizontalHeaderLabels({QStringLiteral("Patient name"), QStringLiteral("Patient ID"), QStringLiteral("Last scan"),
                                          QStringLiteral("Sessions"), QStringLiteral("Eye(s)"), QStringLiteral("Actions")});
        table->horizontalHeader()->setSectionResizeMode(QHeaderView::Interactive);
        table->horizontalHeader()->setFixedHeight(42);
        table->horizontalHeader()->setDefaultAlignment(Qt::AlignLeft | Qt::AlignVCenter);
        table->setColumnWidth(0, 150);
        table->setColumnWidth(1, 104);
        table->setColumnWidth(2, 126);
        table->setColumnWidth(3, 84);
        table->setColumnWidth(4, 66);
        table->setColumnWidth(5, 120);
        table->horizontalHeader()->setStretchLastSection(true);
        table->verticalHeader()->hide();
        table->setShowGrid(false);
        table->setAlternatingRowColors(false);
        table->setSelectionMode(QAbstractItemView::NoSelection);
        table->setEditTriggers(QAbstractItemView::NoEditTriggers);
        table->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
        table->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        table->setStyleSheet(QStringLiteral("QTableWidget { border: 0; background: white; gridline-color: #becabd; } QHeaderView::section { background: #f0f5ed; color: #3f4940; border: 0; border-bottom: 1px solid #becabd; padding: 10px 7px; font-size: 10px; font-weight: 800; letter-spacing: 0.5px; text-transform: uppercase; } QTableWidget::item { border-bottom: 1px solid #e5eae2; padding: 6px; } QTableWidget::item:hover { background: #f0f5ed; }"));
        for (int row = 0; row < rowCount; ++row) {
            const PatientGroup &group = groups[first + row];
            const bool selected = group.id == selectedHistoryPatientId_;
            const QColor rowColor(selected ? QStringLiteral("#eef7ee") : QStringLiteral("#ffffff"));
            const auto addItem = [&](int column, const QString &text, bool bold = false, const QString &color = QStringLiteral("#3f4940")) {
                auto *item = new QTableWidgetItem(text);
                item->setForeground(QColor(color));
                auto font = item->font();
                font.setBold(bold);
                item->setFont(font);
                item->setBackground(rowColor);
                item->setToolTip(text);
                table->setItem(row, column, item);
            };
            addItem(0, group.name, true, QStringLiteral("#181d18"));
            addItem(1, QStringLiteral("#%1").arg(group.id), true);
            addItem(2, group.latest.isValid() ? QLocale().toString(group.latest, QLocale::ShortFormat) : QStringLiteral("—"));
            addItem(3, QStringLiteral("%1 %2").arg(group.allSessions.size()).arg(group.allSessions.size() == 1 ? QStringLiteral("session") : QStringLiteral("sessions")), true, QStringLiteral("#181d18"));
            auto *eyes = new QWidget;
            auto *eyeRow = new QHBoxLayout(eyes);
            eyeRow->setContentsMargins(3, 0, 3, 0);
            eyeRow->setSpacing(4);
            for (const auto &eyeName : {QStringLiteral("OS"), QStringLiteral("OD")}) {
                const bool present = eyeName == QLatin1String("OS") ? group.os : group.od;
                if (!present) continue;
                auto *pill = label(eyeName, 8, true, kPrimary);
                pill->setAlignment(Qt::AlignCenter);
                pill->setStyleSheet(QStringLiteral("color: #005227; background: #e7f7e9; border-radius: 5px; padding: 3px 5px;"));
                eyeRow->addWidget(pill);
            }
            eyeRow->addStretch();
            eyes->setStyleSheet(QStringLiteral("background: %1;").arg(selected ? QStringLiteral("#eef7ee") : QStringLiteral("white")));
            table->setCellWidget(row, 4, eyes);
            table->setRowHeight(row, 62);
            auto *view = button(QStringLiteral("View history"), true);
            view->setObjectName(QStringLiteral("ViewHistory_%1").arg(group.id));
            view->setAccessibleName(QStringLiteral("View history: %1").arg(group.id));
            view->setMinimumHeight(34);
            view->setFixedWidth(110);
            view->setStyleSheet(QStringLiteral("QPushButton { background: #005227; color: white; border: 0; border-radius: 8px; padding: 6px 9px; font-size: 11px; font-weight: 800; } QPushButton:hover { background: #006d36; }"));
            connect(view, &QPushButton::clicked, this, [this, id = group.id] {
                selectedHistoryPatientId_ = id;
                historyError_.clear();
                rebuildPage(History);
            });
            table->setCellWidget(row, 5, view);
        }
        table->setFixedHeight(table->horizontalHeader()->height() + rowCount * 62 + 2);
        tableLayout->addWidget(table);
        auto *pager = new QWidget;
        pager->setObjectName(QStringLiteral("HistoryPagination"));
        pager->setStyleSheet(QStringLiteral("border-top: 1px solid #becabd;"));
        auto *pagerRow = new QHBoxLayout(pager);
        pagerRow->setContentsMargins(14, 9, 14, 9);
        auto *pageLabel = label(QStringLiteral("Page %1 of %2").arg(historyPage_).arg(pageCount), 9, false, kMuted);
        pageLabel->setObjectName(QStringLiteral("HistoryPage"));
        pagerRow->addWidget(pageLabel);
        pagerRow->addStretch();
        auto *previous = button(QStringLiteral("Previous"));
        previous->setObjectName(QStringLiteral("HistoryPrevious"));
        previous->setAccessibleName(QStringLiteral("History Previous"));
        previous->setMinimumHeight(34);
        previous->setEnabled(historyPage_ > 1);
        auto *next = button(QStringLiteral("Next"));
        next->setObjectName(QStringLiteral("HistoryNext"));
        next->setAccessibleName(QStringLiteral("History Next"));
        next->setMinimumHeight(34);
        next->setEnabled(historyPage_ < pageCount);
        connect(previous, &QPushButton::clicked, this, [this] { historyPage_ = qMax(1, historyPage_ - 1); rebuildPage(History); });
        connect(next, &QPushButton::clicked, this, [this, pageCount] { historyPage_ = qMin(pageCount, historyPage_ + 1); rebuildPage(History); });
        pagerRow->addWidget(previous);
        pagerRow->addWidget(next);
        tableLayout->addWidget(pager);
    }

    auto *detail = new QFrame;
    detail->setObjectName(QStringLiteral("SelectedPatientHistory"));
    detail->setStyleSheet(QStringLiteral("QFrame#SelectedPatientHistory { background: #f0f5ed; border: 1px solid #becabd; border-radius: 12px; }"));
    auto *detailLayout = new QVBoxLayout(detail);
    detailLayout->setContentsMargins(20, 20, 20, 20);
    detailLayout->setSpacing(14);
    QVector<int> selectedSessions = sessionsByPatient.value(selectedHistoryPatientId_);
    std::stable_sort(selectedSessions.begin(), selectedSessions.end(), [this](int left, int right) {
        return history_[left].savedAt > history_[right].savedAt;
    });
    if (!selectedSessions.isEmpty()) {
        const QString selectedPatientId = selectedHistoryPatientId_;
        const int selectedIndex = selectedSessions.first();
        const QVariantMap patientDetails = history_[selectedIndex].patient.details;
        const QString selectedName = valueString(patientDetails, QStringLiteral("name"));
        auto *patientName = label(selectedName, 18, true);
        patientName->setObjectName(QStringLiteral("SelectedHistoryPatientName"));
        patientName->setWordWrap(false);
        detailLayout->addWidget(patientName);
        detailLayout->addWidget(label(QStringLiteral("Patient ID: #%1").arg(selectedPatientId), 10, true, kMuted));
        detailLayout->addWidget(label(QStringLiteral("%1 SCREENING %2").arg(selectedSessions.size()).arg(selectedSessions.size() == 1 ? QStringLiteral("SESSION") : QStringLiteral("SESSIONS")), 9, true, kPrimary));
        auto *divider = new QFrame;
        divider->setFrameShape(QFrame::HLine);
        divider->setStyleSheet(QStringLiteral("color: #becabd;"));
        detailLayout->addWidget(divider);
        auto *sessionList = new QScrollArea;
        sessionList->setObjectName(QStringLiteral("PatientSessions"));
        sessionList->setWidgetResizable(true);
        sessionList->setFrameShape(QFrame::NoFrame);
        sessionList->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        sessionList->setMaximumHeight(qMax(180, height() - 330));
        auto *sessionContent = new QWidget;
        auto *sessionLayout = new QVBoxLayout(sessionContent);
        sessionLayout->setContentsMargins(0, 0, 4, 0);
        sessionLayout->setSpacing(10);
        for (int index : selectedSessions) {
            const HistoryEntry &entry = history_[index];
            const auto eyes = completedEyes(entry.patient);
            const int completed = int(eyes.first) + int(eyes.second);
            const QString status = completed == 2 ? QStringLiteral("Complete") : completed == 1 ? QStringLiteral("Partially complete") : QStringLiteral("Saved session");
            const QString id = historySessionId(entry);
            auto *sessionCard = new QFrame;
            sessionCard->setObjectName(QStringLiteral("HistorySessionCard"));
            sessionCard->setProperty("sessionId", id);
            sessionCard->setStyleSheet(QStringLiteral("QFrame#HistorySessionCard { background: white; border: 1px solid #e5eae2; border-radius: 12px; }"));
            auto *sessionLayoutInner = new QVBoxLayout(sessionCard);
            sessionLayoutInner->setContentsMargins(14, 12, 14, 12);
            sessionLayoutInner->setSpacing(7);
            auto *sessionHead = new QHBoxLayout;
            auto *dateColumn = new QWidget;
            auto *dateLayout = column(dateColumn, 0, 2);
            const QString dateText = entry.savedAt.isValid() ? QLocale().toString(entry.savedAt.toLocalTime().date(), QLocale::ShortFormat) : QStringLiteral("Date unavailable");
            const QString timeText = entry.savedAt.isValid() ? QLocale().toString(entry.savedAt.toLocalTime().time(), QLocale::ShortFormat) : QStringLiteral("Time unavailable");
            dateLayout->addWidget(label(QStringLiteral("%1  •  %2").arg(dateText, timeText), 10, true));
            auto *sessionIdLabel = label(QStringLiteral("Session: %1").arg(id), 8, false, kMuted);
            sessionIdLabel->setWordWrap(true);
            dateLayout->addWidget(sessionIdLabel);
            sessionHead->addWidget(dateColumn, 1);
            auto *statusBadge = label(status, 8, true, completed == 2 ? kPrimary : kMuted);
            statusBadge->setWordWrap(false);
            statusBadge->setStyleSheet(QStringLiteral("color: %1; background: %2; border-radius: 6px; padding: 4px 7px;")
                                           .arg(completed == 2 ? QStringLiteral("#005227") : QStringLiteral("#3f4940"),
                                                completed == 2 ? QStringLiteral("#e7f7e9") : QStringLiteral("#e5eae2")));
            sessionHead->addWidget(statusBadge, 0, Qt::AlignTop);
            sessionLayoutInner->addLayout(sessionHead);
            auto *summary = new QHBoxLayout;
            summary->setSpacing(8);
            QVariantMap osResult = reporting::withContext(entry.patient.os.result, entry.patient.details, "OS", entry.patient.os.capturedAt.isValid() ? entry.patient.os.capturedAt : entry.savedAt, entry.patient.os.imagePath);
            QVariantMap odResult = reporting::withContext(entry.patient.od.result, entry.patient.details, "OD", entry.patient.od.capturedAt.isValid() ? entry.patient.od.capturedAt : entry.savedAt, entry.patient.od.imagePath);
            for (const auto &eyeCode : {QStringLiteral("OS"), QStringLiteral("OD")}) {
                const bool present = eyeCode == QLatin1String("OS") ? eyes.first : eyes.second;
                if (!present) continue;
                auto *pill = label(eyeCode, 8, true, kPrimary);
                pill->setStyleSheet(QStringLiteral("color: #005227; background: white; border: 1px solid #9ccea7; border-radius: 5px; padding: 3px 7px;"));
                summary->addWidget(pill);
                const QVariantMap &result = eyeCode == QLatin1String("OS") ? osResult : odResult;
                QVariant grade = result.value(QStringLiteral("grade"));
                if (!grade.isValid()) grade = result.value(QStringLiteral("grading")).toMap().value(QStringLiteral("predicted_grade"));
                if (grade.isValid() && !grade.isNull()) summary->addWidget(label(QStringLiteral("%1: Grade %2").arg(eyeCode, grade.toString()), 8, true, kMuted));
            }
            summary->addStretch();
            sessionLayoutInner->addLayout(summary);
            auto *actions = new QHBoxLayout;
            actions->setSpacing(8);
            auto *viewReports = button(QStringLiteral("View Reports"), true);
            viewReports->setObjectName(QStringLiteral("HistoryViewReports_%1").arg(id));
            viewReports->setAccessibleName(QStringLiteral("View Reports: %1").arg(id));
            viewReports->setMinimumHeight(34);
            viewReports->setStyleSheet(QStringLiteral("QPushButton { background: #005227; color: white; border: 1px solid #005227; border-radius: 8px; padding: 6px 11px; font-size: 11px; font-weight: 800; } QPushButton:hover { background: #006d36; } QPushButton:disabled { background: #dfe4dc; color: #6f7a6f; border-color: #dfe4dc; }"));
            viewReports->setEnabled(completed > 0);
            const QVariantMap patientSnapshot = entry.patient.details;
            connect(viewReports, &QPushButton::clicked, this, [this, id, eyes, osResult, odResult, patientSnapshot] {
                historyReport_ = {{QStringLiteral("sessionId"), id},
                                  {QStringLiteral("patient"), patientSnapshot},
                                  {QStringLiteral("os"), osResult},
                                  {QStringLiteral("od"), odResult}};
                activeEye_ = eyes.first ? QStringLiteral("OS") : QStringLiteral("OD");
                rebuildPage(Report);
                navigate(Report);
            });
            actions->addWidget(viewReports);
            auto *download = button(QStringLiteral("Download"));
            download->setObjectName(QStringLiteral("HistoryDownload_%1").arg(id));
            download->setAccessibleName(QStringLiteral("Download: %1").arg(id));
            download->setMinimumHeight(34);
            download->setStyleSheet(QStringLiteral("QPushButton { background: white; color: #005227; border: 1px solid #005227; border-radius: 8px; padding: 6px 11px; font-size: 11px; font-weight: 800; } QPushButton:hover { background: #e7f7e9; } QPushButton:disabled { background: #dfe4dc; color: #6f7a6f; border-color: #becabd; }"));
            download->setEnabled(completed > 0);
            connect(download, &QPushButton::clicked, this, [this, download, id, eyes, osResult, odResult] {
                if (eyes.first && eyes.second) {
                    auto *menu = new QMenu(download);
                    menu->setObjectName(QStringLiteral("HistoryDownloadMenu"));
                    menu->setStyleSheet(QStringLiteral("QMenu { background: white; border: 1px solid #becabd; border-radius: 10px; padding: 5px; } QMenu::item { padding: 9px 14px; border-radius: 6px; color: #181d18; } QMenu::item:selected { background: #f0f5ed; }"));
                    auto *left = menu->addAction(QStringLiteral("Download Left Eye Report"));
                    auto *right = menu->addAction(QStringLiteral("Download Right Eye Report"));
                    connect(left, &QAction::triggered, this, [this, id, osResult] { requestHistoryReportDownload(id, QStringLiteral("OS"), osResult); });
                    connect(right, &QAction::triggered, this, [this, id, odResult] { requestHistoryReportDownload(id, QStringLiteral("OD"), odResult); });
                    menu->popup(download->mapToGlobal(QPoint(0, download->height())));
                } else {
                    requestHistoryReportDownload(id, eyes.first ? QStringLiteral("OS") : QStringLiteral("OD"), eyes.first ? osResult : odResult);
                }
            });
            actions->addWidget(download);
            actions->addStretch();
            sessionLayoutInner->addLayout(actions);
            sessionLayout->addWidget(sessionCard);
        }
        sessionLayout->addStretch();
        sessionList->setWidget(sessionContent);
        detailLayout->addWidget(sessionList, 1);
    } else {
        auto *empty = new QWidget;
        auto *emptyLayout = column(empty, 24, 10);
        emptyLayout->setAlignment(Qt::AlignCenter);
        auto *icon = label(QStringLiteral("patient_list"), 34, false, kPrimary);
        icon->setFont(iconFont);
        icon->setAlignment(Qt::AlignCenter);
        emptyLayout->addWidget(icon, 0, Qt::AlignCenter);
        auto *emptyTitle = label(QStringLiteral("Select a patient"), 15, true);
        emptyTitle->setAlignment(Qt::AlignCenter);
        emptyLayout->addWidget(emptyTitle);
        auto *emptyMessage = label(QStringLiteral("Select a patient to view previous screening sessions."), 10, false, kMuted);
        emptyMessage->setAlignment(Qt::AlignCenter);
        emptyLayout->addWidget(emptyMessage);
        detailLayout->addWidget(empty, 1);
    }

    if (width() >= 1120) {
        splitLayout->addWidget(tableCard, 0, 0, Qt::AlignTop);
        splitLayout->addWidget(new HistoryStickySlot(detail, scrolls_[History]), 0, 1, Qt::AlignTop);
        splitLayout->setColumnStretch(0, 11);
        splitLayout->setColumnStretch(1, 9);
    } else {
        splitLayout->addWidget(tableCard, 0, 0, Qt::AlignTop);
        splitLayout->addWidget(detail, 1, 0);
    }
    content->addWidget(split);
    content->addStretch(1);

    auto resetPage = [this] { historyPage_ = 1; rebuildPage(History); };
    connect(search, &QLineEdit::textChanged, this, [this, search](const QString &text) {
        historyQuery_ = text;
        historyPage_ = 1;
        const int cursor = search->cursorPosition();
        rebuildPage(History);
        for (auto *field : findChildren<QLineEdit*>(QStringLiteral("HistorySearch"))) {
            if (!field->isVisible()) continue;
            field->setFocus(Qt::OtherFocusReason);
            field->setCursorPosition(qBound(0, cursor, field->text().size()));
            break;
        }
    });
    connect(date, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this, resetPage](int index) { historyDateFilter_ = index; resetPage(); });
    connect(eye, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this, resetPage](int index) { historyEyeFilter_ = index; resetPage(); });
    return outer;
}

void MainWindow::requestHistoryReportDownload(const QString &sessionId, const QString &eye, const QVariantMap &result) {
    if (result.value(QStringLiteral("state")).toString() != QLatin1String("COMPLETE")) {
        historyError_ = QStringLiteral("This session does not contain a completed %1 report.").arg(eye);
        rebuildPage(History);
        return;
    }
    const QString destination = QFileDialog::getExistingDirectory(this, QStringLiteral("Choose RetinaGram history report destination"));
    if (destination.isEmpty()) return;
    historyNotice_.clear();
    historyError_.clear();
    emit historyReportDownloadRequested(sessionId, eye, result, destination);
}

void MainWindow::setHistoryDownloadResult(QString eye, QString path, QString error) {
    if (error.isEmpty()) {
        historyNotice_ = QStringLiteral("%1 report saved to %2").arg(eye, path);
        historyError_.clear();
    } else {
        historyError_ = error;
        historyNotice_.clear();
    }
    if (currentPage_ == History) rebuildPage(History);
    else headerStatus_->setText(error.isEmpty() ? QStringLiteral("%1 report saved to %2").arg(eye, path)
                                                : QStringLiteral("History report export failed: %1").arg(error));
}

QWidget *MainWindow::buildCloud() {
    QVBoxLayout *content = nullptr;
    auto *outer = buildPageFrame(QString(), QString(), &content);
    auto *heading = new QWidget;
    auto *headingColumn = column(heading, 0, 8);
    auto *back = button(QStringLiteral("← Back"));
    back->setFixedHeight(36);
    back->setStyleSheet(QStringLiteral(
        "QPushButton#SecondaryButton { background: transparent; color: #005227; border: none; padding: 0; font-weight: 700; font-size: 14px; }"
        "QPushButton#SecondaryButton:hover { background: #f0f5ed; }"
    ));
    connect(back, &QPushButton::clicked, this, [this] { navigate(Capture); });
    headingColumn->addWidget(back, 0, Qt::AlignLeft);
    auto *cloudTitle = label(QStringLiteral("Cloud Sync"), 22, true, kPrimary);
    QFont cloudFont(QStringLiteral("Manrope"), 22, QFont::ExtraBold);
    cloudFont.setPixelSize(30);
    cloudTitle->setFont(cloudFont);
    headingColumn->addWidget(cloudTitle);
    headingColumn->addWidget(label(QStringLiteral("Keep patient records and reports available across your RetinaGram devices."), 10, false, kMuted));
    content->addWidget(heading);

    auto *topGrid = new QHBoxLayout;
    topGrid->setSpacing(20);
    auto *status = card();
    auto *statusColumn = column(status, 24, 14);
    auto *statusTitle = label(QStringLiteral("Cloud synchronization"), 14, true);
    statusTitle->setFont(QFont(QStringLiteral("Manrope"), 14, QFont::ExtraBold));
    statusColumn->addWidget(statusTitle);
    statusColumn->addWidget(label(QStringLiteral("●  Not connected"), 12, true, kError));
    statusColumn->addWidget(label(QStringLiteral("Your patient data currently stays on this PC. A cloud provider is not configured in this native build."), 11, false, kMuted));
    auto *stats = new QGridLayout;
    stats->setContentsMargins(0, 0, 0, 0);
    stats->setHorizontalSpacing(24);
    stats->setVerticalSpacing(12);
    addLabeledValue(stats, 0, 0, QStringLiteral("Patients"), QString::number(patients_.size()));
    addLabeledValue(stats, 0, 1, QStringLiteral("Sessions"), QString::number(history_.size()));
    addLabeledValue(stats, 0, 2, QStringLiteral("Reports"), QString::number(std::count_if(history_.cbegin(), history_.cend(), [](const HistoryEntry &entry) {
        return !entry.patient.os.result.isEmpty() || !entry.patient.od.result.isEmpty();
    })));
    statusColumn->addLayout(stats);
    topGrid->addWidget(status, 155);
    auto *sync = card();
    auto *syncColumn = column(sync, 24, 14);
    auto *syncTitle = label(QStringLiteral("Synchronization"), 14, true);
    syncTitle->setFont(QFont(QStringLiteral("Manrope"), 14, QFont::ExtraBold));
    syncColumn->addWidget(syncTitle);
    for (const QString &text : {QStringLiteral("Automatic sync"), QStringLiteral("Patient metadata"),
                                QStringLiteral("Reports"), QStringLiteral("Retinal images")}) {
        auto *checkbox = new QCheckBox(text);
        checkbox->setEnabled(false);
        checkbox->setStyleSheet(QStringLiteral("QCheckBox { font-size: 12px; color: #181d18; } QCheckBox::indicator { width: 18px; height: 18px; }"));
        syncColumn->addWidget(checkbox);
    }
    syncColumn->addWidget(label(QStringLiteral("Cloud provider is not configured yet."), 10, false, kMuted));
    syncColumn->addStretch();
    topGrid->addWidget(sync, 100);
    content->addLayout(topGrid);

    auto *bottomGrid = new QHBoxLayout;
    bottomGrid->setSpacing(20);
    auto *storage = card();
    auto *storageColumn = column(storage, 24, 14);
    auto *storageTitle = label(QStringLiteral("Offline storage"), 14, true);
    storageTitle->setFont(QFont(QStringLiteral("Manrope"), 14, QFont::ExtraBold));
    storageColumn->addWidget(storageTitle);
    storageColumn->addWidget(label(QStringLiteral("Current patients and sessions are stored on this PC. Exported reports remain in the folder you choose."), 11, false, kMuted));
    auto *storageStats = new QGridLayout;
    storageStats->setContentsMargins(0, 8, 0, 0);
    storageStats->setHorizontalSpacing(24);
    storageStats->setVerticalSpacing(8);
    addLabeledValue(storageStats, 0, 0, QStringLiteral("Local patient records"), QString::number(patients_.size()));
    addLabeledValue(storageStats, 0, 1, QStringLiteral("Scan sessions"), QString::number(history_.size()));
    addLabeledValue(storageStats, 0, 2, QStringLiteral("Images"), QString::number(std::count_if(history_.cbegin(), history_.cend(), [](const HistoryEntry &entry) {
        return !entry.patient.os.imagePath.isEmpty() || !entry.patient.od.imagePath.isEmpty();
    })));
    addLabeledValue(storageStats, 0, 3, QStringLiteral("Reports"), QString::number(std::count_if(history_.cbegin(), history_.cend(), [](const HistoryEntry &entry) {
        return !entry.patient.os.result.isEmpty() || !entry.patient.od.result.isEmpty();
    })));
    storageColumn->addLayout(storageStats);
    auto *openFolder = button(QStringLiteral("Open data folder"));
    openFolder->setMinimumHeight(40);
    openFolder->setStyleSheet(QStringLiteral(
        "QPushButton#SecondaryButton { background: white; color: #005227; border: 1px solid #6f7a6f; border-radius: 10px; padding: 8px 16px; font-weight: 700; font-size: 12px; }"
        "QPushButton#SecondaryButton:hover { background: #f0f5ed; }"
    ));
    storageColumn->addWidget(openFolder, 0, Qt::AlignLeft);
    bottomGrid->addWidget(storage, 155);
    auto *management = card();
    auto *managementColumn = column(management, 24, 14);
    auto *managementTitle = label(QStringLiteral("Data management"), 14, true);
    managementTitle->setFont(QFont(QStringLiteral("Manrope"), 14, QFont::ExtraBold));
    managementColumn->addWidget(managementTitle);
    managementColumn->addWidget(label(QStringLiteral("Clear local data"), 14, true));
    managementColumn->addWidget(label(QStringLiteral("Remove locally stored RetinaGram patient records, scans, reports and generated analysis files from this computer."), 10, false, kMuted));
    auto *clear = button(QStringLiteral("Clear local history"));
    clear->setEnabled(!history_.isEmpty());
    clear->setMinimumHeight(40);
    clear->setStyleSheet(QStringLiteral(
        "QPushButton#SecondaryButton { background: white; color: #ba1a1a; border: 1px solid #ba1a1a; border-radius: 10px; padding: 8px 16px; font-weight: 700; font-size: 12px; }"
        "QPushButton#SecondaryButton:hover { background: #ffdad6; }"
    ));
    connect(clear, &QPushButton::clicked, this, [this] {
        if (QMessageBox::warning(this, QStringLiteral("Clear history?"),
                                 QStringLiteral("Remove the locally saved history entries? Exported report files are unaffected."),
                                 QMessageBox::Cancel | QMessageBox::Yes, QMessageBox::Cancel) != QMessageBox::Yes) return;
        history_.clear();
        saveState();
        rebuildPage(History);
        rebuildPage(Cloud);
    });
    managementColumn->addWidget(clear, 0, Qt::AlignLeft);
    bottomGrid->addWidget(management, 100);
    content->addLayout(bottomGrid);
    return outer;
}

} // namespace retina




