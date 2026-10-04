#include "ui/MainWindow.h"
#include "ui/UiComponents.h"
#include "app/BatchDiscovery.h"
#include <QApplication>
#include <QComboBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFile>
#include <QJsonDocument>
#include <QProgressBar>
#include <QRadioButton>
#include <QScrollArea>
#include <QScrollBar>
#include <QSlider>
#include <QTableWidget>
#include <QTemporaryDir>
#include <QCheckBox>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QMenu>
#include <QPushButton>
#include <QSignalSpy>
#include <QStackedWidget>
#include <QStandardPaths>
#include <QTest>
#include <QTimer>

class UiRegression : public QObject {
    Q_OBJECT
private slots:
    void patientGroupedHistoryAndFilters() {
        QCoreApplication::setApplicationName(QString("HistorySmoke-%1").arg(QCoreApplication::applicationPid()));
        const QString fixtureImage = qEnvironmentVariable("RETINAGRAM_TEST_IMAGE");
        const auto eyeState = [&fixtureImage](bool complete, int grade) {
            QVariantMap result;
            if (complete) result = {{"state", "COMPLETE"}, {"grade", grade}, {"image_path", fixtureImage}};
            return QVariantMap{{"imagePath", complete ? fixtureImage : QString()}, {"result", result}, {"stage", ""}, {"error", ""}};
        };
        QVariantList sessions;
        const QDateTime now = QDateTime::currentDateTime();
        const auto addSession = [&sessions, &eyeState](QString id, QString name, int daysAgo, bool os, bool od) {
            const QVariantMap patient{{"details", QVariantMap{{"id", id}, {"patientIdNumber", id}, {"name", name}}},
                                      {"os", eyeState(os, 2)}, {"od", eyeState(od, 1)}};
            sessions.append(QVariantMap{{"patient", patient}, {"savedAt", QDateTime::currentDateTime().addDays(-daysAgo).toString(Qt::ISODateWithMs)}});
        };
        addSession("RH-101", "Bird Patient", 0, true, false);
        addSession("RH-101", "Bird Patient", 2, true, true);
        addSession("RH-101", "Bird Patient", 40, false, true);
        addSession("RH-102", "Left Only", 0, true, false);
        addSession("RH-103", "Right Only", 6, false, true);
        addSession("RH-104", "Both Eyes", 20, true, true);
        addSession("RH-105", "Future Session", -1, true, false);
        addSession("RH-106", "Saved Only", 3, false, false);
        for (int index = 0; index < 12; ++index)
            addSession(QString("RH-%1").arg(200 + index), QString("Patient %1").arg(index), index % 29, index % 2 == 0, index % 3 == 0);
        QVERIFY(!sessions.isEmpty());
        QVERIFY(now.isValid());
        const QString dataFolder = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
        QVERIFY(QDir().mkpath(dataFolder));
        QFile state(QDir(dataFolder).filePath("session.json"));
        QVERIFY(state.open(QIODevice::WriteOnly));
        state.write(QJsonDocument::fromVariant(QVariantMap{{"patients", QVariantList{}}, {"history", sessions}, {"currentPatient", -1}}).toJson());
        state.close();

        retina::MainWindow window;
        window.resize(1440, 960);
        window.show();
        QCoreApplication::processEvents();
        const QString output = qEnvironmentVariable("RETINAGRAM_UI_OUTPUT");
        const auto visibleButton = [&window](const QString &name) -> QPushButton* {
            for (auto *candidate : window.findChildren<QPushButton*>())
                if (candidate->isVisible() && (candidate->objectName() == name || candidate->accessibleName() == name || candidate->text() == name)) return candidate;
            return nullptr;
        };
        const auto click = [&](const QString &name) {
            auto *candidate = visibleButton(name);
            if (!candidate) return false;
            QTest::mouseClick(candidate, Qt::LeftButton);
            QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
            QCoreApplication::processEvents();
            return true;
        };
        QVERIFY(click("History"));
        auto *table = window.findChild<QTableWidget*>("PatientHistoryTable");
        QVERIFY(table);
        QCOMPARE(table->columnCount(), 6);
        QCOMPARE(table->rowCount(), 10);
        QCOMPARE(table->horizontalHeaderItem(2)->text(), QString("Last scan"));
        QCOMPARE(table->horizontalHeaderItem(3)->text(), QString("Sessions"));
        QVERIFY(!visibleButton("View Selected Report"));
        QVERIFY(window.findChild<QLabel*>("HistorySummary")->text().contains("18 patients · 20 sessions"));
        QVERIFY(window.findChild<QPushButton*>("HistoryNext")->isEnabled());
        QVERIFY(window.grab().save(output + "/history-master-detail-1440x960.png"));
        QVERIFY(window.findChild<QLabel*>("SelectedHistoryPatientName") == nullptr);
        bool emptyDetail = false;
        for (auto *item : window.findChildren<QLabel*>()) emptyDetail |= item->text() == "Select a patient";
        QVERIFY(emptyDetail);

        QVERIFY(click("View history: RH-101"));
        QCOMPARE(window.findChild<QFrame*>("HistorySessionCard")->property("sessionId").toString().size() > 6, true);
        QCOMPARE(window.findChildren<QFrame*>("HistorySessionCard").size(), 3);
        QVERIFY(window.findChild<QLabel*>("SelectedHistoryPatientName")->text() == "Bird Patient");
        QVERIFY(window.findChild<QScrollArea*>("PatientSessions"));
        bool osGrade = false, odGrade = false;
        for (auto *item : window.findChildren<QLabel*>()) { osGrade |= item->text() == "OS: Grade 2"; odGrade |= item->text() == "OD: Grade 1"; }
        QVERIFY(osGrade); QVERIFY(odGrade);
        QVERIFY(window.grab().save(output + "/history-selected-patient-1440x960.png"));
        const auto sessionCards = window.findChildren<QFrame*>("HistorySessionCard");
        const QString bothEyesSession = sessionCards.at(1)->property("sessionId").toString();
        QVERIFY(click(QStringLiteral("View Reports: %1").arg(bothEyesSession)));
        QVERIFY(window.findChild<QStackedWidget*>()->currentIndex() == 3);
        bool historicPatientInReport = false;
        for (auto *item : window.findChildren<QLabel*>()) historicPatientInReport |= item->text() == "Bird Patient";
        QVERIFY(historicPatientInReport);
        QVERIFY(click("History"));
        QVERIFY(click("View history: RH-101"));
        QSignalSpy historyDownload(&window, &retina::MainWindow::historyReportDownloadRequested);
        auto *twoEyeDownload = window.findChild<QPushButton*>(QStringLiteral("HistoryDownload_%1").arg(bothEyesSession));
        QVERIFY(twoEyeDownload);
        QTest::mouseClick(twoEyeDownload, Qt::LeftButton);
        QCoreApplication::processEvents();
        auto *downloadMenu = window.findChild<QMenu*>("HistoryDownloadMenu");
        QVERIFY(downloadMenu);
        QCOMPARE(downloadMenu->actions().size(), 2);
        QCOMPARE(downloadMenu->actions().at(0)->text(), QString("Download Left Eye Report"));
        QCOMPARE(downloadMenu->actions().at(1)->text(), QString("Download Right Eye Report"));
        QTimer::singleShot(100, [output] {
            auto *dialog = qobject_cast<QFileDialog*>(QApplication::activeModalWidget());
            if (!dialog) return;
            dialog->setDirectory(output);
            QTimer::singleShot(250, dialog, [dialog] { QMetaObject::invokeMethod(dialog, "accept", Qt::DirectConnection); });
        });
        downloadMenu->actions().at(1)->trigger();
        QCOMPARE(historyDownload.count(), 1);
        QCOMPARE(historyDownload.last().at(1).toString(), QString("OD"));
        QCOMPARE(historyDownload.last().at(2).toMap().value("grade").toInt(), 1);
        QCOMPARE(QDir(historyDownload.last().at(3).toString()).absolutePath(), QDir(output).absolutePath());
        auto *search = window.findChild<QLineEdit*>("HistorySearch");
        QVERIFY(search);
        search->setText("RH-104");
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        table = window.findChild<QTableWidget*>("PatientHistoryTable");
        QCOMPARE(table->rowCount(), 1);
        QCOMPARE(table->item(0, 1)->text(), QString("#RH-104"));
        QVERIFY(window.findChild<QLabel*>("SelectedHistoryPatientName")->text() == "Bird Patient"); // Detail keeps every session when filters hide its row.

        search = window.findChild<QLineEdit*>("HistorySearch"); search->clear();
        auto *date = window.findChild<QComboBox*>("HistoryDateFilter"); QVERIFY(date);
        date->setCurrentIndex(1); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        table = window.findChild<QTableWidget*>("PatientHistoryTable");
        QVERIFY(table->rowCount() >= 2);
        bool birdRow = false;
        bool futureRow = false;
        for (int row = 0; row < table->rowCount(); ++row) { futureRow |= table->item(row, 1)->text() == "#RH-105"; if (table->item(row, 1)->text() == "#RH-101") { birdRow = true; QCOMPARE(table->item(row, 3)->text(), QString("3 sessions")); } }
        QVERIFY(birdRow);
        QVERIFY(!futureRow);
        date = window.findChild<QComboBox*>("HistoryDateFilter"); date->setCurrentIndex(2); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        search = window.findChild<QLineEdit*>("HistorySearch"); search->setText("RH-103"); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        table = window.findChild<QTableWidget*>("PatientHistoryTable");
        QCOMPARE(table->rowCount(), 1);
        bool withinSeven = false, beyondSeven = false;
        for (int row = 0; row < table->rowCount(); ++row) { withinSeven |= table->item(row,1)->text() == "#RH-103"; beyondSeven |= table->item(row,1)->text() == "#RH-104"; }
        QVERIFY(withinSeven); QVERIFY(!beyondSeven);
        search = window.findChild<QLineEdit*>("HistorySearch"); search->clear(); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        date = window.findChild<QComboBox*>("HistoryDateFilter"); date->setCurrentIndex(3); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        search = window.findChild<QLineEdit*>("HistorySearch"); search->setText("RH-104"); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        table = window.findChild<QTableWidget*>("PatientHistoryTable");
        QCOMPARE(table->rowCount(), 1);
        bool withinThirty = false;
        for (int row = 0; row < table->rowCount(); ++row) withinThirty |= table->item(row,1)->text() == "#RH-104";
        QVERIFY(withinThirty);
        search = window.findChild<QLineEdit*>("HistorySearch"); search->clear(); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        auto *eye = window.findChild<QComboBox*>("HistoryEyeFilter"); QVERIFY(eye);
        eye->setCurrentIndex(1); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        table = window.findChild<QTableWidget*>("PatientHistoryTable");
        bool leftPresent = false, rightOnlyPresent = false;
        for (int row = 0; row < table->rowCount(); ++row) { leftPresent |= table->item(row,1)->text() == "#RH-102"; rightOnlyPresent |= table->item(row,1)->text() == "#RH-103"; }
        QVERIFY(leftPresent); QVERIFY(!rightOnlyPresent);
        eye = window.findChild<QComboBox*>("HistoryEyeFilter"); eye->setCurrentIndex(2); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        table = window.findChild<QTableWidget*>("PatientHistoryTable");
        bool rightPresent = false;
        for (int row = 0; row < table->rowCount(); ++row) rightPresent |= table->item(row,1)->text() == "#RH-103";
        QVERIFY(rightPresent);
        eye = window.findChild<QComboBox*>("HistoryEyeFilter"); eye->setCurrentIndex(3); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        table = window.findChild<QTableWidget*>("PatientHistoryTable");
        for (int row = 0; row < table->rowCount(); ++row) QVERIFY(table->item(row,1)->text() != "#RH-102" && table->item(row,1)->text() != "#RH-103");
        eye = window.findChild<QComboBox*>("HistoryEyeFilter"); eye->setCurrentIndex(0);
        date = window.findChild<QComboBox*>("HistoryDateFilter"); date->setCurrentIndex(0);
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        QVERIFY(click("History Next"));
        QVERIFY(window.findChild<QLabel*>("HistoryPage")->text().contains("Page 2 of 2"));
        QVERIFY(!window.findChild<QPushButton*>("HistoryNext")->isEnabled());
        QVERIFY(window.findChild<QPushButton*>("HistoryPrevious")->isEnabled());
        search = window.findChild<QLineEdit*>("HistorySearch"); search->setText("not-a-patient");
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        QVERIFY(!window.findChild<QTableWidget*>("PatientHistoryTable"));
        bool noResults = false;
        for (auto *item : window.findChildren<QLabel*>()) noResults |= item->text() == "No patients found";
        QVERIFY(noResults);
        search = window.findChild<QLineEdit*>("HistorySearch"); search->clear(); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        search = window.findChild<QLineEdit*>("HistorySearch"); QVERIFY(search); window.activateWindow(); search->setFocus(); QCoreApplication::processEvents();
        for (const QChar character : QStringLiteral("RH-106")) {
            auto *focusedSearch = qobject_cast<QLineEdit*>(QApplication::focusWidget());
            QVERIFY(focusedSearch);
            QTest::keyClick(focusedSearch, character.toUpper().unicode());
            QCoreApplication::processEvents();
        }
        search = window.findChild<QLineEdit*>("HistorySearch");
        QVERIFY(search);
        QCOMPARE(search->text(), QStringLiteral("RH-106"));
        search->clear(); QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete); QCoreApplication::processEvents();
        QVERIFY(click("View history: RH-106"));
        bool savedStatus = false; for (auto *item : window.findChildren<QLabel*>()) savedStatus |= item->text() == "Saved session";
        QVERIFY(savedStatus);
        auto *savedCard = window.findChild<QFrame*>("HistorySessionCard"); QVERIFY(savedCard);
        auto *savedDownload = savedCard->findChild<QPushButton*>(QStringLiteral("HistoryDownload_%1").arg(savedCard->property("sessionId").toString()));
        QVERIFY(savedDownload);
        QVERIFY(!savedDownload->isEnabled());
        QVERIFY(window.findChild<QScrollArea*>("PatientSessions"));
        window.resize(800,900); QCoreApplication::processEvents();
        QVERIFY(window.grab().save(output + "/history-stacked-800x900.png"));
    }

    void damagedHistoryStoreIsPreserved() {
        QCoreApplication::setApplicationName(QString("HistoryErrorSmoke-%1").arg(QCoreApplication::applicationPid()));
        const QString dataFolder = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
        QVERIFY(QDir().mkpath(dataFolder));
        const QString path = QDir(dataFolder).filePath("session.json");
        const QByteArray original("damaged local history fixture\n");
        QFile file(path);
        QVERIFY(file.open(QIODevice::WriteOnly));
        QCOMPARE(file.write(original), qint64(original.size()));
        file.close();

        retina::MainWindow window;
        window.resize(1440, 960);
        window.show();
        QCoreApplication::processEvents();
        QPushButton *history = nullptr;
        for (auto *candidate : window.findChildren<QPushButton*>())
            if (candidate->isVisible() && candidate->accessibleName() == "History") history = candidate;
        QVERIFY(history);
        history->click();
        QCoreApplication::processEvents();
        auto *error = window.findChild<QLabel*>("HistoryError");
        QVERIFY(error);
        QVERIFY(error->text().contains("local session file could not be read"));
        QVERIFY(file.open(QIODevice::ReadOnly));
        QCOMPARE(file.readAll(), original);
    }

    void analysisLayersAndRegionSelection() {
        QCoreApplication::setApplicationName(QString("AnalysisSmoke-%1").arg(QCoreApplication::applicationPid()));
        retina::MainWindow window; window.resize(1426,952); window.show();
        QFile file(qEnvironmentVariable("RETINAGRAM_TEST_RESULT")); QVERIFY(file.open(QIODevice::ReadOnly));
        auto result=QJsonDocument::fromJson(file.readAll()).toVariant().toMap();
        window.setPatient({{"name","Analysis Smoke Patient"},{"patientIdNumber","RH-TEST"}}); window.setEyeResult("OS",result);
        const auto button=[&](QString name) -> QPushButton* { for(auto *b:window.findChildren<QPushButton*>()) if(b->isVisible()&&(b->accessibleName()==name||b->text()==name)) return b; return nullptr; };
        const auto click=[&](QString name) { auto *b=button(name); if(!b) return false; QTest::mouseClick(b,Qt::LeftButton); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents(); return true; };
        const auto stage=[&]() -> retina::ui::ImageStage* { for(auto *w:window.findChildren<QWidget*>("ImageStage")) if(w->isVisible()) return static_cast<retina::ui::ImageStage*>(w); return nullptr; };
        const auto save=[&](QString name) { QCoreApplication::processEvents(); return window.grab().save(qEnvironmentVariable("RETINAGRAM_UI_OUTPUT")+"/"+name+".png"); };
        const auto saveLegend=[&](QString name) { auto *stack=window.findChild<QStackedWidget*>(); auto *scroll=qobject_cast<QScrollArea*>(stack->currentWidget()); if(!scroll) return false; scroll->verticalScrollBar()->setValue(400); const bool saved=save(name); scroll->verticalScrollBar()->setValue(0); return saved; };
        QVERIFY(click("Analysis")); QVERIFY(stage());
        QVERIFY(window.findChild<QProgressBar*>()); QVERIFY(save("analysis-grade"));
        QVERIFY(click("Lesion Probability"));
        auto *type=window.findChild<QComboBox*>("LesionType"); QVERIFY(type); QCOMPARE(type->count(),4); QCOMPARE(type->currentData().toString(),QString("HE"));
        QVERIFY(button("Lesion visualization mechanism: Probability")->isChecked());
        QVERIFY(button("Lesion image mode: Overlay")->isChecked());
        auto he=stage()->image; type->setCurrentIndex(type->findData("MA")); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents(); QVERIFY(he!=stage()->image);
        type=window.findChild<QComboBox*>("LesionType"); type->setCurrentIndex(type->findData("HE")); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents();
        auto *slider=window.findChild<QSlider*>(); QVERIFY(slider); slider->setValue(73); QCOMPARE(window.findChild<QLabel*>("OpacityPercentage")->text(),QString("73%")); QVERIFY(he!=stage()->image); slider->setValue(50);
        QVERIFY(save("analysis-probability"));
        QVERIFY(saveLegend("analysis-probability-legend"));
        QVERIFY(click("Lesion visualization mechanism: Grad-CAM")); QVERIFY(stage()->status.contains("unavailable")); QVERIFY(button("Lesion image mode: Grad-CAM")); QVERIFY(save("analysis-lesion-cam-unavailable"));
        QVERIFY(click("Lesion Annotation"));
        int masks=0; for(auto *c:window.findChildren<QCheckBox*>()) if(c->isVisible()&&c->accessibleName().startsWith("Visible lesion mask")) ++masks; QCOMPARE(masks,4);
        auto withMasks=stage()->image;
        for(const auto &code:QStringList{"MA","HE","EX","SE"}) {
            QCheckBox *check=nullptr; for(auto *c:window.findChildren<QCheckBox*>()) if(c->isVisible()&&c->accessibleName()=="Visible lesion mask: "+code) check=c;
            QVERIFY(check); check->setChecked(false); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents();
        }
        QVERIFY(withMasks!=stage()->image);
        for(const auto &code:QStringList{"MA","HE","EX","SE"}) { for(auto *c:window.findChildren<QCheckBox*>()) if(c->isVisible()&&c->accessibleName()=="Visible lesion mask: "+code) { c->setChecked(true); break; } QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents(); }
        QVERIFY(save("analysis-annotation"));
        QVERIFY(saveLegend("analysis-annotation-legend"));
        QVERIFY(click("Lesion Detection")); QVERIFY(!window.findChild<QSlider*>()); QVERIFY(button("Detection mode: Boxes")); QVERIFY(button("Detection mode: Coordinates"));
        auto cards=window.findChildren<QFrame*>("RegionCard"); QCOMPARE(cards.size(),25); QVERIFY(save("analysis-detection"));
        auto id=cards.first()->property("regionId").toString(); QTest::keyClick(cards.first(),Qt::Key_Return); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents();
        bool selected=false; for(auto *c:window.findChildren<QFrame*>("RegionCard")) if(c->property("regionId").toString()==id) selected=c->property("selected").toBool(); QVERIFY(selected);
        QVERIFY(click("Detection mode: Coordinates"));
        auto *stack=window.findChild<QStackedWidget*>(); auto *scroll=qobject_cast<QScrollArea*>(stack->currentWidget()); QVERIFY(scroll); scroll->verticalScrollBar()->setValue(950); QVERIFY(save("analysis-region-cards")); scroll->verticalScrollBar()->setValue(0);
        QCheckBox *raw=nullptr; for(auto *c:window.findChildren<QCheckBox*>()) if(c->isVisible()&&c->text()=="View all raw model regions") raw=c; QVERIFY(raw); raw->setChecked(true);
        QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents(); QCOMPARE(window.findChildren<QFrame*>("RegionCard").size(),result.value("raw_regions").toList().size());
        QVERIFY(!window.findChild<QComboBox*>("RegionClass")->isEnabled());
        window.resize(800,900); QCoreApplication::processEvents(); QVERIFY(save("analysis-medium-800x900"));
    }
    void batchReviewAndConditionalStates() {
        QCoreApplication::setApplicationName(QString("BatchSmoke-%1").arg(QCoreApplication::applicationPid()));
        retina::MainWindow window; window.resize(1426,952); window.show();
        const auto button=[&](QString name) -> QPushButton* { for(auto *b:window.findChildren<QPushButton*>()) if(b->isVisible()&&(b->text()==name||b->accessibleName()==name)) return b; return nullptr; };
        const auto click=[&](QString name) { auto *b=button(name); if(!b) return false; QTest::mouseClick(b,Qt::LeftButton); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents(); return true; };
        const auto save=[&](QString name) { QCoreApplication::processEvents(); return window.grab().save(qEnvironmentVariable("RETINAGRAM_UI_OUTPUT")+"/"+name+".png"); };
        QVERIFY(click("Batch Analysis")); QVERIFY(window.findChild<QFrame*>("BatchWorkflow")); QVERIFY(!window.findChild<QTableWidget*>("BatchPatientTable")); QVERIFY(!button("View Patient List")->isEnabled()); QVERIFY(save("batch-initial"));
        window.setBusy(true); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents(); QVERIFY(!button("Choose Folder")->isEnabled()); window.setBusy(false); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents(); QVERIFY(button("Choose Folder")->isEnabled());
        QTemporaryDir input; QVERIFY(input.isValid()); QString image=qEnvironmentVariable("RETINAGRAM_TEST_IMAGE");
        QVERIFY(QFile::copy(image,input.filePath("RH-100_Alice_OS.jpg"))); QVERIFY(QFile::copy(image,input.filePath("RH-100_Alice_OD.jpg")));
        QVERIFY(QFile::copy(image,input.filePath("RH-200_Bob_OS.jpg"))); QVERIFY(QFile::copy(image,input.filePath("RH-200_Bob_OS_2.jpg")));
        QFile invalid(input.filePath("unknown.jpg")); QVERIFY(invalid.open(QIODevice::WriteOnly)); invalid.write("unreadable"); invalid.close();
        auto snapshot=retina::discoverBatchInput(input.path()); QCOMPARE(snapshot.value("patients").toList().size(),2); QCOMPARE(snapshot.value("counts").toMap().value("needs_review").toInt(),1); QCOMPARE(snapshot.value("invalid_items").toList().size(),1);
        QTemporaryDir emptyPatient; QVERIFY(QDir(emptyPatient.path()).mkdir("RH-300_Empty")); auto emptySnapshot=retina::discoverBatchInput(emptyPatient.path()); QCOMPARE(emptySnapshot.value("patients").toList().size(),1); QCOMPARE(emptySnapshot.value("patients").toList().first().toMap().value("discovery_status").toString(),QString("INVALID")); QVERIFY(retina::batchImagePlan(emptySnapshot,{}).isEmpty());
        window.setBatchCapacity({{"available",true},{"name","UI test capacity fixture"},{"vram_mb",8192},{"max_batch_size",90}});
        window.discoverBatch(input.path()); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents(); QVERIFY(!window.findChild<QTableWidget*>("BatchPatientTable"));
        QVERIFY(click("View Patient List")); auto *table=window.findChild<QTableWidget*>("BatchPatientTable"); QVERIFY(table); QCOMPARE(table->columnCount(),7); QCOMPARE(table->rowCount(),2);
        auto radios=table->findChildren<QRadioButton*>(); QCOMPARE(radios.size(),2); QTest::mouseClick(radios.first(),Qt::LeftButton); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents();
        QVERIFY(click("Discovery log")); QVERIFY(save("batch-discovery"));
        QSignalSpy control(&window,&retina::MainWindow::batchControlRequested);
        window.setBatchSnapshot({{"state","Processing"},{"stage_label","GRADE_INFERENCE"},{"progress_percent",40},{"counts",QVariantMap{{"completed",1},{"processing",1}}}}); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents();
        QVERIFY(window.findChild<QFrame*>("BatchProgress")); QVERIFY(click("Pause Batch")); QCOMPARE(control.count(),1); QCOMPARE(control.last()[0].toString(),QString("pause")); QVERIFY(save("batch-processing"));
        window.setBatchSnapshot({{"state","Paused"}}); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); QCoreApplication::processEvents(); QVERIFY(click("Resume Batch")); QVERIFY(click("Cancel Batch")); QCOMPARE(control.count(),3);
        window.resize(800,900); QCoreApplication::processEvents(); QVERIFY(save("batch-medium-800x900"));
    }
    void patientWorkflowAndAllPages() {
        QCoreApplication::setApplicationName(QString("UISmoke-%1").arg(QCoreApplication::applicationPid()));
        retina::MainWindow window;
        window.resize(1426, 952);
        window.show();
        QVERIFY(QTest::qWaitForWindowExposed(&window));
        const QString output = qEnvironmentVariable("RETINAGRAM_UI_OUTPUT");
        QVERIFY(QDir().mkpath(output));
        QTimer watchdog;
        watchdog.setInterval(5000);
        connect(&watchdog, &QTimer::timeout, [] {
            if (auto *dialog = qobject_cast<QDialog*>(QApplication::activeModalWidget())) dialog->reject();
        });
        watchdog.start();
        const auto visibleButton = [&window](const QString &name) -> QPushButton * {
            for (auto *item : window.findChildren<QPushButton*>())
                if (item->isVisible() && (item->text() == name || item->accessibleName() == name)) return item;
            return nullptr;
        };
        const auto click = [&](const QString &name) {
            auto *item = visibleButton(name);
            if (!item) return false;
            QTest::mouseClick(item, Qt::LeftButton);
            QCoreApplication::processEvents();
            return true;
        };
        // Register through the real modal, using a unique test-only data root.
        bool registrationOpened = false;
        QTimer::singleShot(100, [&] {
            auto *dialog = qobject_cast<QDialog*>(QApplication::activeModalWidget());
            if (!dialog) return;
            registrationOpened = dialog->windowTitle() == QStringLiteral("New Patient Registration");
            dialog->findChildren<QLineEdit*>()[0]->setText(QStringLiteral("UI Smoke Patient"));
            dialog->grab().save(output + "/new-patient.png");
            QTest::mouseClick(dialog->findChild<QDialogButtonBox*>()->button(QDialogButtonBox::Save), Qt::LeftButton);
        });
        QVERIFY(click(QStringLiteral("Register patient")));
        QVERIFY(registrationOpened);
        auto *selector = window.findChild<QComboBox*>(QStringLiteral("PatientSelector"));
        QVERIFY(selector);
        QCOMPARE(selector->count(), 1);
        QCOMPARE(window.size(), QSize(1426, 952));
        QVERIFY(window.grab().save(output + "/capture-empty-1426x952.png"));
        int cloudActions = 0;
        for (auto *item : window.findChildren<QPushButton*>())
            if (item->text() == "Cloud Sync") ++cloudActions;
        QCOMPARE(cloudActions, 1);
        // A valid top-level construction and all seven page transitions guard the startup regression.
        const QStringList pages{"Capture", "Analysis", "Compare", "Report", "History", "Batch Analysis", "Cloud Sync"};
        auto *stack = window.findChild<QStackedWidget*>();
        QVERIFY(stack);
        for (int index = 0; index < pages.size(); ++index) {
            QVERIFY2(click(pages[index]), qPrintable(pages[index]));
            QCOMPARE(stack->currentIndex(), index);
            QVERIFY(window.isVisible());
            QVERIFY(window.grab().save(output + QStringLiteral("/page-%1-1426x952.png").arg(index)));
        }
        QVERIFY(click("Capture"));
        bool cancelOpened = false;
        QTimer::singleShot(100, [&] {
            auto *dialog = qobject_cast<QDialog*>(QApplication::activeModalWidget());
            if (!dialog) return;
            cancelOpened = true;
            dialog->reject();
        });
        QVERIFY(click("New Patient"));
        QVERIFY(cancelOpened);
        QCOMPARE(selector->count(), 1);
        // Exercise the actual import dialog, decoder and managed copy.
        const QString image = qEnvironmentVariable("RETINAGRAM_TEST_IMAGE");
        QVERIFY(QFileInfo::exists(image));
        bool importOpened = false;
        QTimer::singleShot(100, [&] {
            auto *dialog = qobject_cast<QFileDialog*>(QApplication::activeModalWidget());
            if (!dialog) return;
            importOpened = true;
            dialog->setDirectory(QFileInfo(image).absolutePath());
            QTimer::singleShot(250, dialog, [dialog, image, output] {
                // QFileSystemModel populates asynchronously; fill the dialog's
                // filename field after it has initialized, then use its real accept path.
                auto *filename = dialog->findChild<QLineEdit*>(QStringLiteral("fileNameEdit"));
                if (!filename) { dialog->reject(); return; }
                filename->setText(image);
                dialog->grab().save(output + "/image-import.png");
                QMetaObject::invokeMethod(dialog, "accept", Qt::DirectConnection);
            });
        });
        QVERIFY(click(QStringLiteral("＋  Tap to Capture Image")));
        QVERIFY(importOpened);
        auto previews = window.findChildren<QLabel*>(QStringLiteral("CapturePreview"));
        QCOMPARE(previews.size(), 1);
        QCOMPARE(previews[0]->size(), QSize(320, 320));
        QVERIFY(!previews[0]->pixmap().isNull());
        QVERIFY(window.grab().save(output + "/capture-loaded-1426x952.png"));
        QSignalSpy analysis(&window, &retina::MainWindow::analyzeRequested);
        QVERIFY(click("Analyze Retinal Images"));
        QCOMPARE(analysis.count(), 1);
        QCOMPARE(analysis[0][0].toString(), QStringLiteral("OS"));
        QVERIFY(QFileInfo::exists(analysis[0][1].toString()));
        QVERIFY(!visibleButton("Analyzing retinal images…")->isEnabled());
        window.setBusy(false);
        bool sessionOpened = false;
        QTimer::singleShot(100, [&] {
            auto *dialog = qobject_cast<QMessageBox*>(QApplication::activeModalWidget());
            if (!dialog) return;
            sessionOpened = true;
            dialog->grab().save(output + "/new-session.png");
            QTest::mouseClick(dialog->button(QMessageBox::Cancel), Qt::LeftButton);
        });
        QVERIFY(click("New Session"));
        QVERIFY(sessionOpened);
        QCOMPARE(window.findChildren<QLabel*>(QStringLiteral("CapturePreview")).size(), 1);
        QTimer::singleShot(100, [] {
            if (auto *dialog = qobject_cast<QMessageBox*>(QApplication::activeModalWidget()))
                QTest::mouseClick(dialog->button(QMessageBox::Ok), Qt::LeftButton);
        });
        QVERIFY(click("New Session"));
        QCOMPARE(window.findChildren<QLabel*>(QStringLiteral("CapturePreview")).size(), 0);
        QSignalSpy patients(&window, &retina::MainWindow::patientChanged);
        window.setPatient({{"id", "UI-SECOND"}, {"patientIdNumber", "UI-SECOND"}, {"name", "UI Second Patient"}});
        QCOMPARE(selector->count(), 2);
        selector->setCurrentIndex(0);
        QCOMPARE(patients.count(), 1);
        QVERIFY(selector->currentText().contains("UI Smoke Patient"));
        window.resize(1920, 1080);
        QCoreApplication::processEvents();
        QCOMPARE(window.size(), QSize(1920, 1080));
        QVERIFY(window.grab().save(output + "/capture-empty-1920x1080.png"));
        QVERIFY(click("Cloud Sync"));
        QVERIFY(window.grab().save(output + "/cloud-1920x1080.png"));
        qInfo() << "Isolated UI data:" << QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    }
};

int main(int argc, char **argv) {
    QCoreApplication::setAttribute(Qt::AA_DontUseNativeDialogs);
    QApplication application(argc, argv);
    QStandardPaths::setTestModeEnabled(true);
    QCoreApplication::setOrganizationName("RetinaGramValidation");
    QCoreApplication::setApplicationName(QStringLiteral("UISmoke-%1").arg(QCoreApplication::applicationPid()));
    UiRegression test;
    return QTest::qExec(&test, argc, argv);
}

#include "UiRegression.moc"
