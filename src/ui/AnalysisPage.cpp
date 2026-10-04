#include "ui/MainWindow.h"
#include "ui/UiComponents.h"
#include "image/ImageDecoder.h"
#include <QCheckBox>
#include <QComboBox>
#include <QFileInfo>
#include <QtMath>
#include <QScrollBar>
#include <QScrollArea>
#include <QSlider>
#include <QVBoxLayout>
#include <algorithm>

namespace retina {
namespace {
QString name(QString code) {
    return QMap<QString,QString>{{"MA","Microaneurysms"},{"HE","Hemorrhages"},{"EX","Hard Exudates"},{"SE","Soft Exudates"}}.value(code,code);
}
QColor color(QString code) {
    return QColor(QMap<QString,QString>{{"MA","#ff2d2d"},{"HE","#ff7e22"},{"EX","#ffe020"},{"SE","#23d2ff"}}.value(code,"#ffffff"));
}
QString code(const QVariantMap &r) { return r.value("class",r.value("code")).toString(); }
QRectF box(const QVariantMap &r) { return {r.value("x_min",r.value("x")).toDouble(),r.value("y_min",r.value("y")).toDouble(),r.value("width",r.value("w")).toDouble(),r.value("height",r.value("h")).toDouble()}; }
QString pct(QVariant v) { return v.isValid() && !v.isNull()?QString::number(v.toDouble()*100,'f',1)+"%":"Unavailable"; }
QFrame *panel(QString style={}) {
    auto *w=new QFrame; w->setObjectName("AnalysisPanel");
    w->setStyleSheet("QFrame#AnalysisPanel { background:white; border:1px solid #becabd; border-radius:12px; "+style+" }"); return w;
}
QVBoxLayout *col(QWidget *w,int padding=0,int gap=16) {
    auto *l=new QVBoxLayout(w); l->setContentsMargins(padding,padding,padding,padding); l->setSpacing(gap); return l;
}
QWidget *divider() { auto *w=new QFrame; w->setFixedHeight(1); w->setStyleSheet("background:#becabd; border:0;"); return w; }
QWidget *counts(const QVariantMap &r,int displayed,QString selection) {
    auto *w=new QWidget; w->setObjectName("RegionCounts"); auto *l=col(w,0,4);
    l->addWidget(ui::text(QString("%1 regions displayed · %2").arg(displayed).arg(selection),14,true));
    const bool assessed=r.contains("regions");
    l->addWidget(ui::text(assessed?QString("%1 retained after post-processing").arg(r.value("regions").toList().size()):"Not assessed",12,false,"#3f4940"));
    l->addWidget(ui::text(r.contains("raw_regions")?QString("%1 raw connected regions before size, proximity and region-score rules.").arg(r.value("raw_regions").toList().size()):assessed?"Raw component count is unavailable for this older run. Analyze again for post-processing.":"Run analysis to generate region counts.",12,false,"#3f4940"));
    l->addWidget(ui::text("Model predictions require clinician interpretation.",12,false,"#3f4940")); return w;
}
class RegionCard : public QFrame {
public:
    std::function<void()> selected;
    RegionCard() { setCursor(Qt::PointingHandCursor); setFocusPolicy(Qt::StrongFocus); }
protected:
    void mousePressEvent(QMouseEvent *e) override { if(e->button()==Qt::LeftButton && selected) selected(); }
    void keyPressEvent(QKeyEvent *e) override { if((e->key()==Qt::Key_Return || e->key()==Qt::Key_Space) && selected) selected(); else QFrame::keyPressEvent(e); }
};
}

QString MainWindow::regionKey(const QVariantMap &r) const {
    return QString("%1-%2%3-%4").arg(activeEye_,showRawRegions_?"raw-":"",code(r),r.value("region_id").toString());
}
QStringList MainWindow::availableLesionClasses(const QVariantMap &r) const {
    QStringList classes;
    const auto probabilities=r.value("lesion_probability_paths").toMap();
    const auto masks=r.value("lesion_mask_paths").toMap();
    const auto reported=r.value("lesion_counts").toMap();
    for(const QString &c:{QString("MA"),QString("HE"),QString("EX"),QString("SE")})
        if(probabilities.contains(c)||masks.contains(c)||reported.contains(c)) classes.append(c);
    return classes;
}
QList<QVariantMap> MainWindow::displayedRegions(const QVariantMap &r) const {
    QList<QVariantMap> rows;
    // Raw output deliberately bypasses both ranking limits and class filtering.
    const auto source=r.value(showRawRegions_?"raw_regions":"regions").toList();
    for(const auto &v:source) if(showRawRegions_||regionClass_=="all"||code(v.toMap())==regionClass_) rows.append(v.toMap());
    if(showRawRegions_) return rows;
    std::stable_sort(rows.begin(),rows.end(),[](const auto &a,const auto &b) {
        double x=a.value("mean_probability").toDouble(),y=b.value("mean_probability").toDouble();
        return x!=y?x>y:(code(a)+a.value("region_id").toString())<(code(b)+b.value("region_id").toString());
    });
    if(topK_>0 && rows.size()>topK_) rows=rows.mid(0,topK_);
    return rows;
}
QImage MainWindow::visualizationImage(const QString &eye,View view,bool compact) const {
    const auto r=resultFor(eye);
    QImage image=loadImage(imagePath(eye));
    if(image.isNull()) { image=QImage(640,480,QImage::Format_ARGB32_Premultiplied); image.fill(Qt::black); return image; }
    // Display scaling only. All region coordinates continue to refer to original pixels.
    if(image.width()>1600||image.height()>1600) image=image.scaled(1600,1600,Qt::KeepAspectRatio,Qt::SmoothTransformation);
    image=image.convertToFormat(QImage::Format_ARGB32_Premultiplied);
    const QString mode=view==GradeView?gradeMode_:view==AttentionView?attentionMode_:annotationMode_;
    if(view==AnnotationView && mode!="Original") {
        if(mode=="Mask") image.fill(Qt::black);
        const auto paths=r.value("lesion_mask_paths").toMap();
        QPainter p(&image); p.setOpacity(mode=="Overlay"?opacity_/100.0:1.0);
        for(const auto &c:enabledMaskClasses_) {
            QImage mask(paths.value(c).toString()); if(mask.isNull()) continue;
            mask=mask.scaled(image.size(),Qt::IgnoreAspectRatio,Qt::FastTransformation).convertToFormat(QImage::Format_Grayscale8);
            QImage layer(image.size(),QImage::Format_ARGB32_Premultiplied); layer.fill(Qt::transparent);
            const QRgb ink=color(c).rgba();
            for(int y=0;y<mask.height();++y) { auto *out=reinterpret_cast<QRgb*>(layer.scanLine(y)); auto *in=mask.constScanLine(y); for(int x=0;x<mask.width();++x) if(in[x]) out[x]=ink; }
            p.drawImage(0,0,layer);
        }
    } else if((view==GradeView||view==AttentionView) && mode!="Original") {
        const QString path=view==GradeView?r.value("gradcam_path").toString():
            r.value(attentionType_=="Probability"?"lesion_probability_paths":"lesion_gradcam_paths").toMap().value(lesionClass_).toString();
        // Never substitute an aggregate map or lesion boxes for a missing class layer.
        QImage layer(path);
        if(mode!="Overlay") image.fill(Qt::black);
        if(!layer.isNull()) { QPainter p(&image); p.setOpacity(mode=="Overlay"?opacity_/100.0:1.0); p.drawImage(image.rect(),layer); }
    }
    if(view==DetectionView) {
        QPainter p(&image); p.setRenderHint(QPainter::Antialiasing);
        const double w=r.value("image_width",image.width()).toDouble(),h=r.value("image_height",image.height()).toDouble();
        const double sx=image.width()/qMax(1.0,w),sy=image.height()/qMax(1.0,h);
        QFont f("Atkinson Hyperlegible Next"); f.setPixelSize(qMax(12,image.width()/(compact?28:42))); p.setFont(f);
        if(showCoordinates_) {
            for(int i=0;i<5;++i) {
                int x=int((w-1)*i/4),y=int((h-1)*i/4);
                p.setPen(QPen(QColor(155,246,177,140),1)); p.drawLine(QPointF(x*sx,0),QPointF(x*sx,image.height())); p.drawLine(QPointF(0,y*sy),QPointF(image.width(),y*sy));
                p.setPen(Qt::white); p.drawText(QPointF(qMin(x*sx+5,double(image.width()-90)),f.pixelSize()+3),QString("X %1").arg(x));
                if(i) p.drawText(QPointF(5,qMin(y*sy-5,double(image.height()-5))),QString("Y %1").arg(y));
            }
        }
        for(const auto &region:displayedRegions(r)) {
            const bool selected=!compact && regionKey(region)==selectedRegion_;
            auto bounds=box(region); QRectF scaled(bounds.x()*sx,bounds.y()*sy,bounds.width()*sx,bounds.height()*sy);
            p.setPen(QPen(selected?Qt::white:color(code(region)),selected?5:2));
            p.setBrush(selected?QColor(255,255,255,50):QColor(Qt::transparent)); p.drawRect(scaled);
            if(selected) {
                if(showCoordinates_) { p.setBrush(Qt::white); p.drawEllipse(QPointF(region.value("center_x").toDouble()*sx,region.value("center_y").toDouble()*sy),4,4); }
                p.setPen(Qt::white); p.setBrush(Qt::NoBrush);
                p.drawText(QPointF(qMin(scaled.x(),double(image.width()-250)),qMax(double(f.pixelSize()+8),scaled.y()-8)),code(region)+" · "+pct(region.value("mean_probability"))+" mean probability");
            }
        }
        if(showCoordinates_ && hasCoordinateCursor_) {
            p.setPen(QPen(Qt::white,1)); QPointF pt(coordinateCursor_.x()*sx,coordinateCursor_.y()*sy);
            p.drawLine(pt-QPointF(12,0),pt+QPointF(12,0)); p.drawLine(pt-QPointF(0,12),pt+QPointF(0,12));
        }
    }
    return image;
}

QWidget *MainWindow::buildVisualization(QString eye,View view,bool compact) {
    auto *w=new QWidget; auto *l=col(w,0,12);
    auto *stage=new ui::ImageStage; stage->setAccessibleName(eye+" retinal visualization");
    stage->image=visualizationImage(eye,view,compact);
    const auto r=resultFor(eye); const QString mode=view==GradeView?gradeMode_:view==AttentionView?attentionMode_:annotationMode_;
    if(r.isEmpty()) stage->status="No analysis for this eye. Capture a scan and run analysis.";
    else if((view==GradeView||view==AttentionView) && mode!="Original") {
        QString layer=view==GradeView?r.value("gradcam_path").toString():r.value(attentionType_=="Probability"?"lesion_probability_paths":"lesion_gradcam_paths").toMap().value(lesionClass_).toString();
        if(layer.isEmpty()) stage->status=view==GradeView?"Grade Grad-CAM is unavailable for this run.":attentionType_=="Probability"?"Segmentation probability map is unavailable for this class or run.":"Lesion Grad-CAM is unavailable for this class or run. Optional generation uses RETINAGRAM_ENABLE_LESION_CAM=1.";
        else if(!QFileInfo::exists(layer)) stage->status="An image layer could not be loaded. The run may no longer be available; analyze this eye again.";
    } else if(view==AnnotationView && mode!="Original" && r.value("lesion_mask_paths").toMap().isEmpty()) stage->status="Mask layers are unavailable for this run. Analyze this eye again.";
    l->addWidget(stage);
    if(view==DetectionView && !compact) {
        stage->pointSelected=[this,r](QPointF point) {
            QPointF original(point.x()*r.value("image_width").toDouble(),point.y()*r.value("image_height").toDouble());
            for(const auto &region:displayedRegions(r)) if(box(region).contains(original)) { QString id=regionKey(region); selectedRegion_=selectedRegion_==id?QString():id; rebuildPage(Analysis); return; }
        };
        stage->pointMoved=[this,stage,r,eye,view,compact](QPointF point) {
            if(!showCoordinates_) return;
            coordinateCursor_=QPointF(qFloor(point.x()*r.value("image_width").toDouble()),qFloor(point.y()*r.value("image_height").toDouble()));
            hasCoordinateCursor_=true; stage->image=visualizationImage(eye,view,compact); stage->update();
            if(auto *coords=stage->parentWidget()->findChild<QLabel*>("CursorCoordinates")) coords->setText(QString("Cursor X %1, Y %2 px").arg(int(coordinateCursor_.x())).arg(int(coordinateCursor_.y())));
        };
    }
    QString note=view==GradeView?"Grade Grad-CAM: relative influence on the predicted DR class; not a probability map.":
        view==AttentionView?(attentionType_=="Probability"?"Segmentation probability: independent sigmoid probability at each pixel. This is not Grad-CAM.":"Segmentation Grad-CAM: mean class-channel logit over the predicted mask pixels."):
        view==DetectionView?(showRawRegions_?"Raw model output before region processing. ":"Regions retained after post-processing. ")+QString("Boxes are derived from segmentation. Scores are mean pixel probabilities, not clinical confidence or severity."):
        "Predicted segmentation masks, not manual or ground-truth annotations. Layers use original image pixels.";
    l->addWidget(ui::text(note,12,false,"#3f4940"));
    if(view==GradeView||view==AttentionView) {
        auto *row=new QHBoxLayout; const bool probability=view==AttentionView && attentionType_=="Probability";
        row->addWidget(ui::text(probability?"0 probability":"Low attention",12));
        auto *gradient=new QFrame; gradient->setFixedHeight(8); gradient->setMinimumWidth(80);
        gradient->setStyleSheet("border:1px solid #becabd; border-radius:4px; background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0000ff,stop:0.25 #00ffff,stop:0.5 #00ff00,stop:0.75 #ffff00,stop:1 #ff0000);"); row->addWidget(gradient,1);
        row->addWidget(ui::text(probability?"1 probability":"High attention",12)); l->addLayout(row);
    }
    if(view==AnnotationView) {
        auto *legend=new QWidget; auto *flow=new ui::FlowLayout(legend);
        for(const auto &c:availableLesionClasses(r)) { auto *v=new QWidget; auto *row=new QHBoxLayout(v); row->setContentsMargins(0,0,0,0); auto *swatch=new QFrame; swatch->setFixedSize(12,12); swatch->setStyleSheet("background:"+color(c).name()+"; border:1px solid #6f7a6f; border-radius:2px;"); row->addWidget(swatch); row->addWidget(ui::text(c,12)); flow->addWidget(v); }
        flow->addWidget(ui::text(r.contains("lesion_mask_paths")?"Mask threshold 0.5 · full mask, unaffected by display-region filters":"Mask threshold unavailable · legacy mask; analyze again for full raw output",12,false,"#3f4940"));
        if(enabledMaskClasses_.isEmpty()) flow->addWidget(ui::text("No mask classes selected.",12)); l->addWidget(legend);
    }
    if(view==DetectionView && !compact) {
        auto *detail=panel("background:#f0f5ed;"); detail->setAccessibleName("Region details"); auto *dl=col(detail,16,6);
        QVariantMap selected; for(const auto &region:displayedRegions(r)) if(regionKey(region)==selectedRegion_) selected=region;
        dl->addWidget(ui::text(selected.isEmpty()?"Select a predicted region":name(code(selected))+" · "+eye,14,true));
        dl->addWidget(ui::text(QString("Image resolution: %1 × %2 px · origin at top left").arg(r.value("image_width").toString(),r.value("image_height").toString()),12));
        if(showCoordinates_) { auto *cursor=ui::text("Move across the image to inspect original pixel coordinates.",12); cursor->setObjectName("CursorCoordinates"); dl->addWidget(cursor); }
        if(!selected.isEmpty()) {
            auto b=box(selected); dl->addWidget(ui::text(QString("[X: %1, Y: %2, W: %3, H: %4] · Center [%5, %6] · Area %7 px").arg(b.x()).arg(b.y()).arg(b.width()).arg(b.height()).arg(selected.value("center_x").toString(),selected.value("center_y").toString(),selected.value("area_pixels").toString()),12));
            dl->addWidget(ui::text("Mean pixel probability "+pct(selected.value("mean_probability"))+" · Maximum "+pct(selected.value("max_probability")),12));
            auto *clear=new QPushButton("Clear selection"); clear->setStyleSheet("background:transparent; color:#005227; border:0; font-weight:bold; text-decoration:underline;"); connect(clear,&QPushButton::clicked,this,[this] { selectedRegion_.clear(); rebuildPage(Analysis); }); dl->addWidget(clear,0,Qt::AlignLeft);
        }
        if(showRawRegions_&&!r.contains("raw_regions")) dl->addWidget(ui::text("Raw model regions are unavailable for this run. Analyze this eye again.",12));
        l->addWidget(detail);
    }
    return w;
}

QWidget *MainWindow::buildAnalysis() {
    QVBoxLayout *content=nullptr;
    auto *outer=buildPageFrame(QString(),QString(),&content);
    if(currentPatient_<0) { content->addWidget(buildEmptyState("analytics","No patient selected","Register a patient on Capture to begin.")); return outer; }
    auto *heading=new QHBoxLayout; auto *back=new QPushButton; back->setAccessibleName("Back to Capture"); back->setFixedSize(36,36);
    back->setStyleSheet("background:transparent; border:0; border-radius:18px;"); back->setIcon(ui::buttonIcon("arrow_back")); back->setIconSize(QSize(24,24)); connect(back,&QPushButton::clicked,this,[this] { navigate(Capture); }); heading->addWidget(back);
    auto *title=new QWidget; auto *tl=col(title,0,4); tl->addWidget(ui::text("Analysis Results",30,true));
    const auto patient=patients_[currentPatient_].details;
    tl->addWidget(ui::text(QString("Patient ID: #%1 · %2 · %3").arg(patient.value("patientIdNumber").toString(),patient.value("name").toString(),eyeName(activeEye_)),14,false,"#3f4940")); heading->addWidget(title,1);
    heading->addWidget(ui::segmented("Analysis eye",{"OS (Left)","OD (Right)"},activeEye_=="OS"?"OS (Left)":"OD (Right)",this,[this](QString value) { activeEye_=value.startsWith("OS")?"OS":"OD"; selectedRegion_.clear(); hasCoordinateCursor_=false; rebuildPage(Analysis); }));
    content->addLayout(heading); content->addSpacing(8); content->addWidget(divider()); content->addSpacing(8);
    const auto r=resultFor(activeEye_); const auto rows=displayedRegions(r);
    QStringList classes=availableLesionClasses(r); if(!classes.isEmpty()&&!classes.contains(lesionClass_)) lesionClass_=classes.first();
    auto *quality=panel(); auto *ql=col(quality,16,4);
    ql->addWidget(ui::text(QString("IQA: %1 · Class confidence %2 · State %3").arg(r.value("quality","Not assessed").toString(),pct(r.value("quality_confidence")),resultState(activeEye_)),14,true));
    for(const auto &warning:r.value("warnings").toList()) ql->addWidget(ui::text(warning.toString(),12));
    if(r.contains("run_id")) ql->addWidget(ui::text("Inference run: "+r.value("run_id").toString(),12)); content->addWidget(quality);
    if(r.value("state")=="RECAPTURE_REQUIRED") {
        auto *alert=panel("border:2px solid #7d5700; background:#fff4de;"); auto *al=col(alert,24);
        al->addWidget(ui::text("Recapture required",20,true)); al->addWidget(ui::text("The image-quality model rejected this scan. Restoration, grading, and lesion analysis were intentionally skipped.",14));
        auto *capture=new QPushButton("Return to Capture"); capture->setObjectName("PrimaryButton"); connect(capture,&QPushButton::clicked,this,[this] { navigate(Capture); }); al->addWidget(capture,0,Qt::AlignLeft); content->addWidget(alert); return outer;
    }
    const QStringList views{"Grade Analysis","Lesion Probability","Lesion Detection","Lesion Annotation"};
    content->addWidget(ui::segmented("Analysis views",views,views[analysisView_],this,[this,views](QString v) { analysisView_=View(views.indexOf(v)); rebuildPage(Analysis); },true));
    auto *main=new ui::ResponsiveGrid(32,true,{7,5});
    auto *left=new QWidget; auto *ll=col(left,0,16);
    auto *controls=new QWidget; controls->setObjectName("VisualizationControls"); auto *flow=new ui::FlowLayout(controls,12);
    const auto segment=[&](QString title,QStringList options,QString value,std::function<void(QString)> changed) { flow->addWidget(ui::segmented(title,options,value,this,changed)); };
    const auto select=[&](QString title,QStringList codes,QString value,std::function<void(QString)> change,bool disabled=false) {
        auto *wrap=new QWidget; auto *row=new QHBoxLayout(wrap); row->setContentsMargins(0,0,0,0); row->setSpacing(8); row->addWidget(ui::text(title,12,true));
        auto *combo=new QComboBox; combo->setAccessibleName(title); combo->setObjectName(title=="Lesion type"?"LesionType":"RegionClass");
        for(const auto &c:codes) combo->addItem(c=="all"?"All classes":name(c),c);
        combo->setCurrentIndex(combo->findData(value)); combo->setEnabled(!disabled); combo->setSizePolicy(QSizePolicy::Maximum,QSizePolicy::Fixed);
        row->addWidget(combo); flow->addWidget(wrap); connect(combo,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[combo,change](int) { change(combo->currentData().toString()); });
    };
    if(analysisView_==GradeView) segment("Grade image mode",{"Original","Grad-CAM","Overlay"},gradeMode_,[this](QString v) { gradeMode_=v; attentionMode_=v=="Grad-CAM"&&attentionType_=="Probability"?"Heatmap":v; rebuildPage(Analysis); });
    if(analysisView_==AttentionView) {
        select("Lesion type",classes,lesionClass_,[this](QString v) { lesionClass_=v; rebuildPage(Analysis); });
        segment("Lesion visualization mechanism",{"Grad-CAM","Probability"},attentionType_,[this](QString v) { attentionType_=v; if(attentionMode_!="Original"&&attentionMode_!="Overlay") attentionMode_=v=="Probability"?"Heatmap":"Grad-CAM"; rebuildPage(Analysis); });
        segment("Lesion image mode",{"Original",attentionType_=="Probability"?"Heatmap":"Grad-CAM","Overlay"},attentionMode_,[this](QString v) { attentionMode_=v; gradeMode_=v=="Heatmap"?"Grad-CAM":v; rebuildPage(Analysis); });
    }
    if(analysisView_==DetectionView) {
        segment("Detection mode",{"Boxes","Coordinates"},showCoordinates_?"Coordinates":"Boxes",[this](QString v) { showCoordinates_=v=="Coordinates"; rebuildPage(Analysis); });
        auto *raw=new QCheckBox("View all raw model regions"); raw->setChecked(showRawRegions_); flow->addWidget(raw);
        connect(raw,&QCheckBox::toggled,this,[this](bool v) { showRawRegions_=v; selectedRegion_.clear(); rebuildPage(Analysis); });
        select("Lesion class",QStringList{"all"}+classes,regionClass_,[this](QString v) { regionClass_=v; selectedRegion_.clear(); rebuildPage(Analysis); },showRawRegions_);
        auto *top=new QWidget; auto *tr=new QHBoxLayout(top); tr->setContentsMargins(0,0,0,0); tr->addWidget(ui::text("Regions shown",12,true));
        auto *combo=new QComboBox; combo->setAccessibleName("Regions shown"); for(int k:{5,10,20,25,50,-1}) combo->addItem(k<0?"All filtered":QString("Top %1").arg(k),k);
        combo->setCurrentIndex(combo->findData(topK_)); combo->setEnabled(!showRawRegions_); tr->addWidget(combo); flow->addWidget(top);
        connect(combo,QOverload<int>::of(&QComboBox::currentIndexChanged),this,[this,combo](int) { topK_=combo->currentData().toInt(); selectedRegion_.clear(); rebuildPage(Analysis); });
        if(showRawRegions_) flow->addWidget(ui::text("Raw model output: all raw components; Top-K and class filtering bypassed.",12));
    }
    if(analysisView_==AnnotationView) {
        segment("Annotation image mode",{"Original","Mask","Overlay"},annotationMode_,[this](QString v) { annotationMode_=v; rebuildPage(Analysis); });
        for(const auto &c:classes) { auto *check=new QCheckBox(name(c)); check->setAccessibleName("Visible lesion mask: "+c); check->setChecked(enabledMaskClasses_.contains(c)); flow->addWidget(check); connect(check,&QCheckBox::toggled,this,[this,c](bool v) { if(v) enabledMaskClasses_.append(c); else enabledMaskClasses_.removeAll(c); rebuildPage(Analysis); }); }
    }
    ll->addWidget(controls);
    const QString selection=showRawRegions_?"Raw model output":QString("%1 · %2").arg(topK_<0?"All filtered":QString("Top %1").arg(topK_),regionClass_=="all"?"all classes":regionClass_);
    if(analysisView_==DetectionView) ll->addWidget(counts(r,int(rows.size()),selection));
    auto *visual=buildVisualization(activeEye_,analysisView_); ll->addWidget(visual);
    if(analysisView_!=DetectionView) {
        auto *wrap=new QWidget; auto *row=new QHBoxLayout(wrap); row->setContentsMargins(0,0,0,0); row->setSpacing(8);
        row->addWidget(ui::text("Overlay opacity",12,true)); auto *slider=new QSlider(Qt::Horizontal); slider->setAccessibleName("Overlay opacity"); slider->setRange(0,100); slider->setValue(opacity_); slider->setFixedWidth(96); row->addWidget(slider);
        auto *percentage=ui::text(QString::number(opacity_)+"%",12,true); percentage->setObjectName("OpacityPercentage"); percentage->setFixedWidth(35); row->addWidget(percentage); flow->addWidget(wrap);
        auto *stage=static_cast<ui::ImageStage*>(visual->findChild<QWidget*>("ImageStage"));
        connect(slider,&QSlider::valueChanged,this,[this,stage,percentage](int value) { opacity_=value; percentage->setText(QString::number(value)+"%"); stage->image=visualizationImage(activeEye_,analysisView_,false); stage->update(); });
    }
    main->append(left);
    auto *summary=panel("border:2px solid #6f7a6f;"); summary->setAccessibleName("Diagnostic summary"); auto *dl=col(summary,24,24);
    auto *dh=new QWidget; auto *dhl=col(dh,0,6); auto *caption=new QHBoxLayout; caption->addWidget(ui::icon("visibility",16)); caption->addWidget(ui::text("MACULA-CENTERED FUNDUS PHOTO",14,true,"#3f4940"),1); dhl->addLayout(caption);
    dhl->addWidget(ui::text(gradeText(r),30,true,"#7d5700")); dhl->addWidget(ui::text(r.contains("grade")?"Model class 0–4 (repository class ordering)":"No grading result for this image",12)); dhl->addWidget(divider()); dl->addWidget(dh);
    auto *confidence=new QWidget; auto *cl=col(confidence,0,8); auto *cr=new QHBoxLayout; cr->addWidget(ui::text("Grade Class Confidence",16),1); cr->addWidget(ui::text(pct(r.value("grade_confidence")),24,true,"#005227")); cl->addLayout(cr); cl->addWidget(ui::meter(r.value("grade_confidence").toDouble(),16)); dl->addWidget(confidence);
    auto *types=new QWidget; auto *tc=col(types,0,12); tc->addWidget(ui::text("Predicted Region Types",18,true)); auto *pills=new QWidget; auto *pf=new ui::FlowLayout(pills,8);
    QStringList seen; for(const auto &v:r.value("regions").toList()) { auto c=code(v.toMap()); if(!seen.contains(c)) { seen<<c; pf->addWidget(ui::pill(name(c))); } }
    if(seen.isEmpty()) pf->addWidget(ui::text(r.contains("regions")?"No regions retained for display":"Lesions not assessed",14)); tc->addWidget(pills); dl->addWidget(types); dl->addWidget(divider());
    auto *actions=new QWidget; auto *af=new QHBoxLayout(actions); af->setContentsMargins(0,0,0,0); af->setSpacing(12);
    for(const auto &action:QStringList{"Confirm Diagnosis","Flag for Review"}) {
        auto *b=new QPushButton(action); b->setObjectName(action.startsWith("Confirm")?"PrimaryButton":"SecondaryButton"); b->setMinimumHeight(48); if(action.startsWith("Confirm")) b->setEnabled(r.contains("grade")); af->addWidget(b,1);
        b->setIcon(ui::buttonIcon(action.startsWith("Confirm")?"edit_document":"flag",action.startsWith("Confirm")?"white":"#005227")); b->setIconSize(QSize(18,18));
        connect(b,&QPushButton::clicked,this,[this,action] { setStatus(action.startsWith("Confirm")?"Diagnosis confirmed by clinician for "+eyeName(activeEye_):eyeName(activeEye_)+" flagged for senior review."); });
    } dl->addWidget(actions);
    auto *masks=new QPushButton("View Lesion Masks"); masks->setStyleSheet("color:#005227; border:0; background:transparent; font-weight:bold;"); connect(masks,&QPushButton::clicked,this,[this] { analysisView_=AnnotationView; rebuildPage(Analysis); }); dl->addWidget(masks);
    auto *compare=new QPushButton("Compare OS and OD Side-by-Side  →"); compare->setStyleSheet(masks->styleSheet()); connect(compare,&QPushButton::clicked,this,[this] { navigate(Compare); }); dl->addWidget(compare); main->append(summary); content->addWidget(main);
    content->addSpacing(24); auto *regionTitle=new QHBoxLayout; regionTitle->addWidget(ui::icon("manage_search",24)); regionTitle->addWidget(ui::text(showRawRegions_?QString("Raw Model Output (%1)").arg(rows.size()):"Predicted Lesion Regions",24,true,"#005227"),1); content->addLayout(regionTitle);
    content->addWidget(counts(r,int(rows.size()),selection));
    auto *grid=new ui::ResponsiveGrid(24); grid->setObjectName("RegionCards");
    for(const auto &region:rows) {
        auto *tile=new RegionCard; tile->setObjectName("RegionCard"); auto id=regionKey(region); bool selected=id==selectedRegion_;
        tile->setAccessibleName(name(code(region))+" region "+id); tile->setProperty("regionId",id); tile->setProperty("selected",selected);
        tile->setStyleSheet(QString("QFrame#RegionCard { background:%1; border:%2px solid %3; border-radius:8px; } QFrame#RegionCard:hover { border-color:#005227; }").arg(selected?"#f0f5ed":"white").arg(selected?3:1).arg(selected?"#005227":"#becabd"));
        auto *rl=col(tile,20,12); auto *rh=new QHBoxLayout; rh->addWidget(ui::icon("search",20,color(code(region)).name())); rh->addWidget(ui::text(name(code(region)),18,true),1); rh->addWidget(ui::pill("Not assessed","#ffdeaa","#755100")); rl->addLayout(rh);
        auto b=box(region); rl->addWidget(ui::text(QString("Coordinates: [X: %1, Y: %2, W: %3, H: %4]").arg(b.x()).arg(b.y()).arg(b.width()).arg(b.height()),12));
        rl->addWidget(ui::text(region.value("description","Predicted mask region. Score is mean pixel probability; clinical severity is not assessed.").toString(),12,false,"#3f4940"));
        auto *score=new QHBoxLayout; score->addWidget(ui::text("Mean pixel probability",12),1); score->addWidget(ui::text(pct(region.value("mean_probability")),12,true,"#005227")); rl->addLayout(score); rl->addWidget(ui::meter(region.value("mean_probability").toDouble()));
        tile->setToolTip(QString("Area: %1 px · Maximum probability: %2 · Source components: %3").arg(region.value("area_pixels").toString(),pct(region.value("max_probability")),QString::number(region.value("source_component_ids").toList().size())));
        tile->selected=[this,id] { selectedRegion_=selectedRegion_==id?QString():id; analysisView_=DetectionView; rebuildPage(Analysis); };
        for(auto *child:tile->findChildren<QWidget*>()) child->setAttribute(Qt::WA_TransparentForMouseEvents);
        grid->append(tile);
    }
    content->addWidget(grid); return outer;
}
} // namespace retina
