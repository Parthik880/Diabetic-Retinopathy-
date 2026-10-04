#include "app/BatchDiscovery.h"
#include "image/ImageDecoder.h"
#include "image/EyeAssignment.h"
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QDateTime>

namespace retina {
namespace {
QString normalize(QString s) { s=s.trimmed(); s.remove(QRegularExpression("^#")); auto m=QRegularExpression("^([A-Za-z]+)[ _-]?(\\d+)$").match(s); return m.hasMatch()?m.captured(1).toUpper()+"-"+m.captured(2):s; }
QPair<QString,QString> identity(QString s,bool flat) {
    auto m=QRegularExpression("^\\s*#?([A-Za-z]+)[ _-]?(\\d+)(.*)$").match(s);
    if(!m.hasMatch()) return {};
    QString rest=m.captured(3);
    if(flat) rest.remove(QRegularExpression("[ _-](LEFT(?:[ _-]?EYE)?|RIGHT(?:[ _-]?EYE)?|OS|OD|LE|RE|L|R)(?:[ _-]?\\d+)?$",QRegularExpression::CaseInsensitiveOption));
    rest.replace('_',' '); rest=rest.trimmed(); rest.remove(QRegularExpression("^[ -]+|[ -]+$"));
    return {normalize(m.captured(1)+m.captured(2)),rest.simplified()};
}
bool imageFile(const QFileInfo &f) { return QStringList{"jpg","jpeg","png","bmp","tif","tiff"}.contains(f.suffix().toLower()); }
bool support(const QFileInfo &f) { return f.fileName().compare("patient.json",Qt::CaseInsensitive)==0 || f.fileName().startsWith("readme",Qt::CaseInsensitive) || QStringList{"desktop.ini","thumbs.db",".ds_store"}.contains(f.fileName().toLower()); }
QString outputIdentity(const QVariantMap &p) {
    QString value=p.value("patient_id").toString(); const auto name=p.value("name").toString(); if(!name.isEmpty()) value+="_"+name;
    value.remove(QRegularExpression("[<>:\"/\\\\|?*\\x00-\\x1f]")); value.remove(QRegularExpression("\\s+")); value=value.left(64); value.remove(QRegularExpression("^[ .]+|[ .]+$")); return value.isEmpty()?"Patient":value;
}
}
QVariantMap discoverBatchInput(const QString &directory) {
    QDir root(directory); QVariantList invalid,logs; QMap<QString,QVariantMap> patients;
    auto log=[&](QString message) { logs.append(QVariantMap{{"time",QTime::currentTime().toString("HH:mm:ss")},{"message",message}}); };
    auto reject=[&](QFileInfo f,QString reason) { invalid.append(QVariantMap{{"path",f.absoluteFilePath()},{"name",f.fileName()},{"reason",reason}}); log("Rejected "+f.fileName()+": "+reason); };
    auto add=[&](QFileInfo file,QString id,QString patientName,QString eye,bool hardInvalid) {
        if(id.isEmpty()) { reject(file,"could not determine patient ID"); return; }
        auto key=id.toCaseFolded(); auto p=patients.value(key);
        if(p.isEmpty()) p={{"patient_id",id},{"name",patientName},{"eye_candidates",QVariantMap{{"OS",QVariantList{}},{"OD",QVariantList{}}}},{"issues",QStringList{}}};
        auto issues=p.value("issues").toStringList();
        if(p.value("name").toString().isEmpty()) p["name"]=patientName;
        else if(!patientName.isEmpty()&&p.value("name").toString().compare(patientName,Qt::CaseInsensitive)) { QString issue="Conflicting patient names: "+p.value("name").toString()+" / "+patientName; if(!issues.contains(issue)) issues<<issue; }
        p["issues"]=issues; p["hard_invalid"]=p.value("hard_invalid").toBool()||hardInvalid;
        auto candidates=p.value("eye_candidates").toMap();
        if(eye.isEmpty()) reject(file,"patient recognized, eye side unknown");
        else if(loadImage(file.absoluteFilePath()).isNull()) reject(file,"image is corrupt or unreadable");
        else { auto list=candidates.value(eye).toList(); list.append(QVariantMap{{"source_name",file.fileName()},{"source_path",file.absoluteFilePath()},{"eye",eye}}); candidates[eye]=list; log(id+" ["+eye+"] "+file.fileName()); }
        p["eye_candidates"]=candidates; patients[key]=p;
    };
    auto structured=[&](QDir folder) {
        auto [id,patientName]=identity(folder.dirName(),false); bool hardInvalid=false;
        QFile metadata(folder.filePath("patient.json"));
        if(metadata.exists()) {
            metadata.open(QIODevice::ReadOnly); QJsonParseError error; auto doc=QJsonDocument::fromJson(metadata.readAll(),&error);
            if(error.error!=QJsonParseError::NoError||!doc.isObject()) { reject(QFileInfo(metadata),"invalid patient metadata JSON"); hardInvalid=true; }
            else { auto data=doc.toVariant().toMap(); if(!data.value("patient_id").toString().isEmpty()) id=normalize(data.value("patient_id").toString()); if(!data.value("name").toString().isEmpty()) patientName=data.value("name").toString(); }
        }
        if(!id.isEmpty()&&!patients.contains(id.toCaseFolded())) patients[id.toCaseFolded()]={{"patient_id",id},{"name",patientName},{"eye_candidates",QVariantMap{{"OS",QVariantList{}},{"OD",QVariantList{}}}},{"issues",QStringList{}},{"hard_invalid",hardInvalid}};
        bool found=false;
        for(const auto &f:folder.entryInfoList(QDir::Files,QDir::Name)) {
            if(imageFile(f)) { found=true; add(f,id,patientName,eyeFromBatchPath(f.fileName()),hardInvalid); }
            else if(!support(f)) reject(f,"unsupported file type");
        }
        if(!found&&id.isEmpty()) reject(QFileInfo(folder.absolutePath()),"could not determine patient ID or find retinal images");
    };
    log("Scanning: "+root.absolutePath());
    auto files=root.entryInfoList(QDir::Files,QDir::Name); auto folders=root.entryInfoList(QDir::Dirs|QDir::NoDotAndDotDot,QDir::Name);
    bool rootPatient=QFileInfo::exists(root.filePath("patient.json"));
    if(!rootPatient&&!identity(root.dirName(),false).first.isEmpty()) {
        bool side=false,flat=false;
        for(const auto &f:files) if(imageFile(f)) { side|=!eyeFromBatchPath(f.fileName()).isEmpty(); flat|=!identity(f.completeBaseName(),true).first.isEmpty(); }
        rootPatient=side&&!flat;
    }
    if(rootPatient) structured(root);
    else for(const auto &f:files) {
        if(support(f)) continue;
        if(!imageFile(f)) { reject(f,"unsupported file type"); continue; }
        auto [id,patientName]=identity(f.completeBaseName(),true); add(f,id,patientName,eyeFromBatchPath(f.fileName()),false);
    }
    for(const auto &f:folders) structured(QDir(f.absoluteFilePath()));
    QVariantList result; int totalImages=0,ready=0,review=0,paired=0,single=0;
    for(auto p:patients) {
        auto candidates=p.value("eye_candidates").toMap(); auto issues=p.value("issues").toStringList(); int eyes=0;
        for(const auto &eye:QStringList{"OS","OD"}) { auto size=candidates.value(eye).toList().size(); totalImages+=int(size); if(size) ++eyes; if(size>1) issues<<"Duplicate "+eye+" images"; }
        p["issues"]=issues; p["index"]=result.size()+1;
        p["discovery_status"]=p.value("hard_invalid").toBool()||!eyes?"INVALID":issues.isEmpty()?"READY":"NEEDS_REVIEW";
        p["status"]=p.value("discovery_status"); if(p.value("status")=="READY") ++ready; if(p.value("status")=="NEEDS_REVIEW") ++review;
        if(eyes==2) ++paired; else if(eyes==1) ++single; result<<p;
    }
    log(QString("%1 patients ready · %2 need review · %3 invalid items").arg(ready).arg(review).arg(invalid.size()));
    return {{"state","Review"},{"input_path",root.absolutePath()},{"patients",result},{"invalid_items",invalid},{"logs",logs},
        {"mode",rootPatient||(!folders.isEmpty()&&files.isEmpty())?"structured":folders.isEmpty()?"simple":"mixed"},
        {"counts",QVariantMap{{"total_patients",result.size()},{"total_images",totalImages},{"ready",ready},{"needs_review",review},{"invalid",invalid.size()},{"paired_patients",paired},{"single_eye_patients",single}}}};
}
bool batchPatientReady(const QVariantMap &p,const QMap<QString,QString> &selections) {
    if(p.value("discovery_status")=="INVALID") return false;
    for(const auto &issue:p.value("issues").toStringList()) if(!issue.startsWith("Duplicate ")) return false;
    const auto candidates=p.value("eye_candidates").toMap();
    for(const auto &eye:QStringList{"OS","OD"}) if(candidates.value(eye).toList().size()>1) {
        bool selected=false; for(const auto &v:candidates.value(eye).toList()) selected|=v.toMap().value("source_path").toString()==selections.value(p.value("patient_id").toString()+"/"+eye);
        if(!selected) return false;
    }
    return true;
}
QVariantList batchImagePlan(const QVariantMap &s,const QMap<QString,QString> &selections) {
    QVariantList images;
    for(const auto &v:s.value("patients").toList()) { auto p=v.toMap(); if(!batchPatientReady(p,selections)) continue;
        for(const auto &eye:QStringList{"OS","OD"}) { auto candidates=p.value("eye_candidates").toMap().value(eye).toList(); if(candidates.isEmpty()) continue;
            QVariantMap chosen; if(candidates.size()==1) chosen=candidates.first().toMap(); else for(const auto &c:candidates) if(c.toMap().value("source_path").toString()==selections.value(p.value("patient_id").toString()+"/"+eye)) chosen=c.toMap();
            if(!chosen.isEmpty()) { chosen["patient_id"]=p.value("patient_id"); chosen["patient_name"]=p.value("name"); const auto identity=outputIdentity(p); chosen["patient_folder"]=identity; chosen["anonymous_folder"]=QString("Patient_%1_%2").arg(p.value("index").toInt(),3,10,QChar('0')).arg(identity); images<<chosen; }
        }
    }
    return images;
}
}
