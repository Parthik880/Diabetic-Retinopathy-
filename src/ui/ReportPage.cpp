#include "ui/MainWindow.h"
#include "ui/UiComponents.h"
#include "reporting/ScreeningReport.h"
#include "image/ImageDecoder.h"

#include <QFileDialog>
#include <QMessageBox>
#include <QScrollArea>
#include <QSaveFile>
#include <QTextStream>

namespace retina {
namespace {
QVBoxLayout *stack(QWidget *w,int margin=0,int gap=0) {
    auto *layout=new QVBoxLayout(w); layout->setContentsMargins(margin,margin,margin,margin); layout->setSpacing(gap); return layout;
}
QFrame *panel(QString name,QString background="white",bool border=true) {
    auto *w=new QFrame; w->setObjectName(name);
    w->setStyleSheet(QString("QFrame#%1 { background:%2; border:%3; border-radius:12px; }").arg(name,background,border?"1px solid #becabd":"0"));
    return w;
}
QFrame *line() { auto *w=new QFrame; w->setFrameShape(QFrame::HLine); w->setFixedHeight(1); w->setStyleSheet("background:#becabd; border:0;"); return w; }
class ReportImage final : public ui::ImageStage {
public:
    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return w*2/3; }
    QSize sizeHint() const override { return {270,180}; }
    QSize minimumSizeHint() const override { return {120,80}; }
protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this); p.setRenderHints(QPainter::Antialiasing | QPainter::SmoothPixmapTransform);
        QPainterPath shape; shape.addRoundedRect(QRectF(rect()).adjusted(0.5,0.5,-0.5,-0.5),12,12);
        p.fillPath(shape,Qt::black); p.setClipPath(shape);
        if(!image.isNull()) p.drawImage(imageRect(),image);
        else { p.setPen(QColor("#b8c5bd")); p.drawText(rect(),Qt::AlignCenter,"Image unavailable"); }
        p.setClipping(false); p.setPen(QPen(QColor("#becabd"),1)); p.drawPath(shape);
    }
};
}

QVariantMap MainWindow::reportData(const QString &eye) const {
    if(!historyReport_.isEmpty()) return historyReport_.value(eye=="OS"?"os":"od").toMap();
    if(currentPatient_<0) return {};
    const auto *scan=eyeState(eye);
    QDateTime date=scan->capturedAt;
    if(!date.isValid()) {
        // Older persisted scans predate capture timestamps. Their saved session
        // date is the only retained scan-time evidence.
        for(auto it=history_.crbegin();it!=history_.crend();++it) {
            const auto &old=eye=="OS"?it->patient.os:it->patient.od;
            if(it->patient.details.value("patientIdNumber")==patients_[currentPatient_].details.value("patientIdNumber") && old.imagePath==scan->imagePath) { date=it->savedAt; break; }
        }
    }
    return reporting::withContext(scan->result,patients_[currentPatient_].details,eye,date,scan->imagePath);
}

