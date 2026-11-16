#ifndef TEXPRESSO_TEST_SURFACE_FIXTURE_H
#define TEXPRESSO_TEST_SURFACE_FIXTURE_H
#include "texpressopreview.h"
#include <QBuffer>

// Small, deterministic fake-engine responses obey the production surface wire
// format too. The caller chooses page geometry and pixels, not a legacy mode.
inline QJsonObject testSurfaceHeader(QJsonObject header, const QJsonArray &request)
{
    const auto b = header["bounds"].toArray();
    const QRectF bounds(QPointF(b[0].toDouble(), b[1].toDouble()), QPointF(b[2].toDouble(), b[3].toDouble()));
    const auto grid = TexpressoSurface::pageGrid(request[3].toInt(), bounds);
    const QRect clip = QRect(request[6].toInt(), request[7].toInt(), request[8].toInt() - request[6].toInt(), request[9].toInt() - request[7].toInt()).intersected(QRect(QPoint(), grid));
    header["grid"] = QJsonArray{grid.width(), grid.height()};
    header["clip"] = QJsonArray{clip.x(), clip.y(), clip.x() + clip.width(), clip.y() + clip.height()};
    header["width"] = clip.width(); header["height"] = clip.height();
    if (!header.contains("rasterId")) header["rasterId"] = request[1];
    return header;
}
inline void receiveTestSurface(TexpressoPreview &preview, const QJsonArray &request, QJsonObject header, QByteArray bytes)
{
    header = testSurfaceHeader(header, request);
    if (!header.contains("patch")) {
        auto image = QImage::fromData(bytes, "PNG").scaled(header["width"].toInt(), header["height"].toInt());
        bytes.clear(); QBuffer buffer(&bytes); buffer.open(QIODevice::WriteOnly); image.save(&buffer, "PNG");
        header["byteLength"] = bytes.size();
    }
    preview.receive(header, bytes);
}
#endif
