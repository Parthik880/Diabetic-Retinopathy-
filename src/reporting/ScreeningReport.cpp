#include "reporting/ScreeningReport.h"
#include "image/ImageDecoder.h"

#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QFileInfo>
#include <QFontMetricsF>
#include <QPainter>
#include <QPdfWriter>

namespace retina::reporting {
namespace {
QString first(const QVariantMap &map, const QStringList &keys) {
    for (const auto &key : keys) if (!map.value(key).toString().isEmpty()) return map.value(key).toString();
    return {};
}
int maskDetection(const QString &path) {
    const auto source = path.isEmpty() ? QImage{} : loadImage(path);
    if (source.isNull()) return -1;
    const auto gray = source.convertToFormat(QImage::Format_Grayscale8);
    for (int y = 0; y < gray.height(); ++y)
        for (int x = 0; x < gray.width(); ++x) if (gray.constScanLine(y)[x]) return 1;
    return 0;
}
}

QString gradeLabel(const QVariant &grade) {
    static const QStringList labels = {"No diabetic retinopathy", "Mild NPDR", "Moderate NPDR", "Severe NPDR", "Proliferative DR"};
    return !grade.isValid() || grade.isNull() || grade.toInt() < 0 ? "Unavailable" : labels.value(grade.toInt(), QString("Grade %1").arg(grade.toInt()));
}
QString qualityLabel(const QString &quality) { return quality == "Reject" ? "Poor - Recapture recommended" : quality.isEmpty() ? "Unavailable" : quality; }
QString qualityMessage(const QString &quality) {
    if (quality == "Good") return "Image is of sufficient quality for reliable screening analysis.";
    if (quality == "Usable") return "Image is usable for screening; clinician review remains required.";
    if (quality == "Reject") return "Image quality may limit analysis. Recapture is recommended.";
    return "Image quality assessment is unavailable.";
}
QString recommendation(const QVariant &grade) {
    if (grade.isValid() && !grade.isNull()) switch (grade.toInt()) {
    case 0: return "No signs of diabetic retinopathy were identified by the screening system. Routine ophthalmic screening is recommended.";
    case 1: return "Features consistent with mild diabetic retinopathy were identified. Ophthalmic follow-up is recommended.";
    case 2: return "Features consistent with moderate diabetic retinopathy were identified. Ophthalmologist evaluation and follow-up are recommended.";
    case 3: case 4: return "Features requiring prompt ophthalmic evaluation were identified. Referral to an ophthalmologist is recommended.";
    }
    return "A screening recommendation is unavailable because DR grading did not complete.";
}
QString confidenceText(const QVariant &confidence) {
    return confidence.isValid() && !confidence.isNull() ? QString::number(confidence.toDouble() * 100, 'f', 1) + '%' : "Unavailable";
}
QString assetPath(const QString &name) {
    QDir dir(QCoreApplication::applicationDirPath());
    for (int i = 0; i < 5; ++i) {
        const auto path = dir.filePath("assets/" + name);
        if (QFileInfo::exists(path)) return path;
        if (!dir.cdUp()) break;
    }
    return QDir::current().filePath("assets/" + name);
}
QVariantMap withContext(QVariantMap result, QVariantMap patient, const QString &eye,
                        const QDateTime &scanTime, const QString &originalPath) {
    if (patient.isEmpty()) patient = result.value("report_patient").toMap();
    patient["eye"] = eye;
    if (patient.value("id").toString().isEmpty() || patient.contains("patientIdNumber"))
        patient["id"] = first(patient, {"patientIdNumber", "patient_id", "id"});
    QString timestamp = first(result, {"scan_datetime", "capturedAt"});
    if (timestamp.isEmpty()) timestamp = first(patient, {"scan_datetime", "capturedAt"});
    if (timestamp.isEmpty() && scanTime.isValid()) timestamp = scanTime.toLocalTime().toString(Qt::ISODate);
    if (!timestamp.isEmpty()) { patient["scan_datetime"] = timestamp; result["scan_datetime"] = timestamp; }
    if (result.value("image_path").toString().isEmpty()) result["image_path"] = originalPath;
    if (result.value("run_id").toString().isEmpty()) {
        // Model artifacts already live in a UUID run directory. Older snapshots
        // without artifacts get a stable report identifier from their saved data.
        const QString artifact = first(result, {"lesion_overlay_path", "gradcam_path", "restored_image_path"});
        QString id = artifact.isEmpty() ? QString{} : QFileInfo(artifact).dir().dirName();
        if (id.isEmpty() || !QFileInfo(artifact).dir().absolutePath().contains("/runs/")) {
            const auto identity = (patient.value("id").toString() + '|' + eye + '|' + timestamp + '|' + result.value("image_path").toString()).toUtf8();
            id = "local-" + QString::fromLatin1(QCryptographicHash::hash(identity, QCryptographicHash::Sha256).toHex().left(12));
        }
        result["run_id"] = id;
    }
    result["report_patient"] = patient;
    return result;
}

Data::Data(const QVariantMap &result) {
    patient = result.value("report_patient").toMap();
    eye = patient.value("eye").toString();
    runId = result.value("run_id").toString();
    scanTime = first(patient, {"scan_datetime", "capturedAt"});
    device = first(result, {"device_name", "device"});
    original = first(result, {"image_path", "original_image_path"});
    overlay = first(result, {"lesion_overlay_path"});
    quality = result.value("quality").toString();
    if (result.value("quality").canConvert<QVariantMap>()) quality = result.value("quality").toMap().value("quality").toString();
    restored = first(result, {"restored_image_path"});
    if (!QFileInfo::exists(restored)) restored.clear();
    grade = result.contains("grade") ? result.value("grade") : result.value("grading").toMap().value("predicted_grade");
    confidence = result.contains("grade_confidence") ? result.value("grade_confidence") : result.value("grading").toMap().value("confidence");
    const auto structured = result.value("lesions").toMap().value("lesions").toMap();
    const auto masks = result.value("lesion_mask_paths").toMap();
    const auto counts = result.value("lesion_counts").toMap();
    for (int i = 0; i < 4; ++i) {
        const auto code = lesionCodes[i];
        const auto item = structured.value(code).toMap();
        if (item.contains("detected")) lesions[i] = item.value("detected").toBool() ? 1 : 0;
        else if (masks.contains(code)) lesions[i] = maskDetection(masks.value(code).toString());
        // Legacy saved results may only contain counts. Positive counts confirm
        // detection; zero cannot prove absence without the complete binary mask.
        else if (counts.value(code).toInt() > 0) lesions[i] = 1;
    }
}
QString Data::lesionStatus(int index) const { return lesions[index] < 0 ? "Unavailable" : lesions[index] ? "Detected" : "Not detected"; }
QList<QPair<QString, QString>> Data::metadata() const {
    QStringList demographics;
    for (const auto &key : {"age", "gender"}) if (!patient.value(key).toString().isEmpty()) demographics << patient.value(key).toString();
    return {{"Patient name",patient.value("name").toString()}, {"Patient ID",patient.value("id").toString()},
            {"Age / gender",demographics.join(" / ")}, {"Date and time of scan",scanTime},
            {"Image eye",eye == "OS" ? "Left (OS)" : eye == "OD" ? "Right (OD)" : eye},
            {"Report ID",runId}, {"Inference device",device}, {"Referring doctor",patient.value("referring_doctor").toString()}};
}

bool writePdf(const QString &path, const QVariantMap &result, const QDateTime &generatedAt) {
    const Data data(result);
    constexpr double w = 595.27559, h = 841.88976;
    const QColor green("#075B35"), soft("#EAF5EE"), ink("#142018"), muted("#64736A"), border("#CBD9CF"), amber("#A06400");
    QPdfWriter pdf(path);
    pdf.setPageSize(QPageSize(QPageSize::A4));
    pdf.setPageMargins(QMarginsF(0,0,0,0), QPageLayout::Point);
    pdf.setResolution(144);
    pdf.setTitle("RetinaGram screening report " + data.runId);
    pdf.setCreator("RetinaGram");
    QPainter p;
    if (!p.begin(&pdf)) return false;
    p.scale(pdf.width()/w, pdf.height()/h);
    p.setRenderHints(QPainter::Antialiasing | QPainter::SmoothPixmapTransform);
    p.fillRect(QRectF(0,0,w,h),Qt::white);
    auto font = [&](double size, bool bold = false) { QFont f("Arial"); f.setPixelSize(qRound(size*100)); f.setBold(bold); p.setFont(f); };
    // Fractional point typography independent of the printer's DPI.
    auto text = [&](double x, double y, const QString &s, double size, bool bold, QColor color, int align = 0) {
        p.save(); p.translate(x,h-y); p.scale(0.01,0.01); font(size,bold); p.setPen(color);
        double offset = align == 2 ? -QFontMetricsF(p.font()).horizontalAdvance(s) : align == 1 ? -QFontMetricsF(p.font()).horizontalAdvance(s)/2 : 0;
        p.drawText(QPointF(offset,0),s); p.restore();
    };
    auto lines = [&](double x,double y,const QString &s,double size,bool bold,QColor color,double width,double leading) {
        QFont f("Arial"); f.setPixelSize(qRound(size*100)); f.setBold(bold); QFontMetricsF fm(f);
        QString line; int row=0;
        for(const auto &word:s.split(' ',Qt::SkipEmptyParts)) {
            const QString next=line.isEmpty()?word:line+' '+word;
            if(!line.isEmpty() && fm.horizontalAdvance(next)/100 > width) { text(x,y-row++*leading,line,size,bold,color); line=word; } else line=next;
        }
        if(!line.isEmpty()) text(x,y-row*leading,line,size,bold,color);
    };
    auto rect = [&](double x,double y,double width,double height,double radius,QColor fill,bool stroke) {
        p.setBrush(fill); p.setPen(stroke?QPen(border,0.7):QPen(Qt::NoPen)); p.drawRoundedRect(QRectF(x,h-y-height,width,height),radius,radius);
    };
    auto divider = [&](double x,double y,double right) { p.setPen(QPen(border,0.7)); p.drawLine(QPointF(x,h-y),QPointF(right,h-y)); };
    auto image = [&](const QString &source,double x,double y,double width,double height) {
        rect(x,y,width,height,6,QColor("#101411"),true);
        const auto im=source.isEmpty()?QImage{}:loadImage(source);
        if(im.isNull()) { text(x+width/2,y+height/2,"Image unavailable",8,false,QColor("#b8c5bd"),1); return; }
        const QSizeF size=QSizeF(im.size()).scaled(QSizeF(width-8,height-8),Qt::KeepAspectRatio);
        p.drawImage(QRectF(x+(width-size.width())/2,h-y-height+(height-size.height())/2,size.width(),size.height()),im);
    };
    rect(30,759,w-60,55,8,QColor("#F7FBF8"),false);
    const auto logo=loadImage(assetPath("logo.jpeg"));
    if(!logo.isNull()) p.drawImage(QRectF(38,h-806,40,40),logo);
    text(86,790,"RetinaGram",17,true,green); text(86,777,"AI Retinal Screening",8.5,false,muted);
    text(w-40,793,"Diabetic Retinopathy",13,true,ink,2); text(w-40,777,"Screening Report",10,false,ink,2);
    text(34,740,"Patient information",9.5,true,ink); divider(34,734,w-34);
    const auto metadata=data.metadata();
    auto field = [&](double x,double y,const QPair<QString,QString> &item) {
        text(x,y,item.first.toUpper(),6.8,false,muted);
        // Keep fixed A4 metadata rows clear, as in the reference writer. Use a
        // smaller font for long values before applying its final text elision.
        double size=8.2;
        QFont f("Arial"); f.setBold(true);
        for(;size>6.2;size-=0.2) { f.setPixelSize(qRound(size*100)); if(QFontMetricsF(f).horizontalAdvance(item.second)/100<=235) break; }
        f.setPixelSize(qRound(size*100));
        text(x,y-11,QFontMetricsF(f).elidedText(item.second,Qt::ElideRight,23500),size,true,ink);
    };
    double row=724;
    for(int i=0;i<4;++i) if(!metadata[i].second.isEmpty()) { field(38,row,metadata[i]); row-=24; }
    row=724;
    for(int i : {7,6,4,5}) if(!metadata[i].second.isEmpty()) { field(315,row,metadata[i]); row-=24; }
    text(34,620,"Main analysis",9.5,true,ink);
    const int count=data.restored.isEmpty()?2:3;
    const double gap=8,imageW=(w-68-125-gap*count)/count;
    double x=34;
    const QList<QPair<QString,QString>> images = data.restored.isEmpty()
        ? QList<QPair<QString,QString>>{{"ORIGINAL FUNDUS IMAGE",data.original},{"AI ANALYSIS / LESION OVERLAY",data.overlay}}
        : QList<QPair<QString,QString>>{{"ORIGINAL FUNDUS IMAGE",data.original},{"RESTORED FUNDUS IMAGE",data.restored},{"AI ANALYSIS / LESION OVERLAY",data.overlay}};
    for(const auto &item:images) { text(x,606,item.first,count==3?5.8:7.3,true,muted); image(item.second,x,390,imageW,209); x+=imageW+gap; }
    const double gradeW=w-34-x;
    rect(x,390,gradeW,223,8,soft,false); text(x+13,581,"DR GRADE",8,true,green);
    lines(x+13,552,gradeLabel(data.grade),15,true,ink,gradeW-26,17);
    text(x+13,512,data.grade.isValid()&&data.grade.toInt()>=0?QString("Grade %1").arg(data.grade.toInt()):"Grade unavailable",10,false,muted);
    divider(x+13,493,x+gradeW-13); text(x+13,477,"CONFIDENCE",7.5,true,muted);
    text(x+13,449,confidenceText(data.confidence),18,true,green);
    rect(34,265,325,105,7,Qt::white,true); text(46,350,"Lesion detection",9.5,true,ink);
    for(int i=0;i<4;++i) { const double lx=46+(i%2)*154,ly=325-(i/2)*33;
        text(lx,ly+10,lesionNames[i],7.2,false,muted); text(lx,ly-1,data.lesionStatus(i),8.5,true,data.lesions[i]==1?green:ink); }
    rect(369,265,w-403,105,7,data.quality=="Reject"?QColor("#FFF1E5"):soft,true);
    text(381,350,"Image quality",9.5,true,ink);
    lines(381,324,qualityLabel(data.quality),12,true,data.quality=="Good"||data.quality=="Usable"?green:amber,w-427,14);
    lines(381,290,qualityMessage(data.quality),7.2,false,muted,w-427,9);
    rect(34,145,w-68,100,7,QColor("#F7FBF8"),false);
    text(46,222,"Screening recommendation",9.5,true,ink);
    lines(46,202,recommendation(data.grade),8.4,false,muted,w-92,11);
    divider(34,55,w-34); text(34,39,disclaimer,6.8,false,muted);
    text(w-34,25,"Page 1 of 1",6.8,false,muted,2);
    text(34,25,"Generated locally "+generatedAt.toLocalTime().toString("yyyy-MM-dd HH:mm:ss t"),6.8,false,QColor("#87968D"));
    const bool ended=p.end();
    return ended && QFileInfo(path).size()>0;
}
} // namespace retina::reporting
