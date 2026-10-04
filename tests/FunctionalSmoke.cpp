#include "ui/MainWindow.h"
#include "app/AnalysisController.h"
#include "app/BatchDiscovery.h"
#include "reporting/ScreeningReport.h"
#include <QComboBox>
#include <QAbstractItemView>
#include <QScrollArea>
#include <QScrollBar>
#include <QApplication>
#include <QFile>
#include <QFileDialog>
#include <QJsonDocument>
#include <QDirIterator>
#include <QTimer>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QTemporaryDir>
#include <QTest>
#include <QStandardPaths>

class FunctionalSmoke : public QObject {
    Q_OBJECT
private slots:
    void reportUiAndExports() {
        QCoreApplication::setApplicationName(QString("ReportSmoke-%1").arg(QCoreApplication::applicationPid()));
        const QString output=qEnvironmentVariable("RETINAGRAM_UI_OUTPUT");
        auto load=[](QString path) { QFile file(path); if(!file.open(QIODevice::ReadOnly)) return QVariantMap{}; return QJsonDocument::fromJson(file.readAll()).toVariant().toMap(); };
        auto good=load(qEnvironmentVariable("RETINAGRAM_GOOD_RESULT"));
        auto usable=load(qEnvironmentVariable("RETINAGRAM_USABLE_RESULT"));
        QVERIFY(good.value("state")=="COMPLETE"); QVERIFY(good.value("quality")=="Good");
        QVERIFY(usable.value("quality")=="Usable"); QVERIFY(QFileInfo::exists(usable.value("restored_image_path").toString()));
        good["scan_datetime"]="2026-10-04T09:15:00+05:30"; usable["scan_datetime"]="2026-10-04T09:10:00+05:30";
        retina::MainWindow window; window.resize(1440,960); window.show(); AnalysisController controller(&window);
        auto button=[&](QString name)->QPushButton* { for(auto *b:window.findChildren<QPushButton*>()) if(b->isVisible()&&(b->text()==name||b->accessibleName()==name)) return b; return nullptr; };
        auto patient=[](QString id,QString name) { return QVariantMap{{"id",id},{"patientIdNumber",id},{"name",name},{"age",58},{"gender","Female"},{"referring_doctor","Dr. Test Reviewer"}}; };
        window.setPatient(patient("RH-2816","birds")); window.setEyeResult("OS",usable); window.setEyeResult("OD",good);
        window.setPatient(patient("RH-2817","A very long patient name for checking dropdown text elision and list width"));
        window.setPatient(patient("RH-2818","Third Patient"));
        auto *selector=window.findChild<QComboBox*>("PatientSelector"); QVERIFY(selector); QCOMPARE(selector->count(),3);
        QTRY_VERIFY_WITH_TIMEOUT(selector->isEnabled(),30000); selector->setCurrentIndex(0);
        QVERIFY(button("Report")); button("Report")->click();
        auto *tab=button("Report eye: Right Eye (OD)  "+QString::fromUtf8("✓")); QVERIFY(tab); tab->click();
        QCoreApplication::processEvents(); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete);
        QCOMPARE(window.reportData("OD").value("report_patient").toMap().value("id").toString(),QString("RH-2816"));
        const QStringList gradeLabels={"No diabetic retinopathy","Mild NPDR","Moderate NPDR","Severe NPDR","Proliferative DR"};
        const int fixtureGrade=good.value("grade").toInt();
        QVERIFY(fixtureGrade>=0 && fixtureGrade<gradeLabels.size());
        QCOMPARE(window.findChild<QLabel*>("ReportGradeLabel")->text(),gradeLabels[fixtureGrade]);
        QCOMPARE(window.findChild<QLabel*>("ReportConfidence")->text(),retina::reporting::confidenceText(good.value("grade_confidence")));
        QVERIFY(!window.findChild<QWidget*>("ReportRestored"));
        for(auto key:{"Patient name","Patient ID","Age / gender","Date and time of scan","Image eye","Report ID","Inference device"}) {
            auto *value=window.findChild<QLabel*>(QString("ReportMetadata_")+key); QVERIFY(value); QVERIFY(!value->text().isEmpty());
        }
        const retina::reporting::Data data(window.reportData("OD"));
        for(int i=0;i<4;++i) QCOMPARE(window.findChild<QLabel*>("ReportLesion_"+retina::reporting::lesionCodes[i])->text(),data.lesionStatus(i));
        auto saveScreenshot=[&](QString file) { QCoreApplication::processEvents(); return window.grab().save(output+"/"+file); };
        QVERIFY(selector->width()>=280&&selector->width()<=340); QCOMPARE(selector->height(),44);
        QVERIFY(saveScreenshot("report-good-1440x960.png"));
        QVERIFY(window.findChild<QWidget*>("ReportDocument")->grab().save(output+"/report-good-document.png"));
        for(auto size:{QSize(1440,960),QSize(1600,960),QSize(1920,1080)}) {
            window.resize(size); QCoreApplication::processEvents(); QCOMPARE(window.size(),size);
            auto *cloud=button("Cloud Sync"); QVERIFY(cloud); QVERIFY(cloud->mapTo(&window,QPoint(cloud->width(),0)).x()<=window.width());
            for(auto *nav:window.findChildren<QPushButton*>("NavButton")) QVERIFY(nav->isVisible());
        }
        QVERIFY(saveScreenshot("report-good-1920x1080.png"));
        selector->showPopup(); QCoreApplication::processEvents(); QVERIFY(selector->view()->width()>=280); QVERIFY(selector->view()->width()<=340);
        QVERIFY(selector->view()->window()->width()>=300); QVERIFY(selector->view()->window()->width()<=340);
        QVERIFY(selector->view()->window()->grab().save(output+"/patient-selector-popup.png")); selector->hidePopup();
        selector->setCurrentIndex(1); QVERIFY(selector->currentText().contains("A very long patient name"));
        QVERIFY(saveScreenshot("patient-selector-long-1920x1080.png")); selector->setCurrentIndex(0);
        button("Report")->click();
        tab=button("Report eye: Right Eye (OD)  "+QString::fromUtf8("✓")); QVERIFY(tab); tab->click();
        auto chooseFolder=[](QString path) { QTimer::singleShot(100,[path] { auto *dialog=qobject_cast<QFileDialog*>(QApplication::activeModalWidget()); if(!dialog) return; dialog->setDirectory(path); QTimer::singleShot(200,dialog,[dialog] { QMetaObject::invokeMethod(dialog,"accept",Qt::DirectConnection); }); }); };
        QTemporaryDir singleFolder,bothFolder; QVERIFY(singleFolder.isValid()); QVERIFY(bothFolder.isValid()); chooseFolder(singleFolder.path()); QVERIFY(button("Save Right Eye Report")); button("Save Right Eye Report")->click();
        QDirIterator single(singleFolder.path(),{"*.pdf"},QDir::Files,QDirIterator::Subdirectories); QVERIFY(single.hasNext());
        const auto singlePdf=single.next(); QVERIFY(QFileInfo(singlePdf).size()>1000); QFile::remove(output+"/good-OD.pdf"); QVERIFY(QFile::copy(singlePdf,output+"/good-OD.pdf"));
        chooseFolder(bothFolder.path()); QVERIFY(button("Save Both Reports")); button("Save Both Reports")->click();
        QDirIterator both(bothFolder.path(),{"*.pdf"},QDir::Files,QDirIterator::Subdirectories); int count=0;
        while(both.hasNext()) { const auto path=both.next(); ++count; if(QFileInfo(path).dir().dirName()=="Left_OS") { QFile::remove(output+"/usable-OS.pdf"); QVERIFY(QFile::copy(path,output+"/usable-OS.pdf")); } } QCOMPARE(count,2);
        const auto roots=QDir(bothFolder.path()).entryList(QDir::Dirs|QDir::NoDotAndDotDot); QCOMPARE(roots.size(),1);
        const auto bundle=QDir(bothFolder.path()).filePath(roots[0]);
        for(const auto &eyeFolder:{QString("Left_OS"),QString("Right_OD")}) {
            const QDir dir(QDir(bundle).filePath(eyeFolder));
            QVERIFY(QFileInfo::exists(dir.filePath("results.json"))); QVERIFY(QFileInfo::exists(dir.filePath("original_fundus.jpg")));
            QVERIFY(QFileInfo::exists(dir.filePath("lesion_overlay.png")));
            QCOMPARE(QDir(dir.filePath("masks")).entryList({"*.png"},QDir::Files).size(),4);
        }
        QVERIFY(QFileInfo::exists(QDir(bundle).filePath("Left_OS/restored_fundus.png")));
        QVERIFY(!QFileInfo::exists(QDir(bundle).filePath("Right_OD/restored_fundus.png")));
        QCOMPARE(window.reportData("OD").value("report_path").toString(),QDir(bundle).filePath("Right_OD/report.pdf"));
        QCOMPARE(window.reportData("OS").value("report_path").toString(),QDir(bundle).filePath("Left_OS/report.pdf"));
        auto *left=button("Report eye: Left Eye (OS)  "+QString::fromUtf8("✓")); QVERIFY(left); left->click(); QCoreApplication::processEvents();
        QVERIFY(window.findChild<QWidget*>("ReportRestored")); QCOMPARE(window.findChild<QLabel*>("ReportGradeLabel")->text(),QString("Severe NPDR"));
        QVERIFY(saveScreenshot("report-usable-1920x1080.png"));
        QVERIFY(window.findChild<QWidget*>("ReportDocument")->grab().save(output+"/report-usable-document.png"));
        const QString referral=output+"/referral-draft.txt";
        QFile::remove(referral);
        QTimer::singleShot(100,[referral] { auto *dialog=qobject_cast<QFileDialog*>(QApplication::activeModalWidget()); if(!dialog) return; dialog->setDirectory(QFileInfo(referral).absolutePath()); if(auto *name=dialog->findChild<QLineEdit*>("fileNameEdit")) name->setText(QFileInfo(referral).fileName()); QTimer::singleShot(200,dialog,[dialog] { QMetaObject::invokeMethod(dialog,"accept",Qt::DirectConnection); }); });
        QVERIFY(button("Save referral draft")); button("Save referral draft")->click();
        QFile draft(referral); QVERIFY(draft.open(QIODevice::ReadOnly)); const auto draftText=QString::fromUtf8(draft.readAll()); QVERIFY(draftText.contains("Severe NPDR")); QVERIFY(draftText.contains(retina::reporting::recommendation(3)));
        window.setPatient(patient("RH-2818","Third Patient")); button("Report")->click(); QVERIFY(!button("Save Both Reports"));
        // Detection is read from masks, regardless of a zero Top-K display count.
        good["lesion_counts"]=QVariantMap{{"MA",0},{"HE",0},{"EX",0},{"SE",0}};
        const retina::reporting::Data noTopK(retina::reporting::withContext(good,patient("RH-2816","birds"),"OD"));
        QCOMPARE(noTopK.lesions,data.lesions);
        qInfo()<<"Saved-result report PDF/UI checks:"<<output;
    }
    void realBatchPauseResumeCancelAndReports() {
        QTemporaryDir input,output; QVERIFY(input.isValid()); QVERIFY(output.isValid());
        const QString image=qEnvironmentVariable("RETINAGRAM_TEST_IMAGE");
        QVERIFY(QFile::copy(image,input.filePath("RH-901_Smoke_OS.jpg"))); QVERIFY(QFile::copy(image,input.filePath("RH-901_Smoke_OD.jpg")));
        const QString dataFolder=QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation); QVERIFY(QDir().mkpath(dataFolder));
        const QVariantMap historicResult{{"state","COMPLETE"},{"grade",2},{"grade_confidence",0.91},{"quality","Good"},{"quality_confidence",0.98},{"image_path",image},{"lesion_overlay_path",""},{"lesion_counts",QVariantMap{{"MA","1"},{"HE","2"},{"EX","0"},{"SE","0"}}}};
        const QVariantMap historicEye{{"imagePath",image},{"result",historicResult},{"stage","Complete"},{"error",""}};
        const QVariantMap historicPatient{{"details",QVariantMap{{"id","RH-PDF-1"},{"patientIdNumber","RH-PDF-1"},{"name","Historical PDF Fixture"}}},{"os",historicEye},{"od",QVariantMap{{"imagePath",""},{"result",QVariantMap{}},{"stage",""},{"error",""}}}};
        QFile historyState(QDir(dataFolder).filePath("session.json")); QVERIFY(historyState.open(QIODevice::WriteOnly));
        historyState.write(QJsonDocument::fromVariant(QVariantMap{{"patients",QVariantList{}},{"history",QVariantList{QVariantMap{{"patient",historicPatient},{"savedAt",QDateTime::currentDateTime().toString(Qt::ISODateWithMs)}}}},{"currentPatient",-1}}).toJson()); historyState.close();
        retina::MainWindow window; window.resize(1426,952); window.show(); AnalysisController controller(&window);
        const auto button=[&](QString name)->QPushButton* { for(auto *b:window.findChildren<QPushButton*>()) if(b->isVisible()&&(b->text()==name||b->accessibleName()==name)) return b; return nullptr; };
        const auto modelsReady=[&] { for(auto *l:window.findChildren<QLabel*>()) if(l->text()=="Native models ready for analysis.") return true; return false; };
        QTRY_VERIFY_WITH_TIMEOUT(modelsReady(),30000);
        auto *historyNav=button("History"); QVERIFY(historyNav); historyNav->click();
        auto *patientHistory=button("View history: RH-PDF-1"); QVERIFY(patientHistory); patientHistory->click();
        auto *download=window.findChild<QPushButton*>("HistoryDownload_local-");
        if (!download) {
            for (auto *candidate:window.findChildren<QPushButton*>()) if(candidate->objectName().startsWith("HistoryDownload_local-")) download=candidate;
        }
        QVERIFY(download);
        QTimer::singleShot(100,[path=output.path()] {
            auto *dialog=qobject_cast<QFileDialog*>(QApplication::activeModalWidget()); if(!dialog) return;
            dialog->setDirectory(path);
            QTimer::singleShot(250,dialog,[dialog] { QMetaObject::invokeMethod(dialog,"accept",Qt::DirectConnection); });
        });
        download->click();
        QDirIterator historicalPdf(output.path(),{"*.pdf"},QDir::Files,QDirIterator::Subdirectories);
        QVERIFY(historicalPdf.hasNext());
        const QString historyPdfPath=historicalPdf.next();
        QFile historicFile(historyPdfPath); QVERIFY(historicFile.open(QIODevice::ReadOnly)); QCOMPARE(historicFile.read(5),QByteArray("%PDF-"));
        QFile persisted(QDir(dataFolder).filePath("session.json")); QVERIFY(persisted.open(QIODevice::ReadOnly));
        const auto state=QJsonDocument::fromJson(persisted.readAll()).toVariant().toMap();
        QCOMPARE(state.value("history").toList()[0].toMap().value("patient").toMap().value("os").toMap().value("result").toMap().value("report_path").toString(),historyPdfPath);
        QVERIFY(QFileInfo::exists(QDir(QFileInfo(historyPdfPath).absolutePath()).filePath("results.json")));
        bool savedNotice=false; for(auto *label:window.findChildren<QLabel*>()) savedNotice|=label->objectName()=="HistoryDownloadNotice"&&label->text().contains("OS report saved to"); QVERIFY(savedNotice);
        window.discoverBatch(input.path()); auto *nav=button("Batch Analysis"); QVERIFY(nav); nav->click();
        auto plan=retina::batchImagePlan(retina::discoverBatchInput(input.path()),{}); QCOMPARE(plan.size(),2);
        // Exercise the production controller and worker with real selected inputs.
        window.setBatchSnapshot({{"state","Processing"}}); window.batchPlanRequested(plan,output.path(),true);
        QTRY_VERIFY_WITH_TIMEOUT(button("Pause Batch"),5000); button("Pause Batch")->click();
        QTRY_VERIFY_WITH_TIMEOUT(button("Resume Batch"),30000);
        QVERIFY(window.grab().save(qEnvironmentVariable("RETINAGRAM_UI_OUTPUT")+"/batch-real-paused.png"));
        button("Resume Batch")->click();
        // Completion is reported by the real worker; wait for the footer rather than a timer.
        const auto finished=[&] { for(auto *l:window.findChildren<QLabel*>()) if(l->isVisible()&&l->text().startsWith("Batch finished · ")) return true; return false; };
        QTRY_VERIFY_WITH_TIMEOUT(finished(),30000);
        QDirIterator reports(output.path(),{"*.pdf"},QDir::Files,QDirIterator::Subdirectories); int count=0;
        while(reports.hasNext()) { QFile file(reports.next()); QVERIFY(file.open(QIODevice::ReadOnly)); QVERIFY(file.read(5)=="%PDF-"); ++count; } QCOMPARE(count,3);
        QVERIFY(window.grab().save(qEnvironmentVariable("RETINAGRAM_UI_OUTPUT")+"/batch-real-complete.png"));
        // Verify the second folder mode on a completed run. Cancellation may
        // legitimately win before the first image starts and produce no PDF.
        window.setBatchStatus("Batch validation: running");
        window.setBatchSnapshot({{"state","Processing"}}); window.batchPlanRequested(plan,output.path(),false);
        QTRY_VERIFY_WITH_TIMEOUT(finished(),30000);
        QVERIFY(QFileInfo::exists(output.filePath("Patient_001_RH-901_Smoke/Left_OS/RH-901_Smoke_OS_report.pdf")));
        // A third real run confirms cancellation wakes a paused worker cleanly.
        window.setBatchStatus("Batch validation: running");
        window.setBatchSnapshot({{"state","Processing"}}); window.batchPlanRequested(plan,output.path(),false);
        QTRY_VERIFY_WITH_TIMEOUT(button("Pause Batch"),5000); button("Pause Batch")->click();
        QTRY_VERIFY_WITH_TIMEOUT(button("Resume Batch"),30000); QVERIFY(button("Cancel Batch")); button("Cancel Batch")->click();
        const auto cancelled=[&] { for(auto *l:window.findChildren<QLabel*>()) if(l->isVisible()&&l->text().startsWith("Batch cancelled between images.")) return true; return false; };
        QTRY_VERIFY_WITH_TIMEOUT(cancelled(),10000);
        QVERIFY(QFileInfo::exists(output.filePath("RH-901_Smoke/Left_OS/RH-901_Smoke_OS_report.pdf")));
        QVERIFY(QFileInfo::exists(output.filePath("Patient_001_RH-901_Smoke/Left_OS/RH-901_Smoke_OS_report.pdf")));
    }
};
int main(int argc,char **argv) {
    QCoreApplication::setAttribute(Qt::AA_DontUseNativeDialogs);
    QApplication app(argc,argv); QStandardPaths::setTestModeEnabled(true);
    QCoreApplication::setOrganizationName("RetinaGramValidation"); QCoreApplication::setApplicationName(QString("FunctionalSmoke-%1").arg(QCoreApplication::applicationPid()));
    FunctionalSmoke test; return QTest::qExec(&test,argc,argv);
}
#include "FunctionalSmoke.moc"
