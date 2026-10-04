#include "ui/MainWindow.h"
#include "ui/UiComponents.h"
#include "app/BatchDiscovery.h"
#include <QCheckBox>
#include <QFileDialog>
#include <QHeaderView>
#include <QRadioButton>
#include <QTableWidget>
#include <QTextEdit>
#include <QVBoxLayout>

namespace retina {
namespace {
QVBoxLayout *column(QWidget *w,int margin=20,int spacing=12) { auto *l=new QVBoxLayout(w); l->setContentsMargins(margin,margin,margin,margin); l->setSpacing(spacing); return l; }
QFrame *card() { auto *w=new QFrame; w->setObjectName("Card"); return w; }
QPushButton *action(QString value,bool primary=false) {
    auto *w=new QPushButton(value); w->setObjectName(primary?"PrimaryButton":"SecondaryButton"); w->setMinimumHeight(44); w->setIconSize(QSize(20,20)); w->setCursor(Qt::PointingHandCursor);
    w->setStyleSheet(QString("QPushButton { background:%1; color:%2; border:1px solid #005227; border-radius:12px; padding:8px 16px; font-size:14px; font-weight:bold; } QPushButton:disabled { background:#dfe4dc; color:#3f4940; border-color:#dfe4dc; }").arg(primary?"#005227":"white",primary?"white":"#005227")); return w;
}
class Workflow : public QFrame {
public:
    QList<QWidget*> steps;
    Workflow() { setObjectName("BatchWorkflow"); setAccessibleName("Batch workflow"); setStyleSheet("QFrame#BatchWorkflow { background:white; border:1px solid #becabd; border-radius:16px; }"); }
protected:
    void resizeEvent(QResizeEvent *e) override {
        QFrame::resizeEvent(e); const bool desktop=window()->width()>=1024;
        for(int i=0;i<steps.size();++i) steps[i]->setStyleSheet(QString("QWidget#BatchStep { background:transparent; border:0; %1 }").arg(i?desktop?"border-left:1px solid #becabd;":"border-top:1px solid #becabd;":""));
    }
};
}
void MainWindow::discoverBatch(QString directory) {
    batchInput_=directory; batchSnapshot_=discoverBatchInput(directory); batchSnapshot_["gpu_capacity"]=batchCapacity_;
    batchSelections_.clear(); batchReviewed_=false; showBatchPatients_=false; batchSkipUnresolved_=true; batchStatus_.clear(); rebuildPage(Batch);
}
void MainWindow::setBatchCapacity(QVariantMap capacity) { batchCapacity_=capacity; if(!batchSnapshot_.isEmpty()) batchSnapshot_["gpu_capacity"]=capacity; rebuildPage(Batch); }
void MainWindow::setBatchSnapshot(QVariantMap event) {
    if(event.contains("patients")) batchSnapshot_=event;
    else {
        for(auto it=event.cbegin();it!=event.cend();++it) if(it.key()!="counts") batchSnapshot_[it.key()]=it.value();
        auto counts=batchSnapshot_.value("counts").toMap(); auto updates=event.value("counts").toMap(); for(auto it=updates.cbegin();it!=updates.cend();++it) counts[it.key()]=it.value(); batchSnapshot_["counts"]=counts;
        QString path=event.value("source_path").toString();
        if(!path.isEmpty()) {
            auto patients=batchSnapshot_.value("patients").toList();
            for(auto &v:patients) { auto p=v.toMap(); auto candidates=p.value("eye_candidates").toMap(); auto eyes=p.value("eyes").toMap();
                for(const auto &eye:QStringList{"OS","OD"}) for(const auto &candidate:candidates.value(eye).toList()) if(candidate.toMap().value("source_path")==path) {
                    eyes[eye]=QVariantMap{{"status",event.value("eye_status","Processing")},{"stage",event.value("stage_label")}};
                    p["status"]=event.value("eye_status","Processing");
                }
                p["eyes"]=eyes; v=p;
            }
            batchSnapshot_["patients"]=patients;
        }
    }
    rebuildPage(Batch);
}
QWidget *MainWindow::buildBatch() {
    QVBoxLayout *content=nullptr; auto *outer=buildPageFrame(QString(),QString(),&content);
    // Batch has its own 1440px shell rather than the general 1280px shell.
    auto *inner=content->parentWidget(); inner->setMaximumWidth(1440); outer->layout()->setContentsMargins(0,0,0,0); const int padding=width()>=1024?32:width()>=768?24:16; content->setContentsMargins(padding,32,padding,96); content->setSpacing(24);
    const bool snapshot=!batchSnapshot_.isEmpty(); const QString state=batchSnapshot_.value("state").toString(); const bool review=state=="Review";
    const auto counts=batchSnapshot_.value("counts").toMap(); const auto capacity=batchSnapshot_.value("gpu_capacity",batchCapacity_).toMap();
    const auto patients=batchSnapshot_.value("patients").toList(); const auto plan=batchImagePlan(batchSnapshot_,batchSelections_);
    int readyPatients=0; for(const auto &v:patients) if(batchPatientReady(v.toMap(),batchSelections_)) ++readyPatients;
    const bool available=capacity.value("available").toBool(); const int maximum=capacity.value("max_batch_size").toInt(); const bool tooLarge=available&&plan.size()>maximum;
    auto *header=new QWidget; auto *hl=new QVBoxLayout(header); hl->setContentsMargins(0,0,0,24); hl->setSpacing(8);
    auto *heading=new QHBoxLayout; heading->addWidget(ui::text("Batch Analysis",36,true),1); if(snapshot) heading->addWidget(ui::pill(state,"#f0f5ed","#005227")); hl->addLayout(heading);
    hl->addWidget(ui::text("Process multiple retinal images and generate patient reports automatically.",16,false,"#3f4940")); header->setStyleSheet("QWidget { border-bottom:1px solid #becabd; } QLabel { border:0; }"); content->addWidget(header);
    if(!batchStatus_.isEmpty()&&batchStatus_.startsWith("Batch failed")) content->addWidget(ui::text(batchStatus_,14,true,"#ba1a1a"));
    auto *workflow=new Workflow; auto *wl=column(workflow,0,0); auto *grid=new ui::ResponsiveGrid(0,true,{},true); wl->addWidget(grid);
    const QStringList titles{"Select Input Folder","Review & Confirm","Start Batch Analysis"}; QList<QVBoxLayout*> columns;
    for(int i=0;i<3;++i) {
        auto *step=new QWidget; step->setObjectName("BatchStep"); workflow->steps<<step; auto *cl=column(step,20,12); auto *row=new QHBoxLayout; row->setSpacing(12);
        auto *number=ui::text(QString::number(i+1),14,true,"white"); number->setAlignment(Qt::AlignCenter); number->setFixedSize(32,32); number->setStyleSheet("background:#005227; color:white; border:0; border-radius:8px;"); row->addWidget(number); row->addWidget(ui::text(titles[i],18,true),1); cl->addLayout(row); columns<<cl; grid->append(step);
    }
    auto *description=ui::text("Structured patient folders and ID_Name_OS/OD filenames are supported.",14,false,"#3f4940"); description->setMinimumHeight(40); columns[0]->addWidget(description);
    auto *input=action("Choose Folder"); input->setAccessibleName("Choose Folder"); input->setEnabled(!busy_&&(!snapshot||review));
    input->setIcon(ui::buttonIcon("folder_open"));
    connect(input,&QPushButton::clicked,this,[this] { auto chosen=QFileDialog::getExistingDirectory(this,"Choose RetinaGram batch input folder"); if(!chosen.isEmpty()) discoverBatch(chosen); }); columns[0]->addWidget(input,0,Qt::AlignLeft);
    if(snapshot) columns[0]->addWidget(ui::text(batchInput_,12,false,"#3f4940")); columns[0]->addStretch();
    if(snapshot) {
        auto *metrics=new QGridLayout; metrics->setHorizontalSpacing(16); metrics->setVerticalSpacing(6);
        const QStringList keys{"total_patients","total_images","ready","needs_review","invalid","mode","paired_patients","single_eye_patients"};
        const QStringList names{"patients","images","ready","need review","invalid","mode","paired","single-eye"};
        for(int i=0;i<keys.size();++i) metrics->addWidget(ui::text((keys[i]=="mode"?batchSnapshot_.value("mode").toString():counts.value(keys[i]).toString())+" "+names[i],14,i==2,i==2?"#005227":"#3f4940"),i/2,i%2); columns[1]->addLayout(metrics);
    } else columns[1]->addWidget(ui::text("Choose a folder to detect patients and eye images.",14,false,"#3f4940"));
    auto *show=new QPushButton(showBatchPatients_?"Hide Patient List":"View Patient List"); show->setEnabled(snapshot); show->setMinimumHeight(44); show->setStyleSheet("QPushButton { color:#005227; font-weight:bold; background:transparent; border:0; text-decoration:underline; } QPushButton:disabled { color:#8b948b; }");
    connect(show,&QPushButton::clicked,this,[this] { showBatchPatients_=!showBatchPatients_; rebuildPage(Batch); }); columns[1]->addWidget(show,0,Qt::AlignLeft);
    if(review) { auto *checked=new QCheckBox("I reviewed the detected patients and eye assignments."); checked->setChecked(batchReviewed_); columns[1]->addWidget(checked); connect(checked,&QCheckBox::toggled,this,[this](bool v) { batchReviewed_=v; rebuildPage(Batch); }); } columns[1]->addStretch();
    auto *output=action("Choose Output Folder"); output->setEnabled(review&&!busy_); columns[2]->addWidget(output,0,Qt::AlignLeft); connect(output,&QPushButton::clicked,this,[this] { auto chosen=QFileDialog::getExistingDirectory(this,"Choose RetinaGram batch output folder"); if(!chosen.isEmpty()) { batchOutput_=chosen; rebuildPage(Batch); } });
    output->setIcon(ui::buttonIcon("drive_folder_upload"));
    columns[2]->addWidget(ui::text(batchOutput_.isEmpty()?"No output folder selected":batchOutput_,12,false,"#3f4940"));
    auto *folders=new QCheckBox("Create patient-wise folders"); folders->setChecked(batchPatientFolders_); folders->setEnabled(review); columns[2]->addWidget(folders); connect(folders,&QCheckBox::toggled,this,[this](bool v) { batchPatientFolders_=v; });
    const int unresolved=counts.value("needs_review").toInt()+counts.value("invalid").toInt();
    if(review&&unresolved) {
        auto *skip=new QCheckBox("Skip unresolved entries"); skip->setChecked(batchSkipUnresolved_); columns[2]->addWidget(skip); columns[2]->addWidget(ui::text("READY patients and resolved duplicate selections will still run.",12,false,"#3f4940"));
        connect(skip,&QCheckBox::toggled,this,[this](bool v) { batchSkipUnresolved_=v; rebuildPage(Batch); });
    }
    auto *start=action("Start Batch Analysis",true); start->setEnabled(review&&available&&!tooLarge&&readyPatients>0&&!batchOutput_.isEmpty()&&batchReviewed_&&!busy_&&(batchSkipUnresolved_||readyPatients==patients.size()&&counts.value("invalid").toInt()==0)); columns[2]->addWidget(start);
    start->setIcon(ui::buttonIcon("play_arrow","white"));
    connect(start,&QPushButton::clicked,this,[this,plan] { if(receivers(SIGNAL(batchPlanRequested(QVariantList,QString,bool)))==0) { setBatchStatus("Batch failed: native batch controller unavailable."); return; } batchSnapshot_["state"]="Processing"; emit batchPlanRequested(plan,batchOutput_,batchPatientFolders_); rebuildPage(Batch); });
    if(review) {
        auto *gpu=card(); gpu->setObjectName("GpuCapacity"); gpu->setStyleSheet(QString("QFrame#GpuCapacity { background:%1; border:0; border-radius:8px; }").arg(!available||tooLarge?"#ffdad6":"#f0f5ed")); auto *gl=column(gpu,12,4);
        if(available) { gl->addWidget(ui::text(capacity.value("name").toString(),12,true)); gl->addWidget(ui::text(QString("VRAM: %1 GB · Maximum batch: %2 images · Selected: %3").arg(capacity.value("vram_mb").toDouble()/1024,0,'f',1).arg(maximum).arg(plan.size()),12)); if(tooLarge) gl->addWidget(ui::text("Batch too large for this GPU. Reduce the batch size and try again.",12,true,"#93000a")); }
        else gl->addWidget(ui::text("GPU batch analysis is unavailable because CUDA VRAM could not be detected.",12,true,"#93000a")); columns[2]->addWidget(gpu);
        columns[2]->addWidget(ui::text(QString("%1 patients · %2 images ready").arg(readyPatients).arg(plan.size()),12,false,"#3f4940"));
    }
    content->addWidget(workflow);
    if(snapshot&&!review) {
        auto *progress=card(); progress->setObjectName("BatchProgress"); progress->setStyleSheet("QFrame#BatchProgress { background:#f0f5ed; border:0; border-radius:16px; }"); auto *pl=column(progress);
        auto *row=new QHBoxLayout; auto *caption=new QWidget; auto *cl=column(caption,0,4); cl->addWidget(ui::text("Batch Progress",20,true)); cl->addWidget(ui::text("The bar reflects the current backend pipeline stage.",12)); row->addWidget(caption,1);
        for(const auto &verb:QStringList{"pause","resume","cancel"}) {
            const bool allowed=verb=="pause"?state=="Processing":verb=="resume"?state=="Paused":QStringList{"Processing","Pausing","Paused"}.contains(state);
            if(!allowed) continue; auto *b=action(verb=="pause"?"Pause Batch":verb=="resume"?"Resume Batch":"Cancel Batch",verb=="resume"); row->addWidget(b); connect(b,&QPushButton::clicked,this,[this,verb] { emit batchControlRequested(verb); });
        } pl->addLayout(row);
        pl->addWidget(ui::text(batchSnapshot_.value("stage_label","Preparing batch").toString(),14,true,"#005227")); pl->addWidget(ui::meter(batchSnapshot_.value("progress_percent").toDouble()/100,12));
        auto *metrics=new ui::ResponsiveGrid(0,true); const QStringList keys{"total_patients","total_images","completed","processing","recapture_required","failed"}; const QStringList names{"Total Patients","Total Images","Completed","Processing","Recapture Required","Failed"};
        for(int i=0;i<keys.size();++i) { auto *m=card(); auto *ml=column(m,16,3); ml->addWidget(ui::text(QString::number(counts.value(keys[i]).toInt()),24,true,"#005227")); ml->addWidget(ui::text(names[i],12,true,"#3f4940")); metrics->append(m); } pl->addWidget(metrics); content->addWidget(progress);
    }
    if(snapshot&&(showBatchPatients_||!review)) {
        auto *detected=card(); detected->setObjectName("DetectedPatients"); detected->setStyleSheet("QFrame#DetectedPatients { background:white; border:1px solid #becabd; border-radius:16px; }"); auto *dl=column(detected,20,16);
        auto *row=new QHBoxLayout; auto *title=new QWidget; auto *tl=column(title,0,4); tl->addWidget(ui::text("Detected Patients",20,true)); tl->addWidget(ui::text("Independent eye status is preserved for OS-only, OD-only, and paired patients.",12)); row->addWidget(title,1); row->addWidget(ui::text(QString::number(patients.size()),14,true,"#005227")); dl->addLayout(row);
        auto *table=new QTableWidget(int(patients.size()),7); table->setObjectName("BatchPatientTable"); table->setHorizontalHeaderLabels({"#","Patient ID","Name","OS","OD","Status","Stage"}); table->setShowGrid(false); table->verticalHeader()->hide(); table->setEditTriggers(QAbstractItemView::NoEditTriggers); table->horizontalHeader()->setSectionResizeMode(QHeaderView::ResizeToContents); table->horizontalHeader()->setSectionResizeMode(2,QHeaderView::Stretch); table->horizontalHeader()->setSectionResizeMode(6,QHeaderView::Stretch);
        for(int i=0;i<patients.size();++i) {
            auto p=patients[i].toMap(); QString id=p.value("patient_id").toString(); bool resolved=batchPatientReady(p,batchSelections_); QString status=review?(resolved?(p.value("discovery_status")=="READY"?"READY":"Ready after selection"):p.value("discovery_status").toString()):p.value("status").toString();
            table->setItem(i,0,new QTableWidgetItem(QString::number(i+1))); table->setItem(i,1,new QTableWidgetItem(id)); table->setItem(i,2,new QTableWidgetItem(p.value("name","Unknown").toString()));
            int rowHeight=60;
            for(int eyeIndex=0;eyeIndex<2;++eyeIndex) {
                QString eye=eyeIndex?"OD":"OS"; auto candidates=p.value("eye_candidates").toMap().value(eye).toList(); auto *cell=new QWidget; auto *cc=column(cell,6,4);
                if(candidates.isEmpty()) cc->addWidget(ui::text("—",12));
                else if(candidates.size()==1) { auto path=candidates.first().toMap().value("source_path").toString(); auto *f=ui::text(candidates.first().toMap().value("source_name").toString(),12,true,"#005227"); f->setToolTip(path); cc->addWidget(f); }
                else {
                    cc->addWidget(ui::text(QString("Select one of %1").arg(candidates.size()),12,true,"#7e2838")); auto *group=new QButtonGroup(cell);
                    for(const auto &candidate:candidates) { auto c=candidate.toMap(); auto path=c.value("source_path").toString(); auto *radio=new QRadioButton(c.value("source_name").toString()); radio->setToolTip(path); radio->setChecked(batchSelections_.value(id+"/"+eye)==path); radio->setEnabled(review); group->addButton(radio); cc->addWidget(radio); connect(radio,&QRadioButton::clicked,this,[this,id,eye,path] { batchSelections_[id+"/"+eye]=path; rebuildPage(Batch); }); }
                    rowHeight=qMax(rowHeight,int(candidates.size())*30+45);
                } table->setCellWidget(i,3+eyeIndex,cell);
            }
            auto *statusCell=new QWidget; auto *sc=column(statusCell,6,4); status.replace('_',' '); sc->addWidget(ui::pill(status,"#f0f5ed",resolved?"#005227":"#7e2838")); for(const auto &issue:p.value("issues").toStringList()) sc->addWidget(ui::text(issue,11,false,"#7e2838")); table->setCellWidget(i,5,statusCell);
            QStringList stages; const auto eyes=p.value("eyes").toMap(); for(const auto &eye:QStringList{"OS","OD"}) if(eyes.contains(eye)) { auto e=eyes.value(eye).toMap(); stages<<eye+": "+e.value("status").toString()+" · "+e.value("stage").toString(); }
            table->setItem(i,6,new QTableWidgetItem(review?status:stages.join('\n'))); table->setRowHeight(i,rowHeight);
        } table->setMinimumHeight(qMin(480,80+int(patients.size())*75)); dl->addWidget(table);
        if(patients.isEmpty()) dl->addWidget(ui::text("No valid patients were detected. Check the folder names and patient.json fields.",14));
        auto invalid=batchSnapshot_.value("invalid_items").toList();
        if(!invalid.isEmpty()) { dl->addWidget(ui::text("Rejected items and reasons",14,true,"#ba1a1a")); for(const auto &v:invalid) { auto item=v.toMap(); dl->addWidget(ui::text(item.value("name").toString()+"\n"+item.value("path").toString()+"\nReason: "+item.value("reason").toString(),12,false,"#93000a")); } }
        if(review&&!batchSnapshot_.value("logs").toList().isEmpty()) {
            auto *toggle=new QPushButton("Discovery log"); toggle->setCheckable(true); toggle->setStyleSheet("color:#005227; border:0; font-weight:bold;"); dl->addWidget(toggle,0,Qt::AlignLeft);
            auto *log=new QTextEdit; log->setReadOnly(true); log->setMaximumHeight(192); log->setStyleSheet("background:#2d322d; color:#eef2ea; border:0; border-radius:12px; font-family:Consolas; font-size:12px;"); QStringList lines; for(const auto &v:batchSnapshot_.value("logs").toList()) { auto entry=v.toMap(); lines<<entry.value("time").toString()+" "+entry.value("message").toString(); } log->setPlainText(lines.join('\n')); log->hide(); connect(toggle,&QPushButton::toggled,log,&QWidget::setVisible); dl->addWidget(log);
        }
        content->addWidget(detected);
    }
    return outer;
}
}
