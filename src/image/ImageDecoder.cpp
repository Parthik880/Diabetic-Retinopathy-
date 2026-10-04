#include "image/ImageDecoder.h"

#include <QFileInfo>
#include <QImageReader>
#include <climits>
#include <utility>

#ifdef _WIN32
#include <windows.h>
#include <wincodec.h>
#include <wrl/client.h>
#endif

namespace retina {
QImage loadImage(const QString& path, QString* error) {
    QImageReader reader(path);
    reader.setAutoTransform(false);
    QImage image = reader.read();
    if (!image.isNull()) return image.convertToFormat(QImage::Format_RGB888);
#ifdef _WIN32
    const QString suffix = QFileInfo(path).suffix();
    if (suffix.compare(QStringLiteral("tif"), Qt::CaseInsensitive) == 0 ||
        suffix.compare(QStringLiteral("tiff"), Qt::CaseInsensitive) == 0) {
        const HRESULT initialized = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        const bool releaseCom = SUCCEEDED(initialized);
        HRESULT status = S_OK;
        {
            using Microsoft::WRL::ComPtr;
            ComPtr<IWICImagingFactory> factory;
            ComPtr<IWICBitmapDecoder> decoder;
            ComPtr<IWICBitmapFrameDecode> frame;
            ComPtr<IWICFormatConverter> converter;
            status = CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER,
                                      IID_PPV_ARGS(factory.GetAddressOf()));
            if (SUCCEEDED(status)) status = factory->CreateDecoderFromFilename(
                path.toStdWString().c_str(), nullptr, GENERIC_READ,
                WICDecodeMetadataCacheOnDemand, decoder.GetAddressOf());
            if (SUCCEEDED(status)) status = decoder->GetFrame(0, frame.GetAddressOf());
            if (SUCCEEDED(status)) status = factory->CreateFormatConverter(converter.GetAddressOf());
            if (SUCCEEDED(status)) status = converter->Initialize(frame.Get(), GUID_WICPixelFormat24bppRGB,
                WICBitmapDitherTypeNone, nullptr, 0.0, WICBitmapPaletteTypeCustom);
            UINT width = 0, height = 0;
            if (SUCCEEDED(status)) status = converter->GetSize(&width, &height);
            if (SUCCEEDED(status) && width > 0 && height > 0 && width <= INT_MAX && height <= INT_MAX) {
                QImage candidate(static_cast<int>(width), static_cast<int>(height), QImage::Format_RGB888);
                if (!candidate.isNull() && static_cast<quint64>(candidate.bytesPerLine()) * height <= UINT_MAX) {
                    status = converter->CopyPixels(nullptr, static_cast<UINT>(candidate.bytesPerLine()),
                        static_cast<UINT>(candidate.bytesPerLine() * height), candidate.bits());
                    if (SUCCEEDED(status)) image = std::move(candidate);
                } else {
                    status = E_OUTOFMEMORY;
                }
            } else if (SUCCEEDED(status)) {
                status = E_INVALIDARG;
            }
        }
        if (releaseCom) CoUninitialize();
        if (!image.isNull()) return image;
        if (error) *error = QStringLiteral("TIFF decode failed (WIC 0x%1)").arg(
            QString::number(static_cast<quint32>(status), 16));
        return {};
    }
#endif
    if (error) *error = reader.errorString();
    return {};
}
}
