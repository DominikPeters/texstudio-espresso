#ifndef TEXPRESSOSURFACE_H
#define TEXPRESSOSURFACE_H
#include <QJsonObject>
#include <QJsonArray>
#include <QRectF>
#include <QSize>
#include <algorithm>
#include <cmath>

// One page-anchored device grid, shared by normal pages and the magnifier.
// The image contains only clip; annotations always refer to the full page.
struct TexpressoSurface
{
    QSize grid;
    QRect clip;
    bool operator==(const TexpressoSurface &other) const { return grid == other.grid && clip == other.clip; }
    bool operator!=(const TexpressoSurface &other) const { return !(*this == other); }
    bool covers(const TexpressoSurface &other) const { return grid == other.grid && clip.contains(other.clip); }
    bool isEmpty() const { return grid.isEmpty() || clip.isEmpty(); }
    QRectF pageRect(const QRectF &bounds) const {
        if (isEmpty() || bounds.isEmpty()) return {};
        const double scale = grid.width() / bounds.width();
        return QRectF(bounds.topLeft() + QPointF(clip.topLeft()) / scale, QSizeF(clip.size()) / scale);
    }
    static TexpressoSurface fromHeader(const QJsonObject &h) {
        const auto g = h["grid"].toArray(), c = h["clip"].toArray();
        return {{g[0].toInt(), g[1].toInt()}, {c[0].toInt(), c[1].toInt(), c[2].toInt() - c[0].toInt(), c[3].toInt() - c[1].toInt()}};
    }
    static QSize pageGrid(int width, const QRectF &bounds) {
        width = std::clamp(width, 1, 65536);
        return {width, int(std::clamp(std::ceil(bounds.height() * width / bounds.width() - 1e-4), 1.0, 2147483647.0))};
    }
    static TexpressoSurface plan(int width, const QRectF &bounds, const QRect &visible = {}, bool overscan = true) {
        const auto grid = pageGrid(width, bounds);
        const QRect paper(QPoint(), grid);
        QRect clip = visible.isEmpty() ? paper : visible.intersected(paper);
        if (clip.isEmpty()) clip = QRect(QPoint(), QSize(1, 1));
        if (!visible.isEmpty() && overscan) {
            // Stable overscan avoids requesting a new raster on every scroll tick.
            const int left = std::max(0, (clip.x() - 256) / 512 * 512);
            const int top = std::max(0, (clip.y() - 256) / 512 * 512);
            const int right = std::min(grid.width(), ((clip.x() + clip.width() + 767) / 512) * 512);
            const int bottom = std::min(grid.height(), int(std::min(qint64(2147483647), (qint64(clip.y()) + clip.height() + 767) / 512 * 512)));
            clip = {left, top, right - left, bottom - top};
        }
        // Preserve density at the native limits. Bound allocation, never scale
        // a very large page down just to fit the raster budget.
        const int w = std::min(clip.width(), 8192);
        const int h = std::min({clip.height(), 8192, 16000000 / w});
        return {grid, QRect(clip.x() + (clip.width() - w) / 2, clip.y() + (clip.height() - h) / 2, w, h)};
    }
};
#endif
