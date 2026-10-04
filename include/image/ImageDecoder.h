#pragma once

#include <QImage>
#include <QString>

namespace retina {
// Qt handles common raster formats; Windows Imaging Component covers TIFF.
QImage loadImage(const QString& path, QString* error = nullptr);
}
