#ifndef TEXSTUDIO_PRODUCT_RELEASE_H
#define TEXSTUDIO_PRODUCT_RELEASE_H

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QVector>

namespace TeXstudioProductRelease {
inline QVector<int> version(const QString &tag)
{
    static const QRegularExpression pattern("^v?(\\d+)\\.(\\d+)\\.(\\d+)-espresso-([1-9]\\d*)$");
    const auto match = pattern.match(tag);
    if (!match.hasMatch()) return {};
    QVector<int> result;
    for (int i = 1; i <= 4; ++i) {
        bool ok = false;
        const auto number = match.captured(i).toInt(&ok);
        if (!ok) return {};
        result << number;
    }
    return result;
}

inline QString latest(const QByteArray &bytes, bool includePrereleases)
{
    const auto document = QJsonDocument::fromJson(bytes);
    if (!document.isArray()) return {};
    QString tag;
    QVector<int> newest;
    for (const auto &entry : document.array()) {
        const auto release = entry.toObject();
        if (release["draft"].toBool() || (!includePrereleases && release["prerelease"].toBool())) continue;
        const auto candidate = release["tag_name"].toString();
        const auto parsed = version(candidate);
        if (!parsed.isEmpty() && (newest.isEmpty() || newest < parsed)) {
            newest = parsed; tag = candidate;
        }
    }
    return tag;
}
}
#endif