QWidget *MainWindow::buildReport() {
    QVBoxLayout *content=nullptr;
    auto *outer=buildPageFrame({}, {}, &content);
    outer->findChild<QWidget*>("PageFrame")->setMaximumWidth(1152);
    content->setSpacing(20);
    content->setContentsMargins(width()>=768?24:16,0,width()>=768?24:16,0);
    const bool historic=!historyReport_.isEmpty();
    if(currentPatient_<0&&!historic) { content->addWidget(buildEmptyState("▤","No screening report yet","Register a patient and analyze a retinal image.")); return outer; }
    auto available=[this](QString eye) { return reportData(eye).value("state")=="COMPLETE"; };
    QStringList options;
    for(const auto &eye:{QString("OS"),QString("OD")}) {
        QString status=available(eye)?QString::fromUtf8("✓"):historic?"Pending capture":resultState(eye);
        options<<eyeName(eye)+"  "+status;
    }
    auto *tabs=ui::segmented("Report eye",options,options[activeEye_=="OS"?0:1],this,[this,options](QString value) {
        activeEye_=value==options[0]?"OS":"OD"; rebuildPage(Report);
    });
    tabs->setStyleSheet(tabs->styleSheet().replace("QFrame#Segmented", "QFrame#ReportEyeSelector"));
    tabs->setObjectName("ReportEyeSelector");
    for(auto *b:tabs->findChildren<QPushButton*>()) {
        QFont font("Segoe UI"); font.setPixelSize(14); font.setBold(true); b->setFont(font); b->setMinimumHeight(40);
    }
    content->addWidget(tabs,0,Qt::AlignLeft);
    const auto result=reportData(activeEye_);
    if(result.value("state")!="COMPLETE") {
        const bool running=busy_&&activeAnalysisEye_==activeEye_;
        const bool reject=result.value("state")=="RECAPTURE_REQUIRED";
        content->addWidget(buildEmptyState("▤",running?"Analysis in progress":reject?"Recapture required":"No screening report yet",
            running?eyeState(activeEye_)->stage:reject?"Image quality was rejected. Capture a new image; no grade or lesion findings were generated.":"Complete analysis for "+eyeName(activeEye_)+" before creating its report.")); return outer;
    }
    const reporting::Data report(result);
    auto *paper=panel("ReportDocument");
    auto *paperColumn=stack(paper);
    auto *header=panel("ReportHeader","#f7fbf8",false);
    auto *head=new QHBoxLayout(header); head->setContentsMargins(32,20,32,20); head->setSpacing(12);
    auto *logo=new QLabel; logo->setFixedSize(56,56);
    logo->setPixmap(QPixmap(reporting::assetPath("logo.jpeg")).scaled(56,56,Qt::KeepAspectRatio,Qt::SmoothTransformation)); head->addWidget(logo);
    auto *brand=new QWidget; auto *brandCol=stack(brand,0,2);
    brandCol->addWidget(ui::text("RetinaGram",24,true,"#005227")); brandCol->addWidget(ui::text("AI Retinal Screening",12,true,"#3f4940")); head->addWidget(brand,1);
    auto *title=new QWidget; auto *titleCol=stack(title,0,2);
    auto *t=ui::text("Diabetic Retinopathy",20,true); t->setAlignment(Qt::AlignRight); titleCol->addWidget(t);
    auto *sub=ui::text("Screening Report",14,true,"#3f4940"); sub->setAlignment(Qt::AlignRight); titleCol->addWidget(sub); head->addWidget(title);
    paperColumn->addWidget(header); paperColumn->addWidget(line());
    auto *body=new QWidget; auto *bodyCol=stack(body,32,28);
    auto *patient=new QWidget; auto *patientCol=stack(patient,0,16);
    patientCol->addWidget(ui::text("Patient information",14,true)); patientCol->addWidget(line());
    auto *meta=new QGridLayout; meta->setContentsMargins(0,0,0,0); meta->setHorizontalSpacing(32); meta->setVerticalSpacing(16);
    int n=0; const int cols=width()>=768?4:2;
    for(const auto &item:report.metadata()) {
        if(item.second.isEmpty()) continue;
        auto *cell=new QWidget; auto *cellCol=stack(cell,0,4);
        cellCol->addWidget(ui::text(item.first.toUpper(),11,true,"#3f4940"));
        auto *value=ui::text(item.second,item.first=="Report ID"?12:14,true); value->setObjectName("ReportMetadata_"+item.first);
        value->setTextInteractionFlags(Qt::TextSelectableByMouse); value->setMinimumWidth(0);
        cellCol->addWidget(value); meta->addWidget(cell,n/cols,n%cols); ++n;
    }
    for(int i=0;i<cols;++i) meta->setColumnStretch(i,1);
    patientCol->addLayout(meta); bodyCol->addWidget(patient);
    auto *analysis=new QWidget; auto *analysisCol=stack(analysis,0,12); analysisCol->addWidget(ui::text("Main analysis",14,true));
    const bool restored=!report.restored.isEmpty();
    auto *images=new ui::ResponsiveGrid(16,true,restored?QList<int>{100,100,100,78}:QList<int>{100,100,78},true);
    auto figure=[&](QString caption,QString path,QString name) {
        auto *w=new QWidget; auto *col=stack(w,0,8); col->addWidget(ui::text(caption.toUpper(),11,true,"#3f4940"));
        auto *image=new ReportImage; image->setObjectName(name);
        image->image=path.isEmpty()?QImage{}:loadImage(path); if(image->image.isNull()) image->status="Image unavailable";
        col->addWidget(image); col->addStretch(); images->append(w);
    };
    figure("Original fundus image",report.original,"ReportOriginal");
    if(restored) figure("NAFNet restored image",report.restored,"ReportRestored");
    figure("AI analysis / lesion overlay",report.overlay,"ReportOverlay");
    auto *grade=panel("ReportGrade","#e5eee3",false); grade->setMinimumHeight(180);
    auto *gradeCol=stack(grade,20,0); gradeCol->addWidget(ui::text("DR GRADE",11,true,"#005227")); gradeCol->addSpacing(16);
    auto *diagnosis=ui::text(reporting::gradeLabel(report.grade),24,true); diagnosis->setObjectName("ReportGradeLabel"); gradeCol->addWidget(diagnosis);
    gradeCol->addSpacing(4); gradeCol->addWidget(ui::text(report.grade.isValid()&&report.grade.toInt()>=0?QString("Grade %1").arg(report.grade.toInt()):"Grade unavailable",14,false,"#3f4940"));
    gradeCol->addStretch(); gradeCol->addSpacing(20); gradeCol->addWidget(line()); gradeCol->addSpacing(16);
    gradeCol->addWidget(ui::text("CONFIDENCE",11,true,"#3f4940")); auto *confidence=ui::text(reporting::confidenceText(report.confidence),30,true,"#005227"); confidence->setObjectName("ReportConfidence"); gradeCol->addWidget(confidence); images->append(grade);
    analysisCol->addWidget(images); bodyCol->addWidget(analysis);
    auto *findings=new ui::ResponsiveGrid(16,true,{135,85},true);
    auto *lesions=panel("ReportLesions"); auto *lesionCol=stack(lesions,20,16); lesionCol->addWidget(ui::text("Lesion detection",14,true));
    auto *lesionGrid=new QGridLayout; lesionGrid->setContentsMargins(0,0,0,0); lesionGrid->setHorizontalSpacing(20); lesionGrid->setVerticalSpacing(16);
    for(int i=0;i<4;++i) { auto *cell=new QWidget; auto *col=stack(cell,0,4); col->addWidget(ui::text(reporting::lesionNames[i],12,false,"#3f4940"));
        auto *status=ui::text(report.lesionStatus(i),14,true,report.lesions[i]==1?"#005227":"#181d18"); status->setObjectName("ReportLesion_"+reporting::lesionCodes[i]); col->addWidget(status); lesionGrid->addWidget(cell,i/2,i%2); }
    lesionCol->addLayout(lesionGrid); findings->append(lesions);
    auto *quality=panel("ReportQuality",report.quality=="Reject"?"#fff1e5":"#e5eee3",false); auto *qualityCol=stack(quality,20,0);
    qualityCol->addWidget(ui::text("Image quality",14,true)); qualityCol->addSpacing(16); qualityCol->addWidget(ui::text(reporting::qualityLabel(report.quality),20,true,report.quality=="Reject"?"#7d5700":"#005227"));
    qualityCol->addSpacing(8); qualityCol->addWidget(ui::text(reporting::qualityMessage(report.quality),12,false,"#3f4940")); qualityCol->addStretch(); findings->append(quality); bodyCol->addWidget(findings);
    auto *recommend=panel("ReportRecommendation","#f7fbf8",false); auto *recCol=stack(recommend,20,8);
    recCol->addWidget(ui::text("Screening recommendation",14,true)); recCol->addWidget(ui::text(reporting::recommendation(report.grade),14,false,"#3f4940")); bodyCol->addWidget(recommend);
    auto *footer=new QWidget; auto *footCol=stack(footer,0,16); footCol->addWidget(line()); auto *footRow=new QHBoxLayout;
    footRow->addWidget(ui::text(reporting::disclaimer,11,false,"#3f4940"),1); auto *page=ui::text("Page 1 of 1",11,true,"#3f4940"); page->setWordWrap(false); footRow->addWidget(page,0,Qt::AlignBottom); footCol->addLayout(footRow); bodyCol->addWidget(footer);
    paperColumn->addWidget(body); content->addWidget(paper);
    auto *actions=new QWidget; auto *actionRow=new ui::FlowLayout(actions,12);
    auto action=[&](QString name,bool primary=false) { auto *b=new QPushButton(name); b->setObjectName(primary?"PrimaryButton":"SecondaryButton"); b->setMinimumHeight(56); b->setCursor(Qt::PointingHandCursor); actionRow->addWidget(b); return b; };
    auto *send=action("Send Report"); connect(send,&QPushButton::clicked,this,[this,report] { QMessageBox::information(this,"Send Report",QString("Export the PDF, then attach it in your email or messaging app.\n\nPatient email: %1\nPatient phone: %2").arg(report.patient.value("email","Not registered").toString(),report.patient.value("phone","Not registered").toString())); });
    auto *save=action(QString("Save %1 Report").arg(activeEye_=="OS"?"Left Eye":"Right Eye"),true); save->setObjectName("ReportSaveEye");
    save->setStyleSheet("QPushButton { background:#005227; color:white; border:1px solid #005227; border-radius:12px; padding:0 24px; font-size:16px; font-weight:700; } QPushButton:hover { background:#006d36; }");
    connect(save,&QPushButton::clicked,this,[this,historic,result] { if(historic) requestHistoryReportDownload(historyReport_.value("sessionId").toString(),activeEye_,result); else requestReport(activeEye_); });
    if(available("OS")&&available("OD")) {
        auto *both=action("Save Both Reports"); both->setObjectName("ReportSaveBoth");
        connect(both,&QPushButton::clicked,this,[this,historic] { const auto destination=QFileDialog::getExistingDirectory(this,"Choose RetinaGram report destination"); if(destination.isEmpty()) return;
            emit bothReportsRequested(historic?historyReport_.value("sessionId").toString():QString{},destination);
        });
    }
    auto *referral=action("Save referral draft"); referral->setObjectName("ReportReferral");
    connect(referral,&QPushButton::clicked,this,[this,report] {
        const auto destination=QFileDialog::getSaveFileName(this,"Save referral draft",QString("RetinaGram_%1_%2_referral.txt").arg(report.runId,report.eye),"Text file (*.txt)"); if(destination.isEmpty()) return;
        QSaveFile file(destination); if(!file.open(QIODevice::WriteOnly)) { setStatus("Referral draft could not be saved."); return; }
        QTextStream out(&file); out<<"RetinaGram - Referral draft\n\n";
        for(const auto &item:report.metadata()) if(!item.second.isEmpty()) out<<item.first<<": "<<item.second<<'\n';
        out<<"\nDR grade: "<<reporting::gradeLabel(report.grade)<<"\nGrade confidence: "<<reporting::confidenceText(report.confidence)<<"\n\n"<<reporting::recommendation(report.grade)<<"\n\n"<<reporting::disclaimer<<'\n'; out.flush();
        setStatus(file.commit()?"Referral draft saved to "+destination:"Referral draft could not be saved.");
    });
    content->addWidget(actions);
    return outer;
}
} // namespace retina
