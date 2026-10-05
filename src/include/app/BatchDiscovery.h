#pragma once
#include <QVariantMap>
#include <QMap>

namespace retina {
QVariantMap discoverBatchInput(const QString &directory);
bool batchPatientReady(const QVariantMap &patient,const QMap<QString,QString> &selections);
QVariantList batchImagePlan(const QVariantMap &snapshot,const QMap<QString,QString> &selections);
}
