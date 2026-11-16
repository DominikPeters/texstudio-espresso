#include <QtTest>
#include "surface_fixture.h"
#include "texpressopreview.h"
#include "texpressoprocess.h"
#include "texpressoprotocol.h"
#include "texpressowidget.h"
#include <QBuffer>
#include <QTemporaryDir>
#include <QFile>
#include <QScopeGuard>

class RenderingTest : public QObject
{
    Q_OBJECT
private slots:
    void surfacePlanning();
    void viewportScrollReuse();
    void croppedCanvasPlacement();
    void patchesAndKeyframeRecovery();
    void latestRegionAndSourceFence();
    void surfaceCommand();
    void asynchronousMagnifier();
    void externalBuildDisablesInteractions();
    void realEngine();
    void cachedInverseUsesPublishedSourceMap();
    void preciseCachedSourceSearch();
    void retinaResolution();
};
void RenderingTest::surfacePlanning()
{
    const QRectF page(10, 20, 600, 900);
    const auto large = TexpressoSurface::plan(24000, page, QRect(17000, 22000, 1400, 1000));
    QCOMPARE(large.grid, QSize(24000, 36000));
    QVERIFY(large.clip.contains(QRect(17000, 22000, 1400, 1000)));
    QVERIFY(qint64(large.clip.width()) * large.clip.height() <= TexpressoProtocol::maxPixels);
    const auto capped = TexpressoSurface::plan(65536, page);
    QCOMPARE(capped.grid.width(), 65536); // The allocation cap never lowers density.
    QVERIFY(capped.clip.width() <= 8192 && capped.clip.height() <= 8192);
    QVERIFY(qint64(capped.clip.width()) * capped.clip.height() <= TexpressoProtocol::maxPixels);
    const auto points = large.pageRect(page);
    QCOMPARE(points.topLeft(), page.topLeft() + QPointF(large.clip.topLeft()) / 40);
}
void RenderingTest::viewportScrollReuse()
{
    TexpressoPreview preview; QSignalSpy commands(&preview, &TexpressoPreview::command);
    preview.setViewport({{0, 12000, QRect(7000, 9000, 600, 700)}});
    preview.setActive(true); preview.message({"preview-state", 1, 0, 1, true, 0});
    const auto reply = [&](const QJsonArray &request, Qt::GlobalColor color) {
        QImage image(2, 2, QImage::Format_RGB32); image.fill(color);
        QByteArray bytes; QBuffer buffer(&bytes); buffer.open(QIODevice::WriteOnly); image.save(&buffer, "PNG");
        receiveTestSurface(preview, request, {{"requestId", request[1]}, {"revision", 1}, {"sequence", 0}, {"page", 0},
            {"bounds", QJsonArray{0, 0, 600, 900}}, {"mime", "image/png"}, {"byteLength", bytes.size()}}, bytes);
    };
    const auto first = commands.last()[0].toJsonArray(); reply(first, Qt::red);
    QTRY_VERIFY(preview.valid());
    QCOMPARE(preview.surface().grid, QSize(12000, 18000));
    QVERIFY(preview.image().height() < 2000);
    const auto retained = preview.image(); const auto sent = commands.size();
    preview.setViewport({{0, 12000, QRect(7040, 9040, 600, 700)}});
    QCOMPARE(commands.size(), sent); // Reuse overscan during ordinary scrolling.
    preview.setViewport({{0, 12000, QRect(2000, 3000, 600, 700)}});
    QCOMPARE(commands.size(), sent + 1);
    QCOMPARE(preview.image(), retained); // Keep the last good surface while waiting.
    const auto pending = commands.last()[0].toJsonArray();
    preview.setViewport({{0, 24000, QRect(4000, 6000, 1200, 1400)}});
    const auto sharp = commands.last()[0].toJsonArray();
    QCOMPARE(sharp[3].toInt(), 24000);
    reply(pending, Qt::blue); QTest::qWait(10); QCOMPARE(preview.image(), retained);
    reply(sharp, Qt::green); QTRY_COMPARE(preview.surface().grid.width(), 24000);
    QCOMPARE(preview.image().pixelColor(0, 0), QColor(Qt::green));
    QCOMPARE(preview.bounds(), QRectF(0, 0, 600, 900));
    preview.message({"preview-state", 1, 0, 2, true, 0});
    QTRY_COMPARE(commands.last()[0].toJsonArray()[13].toInt(), 1);
    const auto neighbor = commands.last()[0].toJsonArray();
    QCOMPARE(neighbor[2].toInt(), 1); QCOMPARE(neighbor[3].toInt(), 24000);
    QVERIFY(neighbor[8].toInt() - neighbor[6].toInt() <= 2048);
    QVERIFY(neighbor[9].toInt() - neighbor[7].toInt() <= 2048);
}
void RenderingTest::croppedCanvasPlacement()
{
    PDFDocumentConfig config{}; config.editTool = 2;
    QScrollArea area; QWidget container; TexpressoCanvas canvas(&config, &area);
    canvas.resize(600, 900); canvas.pageBounds = QRectF(0, 0, 600, 900); canvas.scale = 1;
    const auto dpr = canvas.devicePixelRatioF();
    canvas.pixelSurface = {QSize(qRound(600 * dpr), qRound(900 * dpr)),
        QRect(qRound(100 * dpr), qRound(150 * dpr), qRound(200 * dpr), qRound(250 * dpr))};
    canvas.pixels = QImage(canvas.pixelSurface.clip.size(), QImage::Format_RGB32); canvas.pixels.fill(Qt::blue);
    QImage painted(QSize(qRound(600 * dpr), qRound(900 * dpr)), QImage::Format_RGB32); painted.setDevicePixelRatio(dpr);
    canvas.render(&painted);
    QCOMPARE(painted.pixelColor(qRound(150 * dpr), qRound(200 * dpr)), QColor(Qt::blue));
    QCOMPARE(painted.pixelColor(qRound(10 * dpr), qRound(10 * dpr)), QColor(Qt::white));
    QCOMPARE(painted.pixelColor(qRound(350 * dpr), qRound(200 * dpr)), QColor(Qt::white));
    const QPointF screen = (QPointF(canvas.mapToGlobal(QPoint())) + canvas.pageOrigin()) * dpr;
    QVERIFY(std::abs(screen.x() - std::round(screen.x())) < 1e-6);
    QVERIFY(std::abs(screen.y() - std::round(screen.y())) < 1e-6);
    QCOMPARE(canvas.imageRect().width() * dpr, double(canvas.pixels.width()));
    // A toolbar-like offset has a fractional device origin at DPR 1.25/1.5.
    // Preserve single-pixel stripes when the complete widget tree is painted.
    container.resize(640, 970); canvas.setParent(&container); canvas.move(3, 37); canvas.show();
    for (int y = 0; y < canvas.pixels.height(); ++y)
        for (int x = 0; x < canvas.pixels.width(); ++x)
            canvas.pixels.setPixelColor(x, y, (x + y) % 2 ? Qt::black : Qt::white);
    QImage capture(QSize(qRound(640 * dpr), qRound(970 * dpr)), QImage::Format_RGB32); capture.setDevicePixelRatio(dpr);
    container.render(&capture);
    const QPoint origin(qRound((canvas.x() + canvas.pageOrigin().x()) * dpr) + canvas.pixelSurface.clip.x(),
        qRound((canvas.y() + canvas.pageOrigin().y()) * dpr) + canvas.pixelSurface.clip.y());
    for (int y = 20; y < 40; ++y) for (int x = 20; x < 40; ++x)
        QCOMPARE(capture.pixelColor(origin + QPoint(x, y)), canvas.pixels.pixelColor(x, y));
}
void RenderingTest::retinaResolution()
{
    const auto engine = qEnvironmentVariable("TEXPRESSO_TEST_ENGINE");
    if (engine.isEmpty()) QSKIP("Set TEXPRESSO_TEST_ENGINE for native Retina rendering");
    QTemporaryDir project; const auto root = project.filePath("retina.tex");
    QString source = "\\documentclass[a4paper]{article}\n\\begin{document}\nFirst page A.\\newpage\nSecond page B.\\end{document}\n";
    QFile file(root); QVERIFY(file.open(QIODevice::WriteOnly)); file.write(source.toUtf8()); file.close();
    TexpressoManager manager(nullptr, engine); manager.openBuffer(root, source); manager.activate(root);
    auto session = manager.current(); session->followCursor = false; session->setAutoRerun(false);
    auto &preview = session->preview;
    QTRY_VERIFY_WITH_TIMEOUT(preview.valid() || session->failed(), 45000);
    QVERIFY2(!session->failed(), qPrintable(session->engineOutput));
    preview.lastPage(); QTRY_VERIFY_WITH_TIMEOUT(preview.complete() && preview.valid(), 15000);
    for (int width : {2240, 3200}) {
        preview.setWidth(width); preview.navigateTo(0);
        QTRY_VERIFY_WITH_TIMEOUT(preview.valid() && preview.image().width() == width, 15000);
        const auto first = preview.image();
        QVERIFY(qint64(first.width()) * first.height() > 4000000);
        preview.navigateTo(1); QTRY_VERIFY_WITH_TIMEOUT(preview.valid() && preview.image().width() == width, 15000);
        QVERIFY(preview.image() != first);
        preview.releaseCache(); preview.navigateTo(0);
        QTRY_VERIFY_WITH_TIMEOUT(preview.valid() && preview.image().width() == width, 15000);
        QCOMPARE(preview.image(), first); // Includes native encoded-only cache reuse at 3200 px.
    }
    const auto sequence = preview.sequence();
    const auto beforeEdit = preview.image();
    source.replace("page A", "page C"); manager.openBuffer(root, source);
    QTRY_VERIFY_WITH_TIMEOUT(preview.sequence() > sequence && preview.valid(), 15000);
    QCOMPARE(preview.image().width(), 3200); // A changed page still decodes/composes at Retina size.
    QVERIFY(preview.image() != beforeEdit);
    // Zoom density exceeds both the former 4096-width ceiling and the full-page
    // allocation budget. Only the requested neighborhood should be decoded.
    preview.setViewport({{0, 12000, QRect(1500, 1700, 800, 900)}});
    QTRY_COMPARE_WITH_TIMEOUT(preview.surface().grid.width(), 12000, 15000);
    QVERIFY(preview.surface().clip.contains(QRect(1500, 1700, 800, 900)));
    QVERIFY(preview.image().width() <= 2048 && preview.image().height() <= 2048);
    QVERIFY(preview.valid());
    manager.shutdown();
}
static QByteArray png(const QImage &image)
{
    QByteArray bytes; QBuffer buffer(&bytes); buffer.open(QIODevice::WriteOnly); image.save(&buffer, "PNG"); return bytes;
}
static QJsonObject frame(TexpressoPreview &preview, const QJsonArray &request, const QByteArray &bytes, QSize size = {8, 8})
{
    return testSurfaceHeader({{"requestId", request[1]}, {"revision", double(preview.revision())}, {"sequence", double(preview.sequence())},
        {"page", preview.page()}, {"width", size.width()}, {"height", size.height()}, {"bounds", QJsonArray{0, 0, 80, 80}},
        {"mime", "image/png"}, {"byteLength", bytes.size()}}, request);
}
static QJsonArray lastCommand(const QSignalSpy &commands) { return commands.last()[0].toJsonArray(); }
void RenderingTest::patchesAndKeyframeRecovery()
{
    TexpressoPreview preview; preview.setWidth(8); QSignalSpy commands(&preview, &TexpressoPreview::command);
    preview.setCapabilities({{"pngPatches", true}}); preview.setActive(true);
    preview.message({"preview-state", 1, 0, 1, true, 0});
    QCOMPARE(lastCommand(commands)[0].toString(), QString("preview-surface"));
    QCOMPARE(lastCommand(commands)[12].toInt(), 0);
    QImage red(8, 8, QImage::Format_RGB32); red.fill(Qt::red);
    const auto bytes = png(red); auto h = frame(preview, lastCommand(commands), bytes); h["rasterId"] = 1;
    preview.receive(h, bytes); QTRY_VERIFY(preview.valid());
    preview.sourceChanged(1); preview.message({"preview-state", 2, 1, 1, true, 0});
    QCOMPARE(lastCommand(commands)[12].toInt(), 1);
    QImage blue(2, 3, QImage::Format_RGB32); blue.fill(Qt::blue);
    const auto patch = png(blue); h = frame(preview, lastCommand(commands), patch); h["rasterId"] = 2;
    h["patch"] = QJsonObject{{"base", 1}, {"rect", QJsonArray{3, 2, 2, 3}}};
    preview.receive(h, patch); QTRY_VERIFY(preview.valid());
    QCOMPARE(preview.image().pixelColor(3, 2), QColor(Qt::blue));
    QCOMPARE(preview.image().pixelColor(2, 2), QColor(Qt::red));
    const auto composed = preview.image();
    preview.sourceChanged(2); preview.message({"preview-state", 3, 2, 1, true, 0});
    h = frame(preview, lastCommand(commands), {}); h["rasterId"] = 3;
    h["patch"] = QJsonObject{{"base", 2}, {"rect", QJsonArray{0, 0, 0, 0}}};
    preview.receive(h, {}); QTRY_VERIFY(preview.valid()); QCOMPARE(preview.image(), composed);
    QCOMPARE(preview.image().cacheKey(), composed.cacheKey()); // zero payload does no image copy
    preview.sourceChanged(3); preview.message({"preview-state", 4, 3, 1, true, 0});
    h = frame(preview, lastCommand(commands), patch); h["rasterId"] = 4;
    h["patch"] = QJsonObject{{"base", 999}, {"rect", QJsonArray{3, 2, 2, 3}}};
    preview.receive(h, patch);
    QCOMPARE(lastCommand(commands)[12].toInt(), 0); QVERIFY(!preview.valid());
    h = frame(preview, lastCommand(commands), bytes); h["rasterId"] = 5;
    preview.receive(h, bytes); QTRY_VERIFY(preview.valid()); QCOMPARE(preview.image(), red);
    // Matching raster IDs alone cannot authorize a patch for different geometry.
    preview.sourceChanged(4); preview.message({"preview-state", 5, 4, 1, true, 0});
    h = frame(preview, lastCommand(commands), patch); h["rasterId"] = 6; h["bounds"] = QJsonArray{0, 0, 81, 80};
    h["patch"] = QJsonObject{{"base", 5}, {"rect", QJsonArray{3, 2, 2, 3}}};
    preview.receive(h, patch); QCOMPARE(lastCommand(commands)[12].toInt(), 0);
}
void RenderingTest::latestRegionAndSourceFence()
{
    TexpressoPreview preview; preview.setWidth(8); QSignalSpy commands(&preview, &TexpressoPreview::command);
    QSignalSpy regions(&preview, &TexpressoPreview::regionReady);
    preview.setCapabilities({{"regions", true}, {"pngPatches", true}}); preview.setActive(true);
    preview.message({"preview-state", 1, 0, 2, true, 0});
    QImage red(8, 8, QImage::Format_RGB32); red.fill(Qt::red); const auto bytes = png(red);
    auto h = frame(preview, lastCommand(commands), bytes); h["rasterId"] = 1;
    preview.receive(h, bytes); QTRY_VERIFY(preview.valid()); const auto page = preview.image();
    preview.requestRegion({10, 10, 20, 20}, 100, 1); const auto first = lastCommand(commands);
    QCOMPARE(first[0].toString(), QString("preview-surface"));
    for (int token = 2; token <= 100; ++token) preview.requestRegion({20, 20, 20, 20}, 100, token);
    QCOMPARE(commands.size(), 2); // one native export and only the latest queued lens position
    h = frame(preview, first, bytes); receiveTestSurface(preview, first, h, bytes);
    QTRY_COMPARE(commands.size(), 3); QCOMPARE(regions.size(), 0);
    h = frame(preview, lastCommand(commands), bytes); receiveTestSurface(preview, lastCommand(commands), h, bytes);
    QTRY_COMPARE(regions.size(), 1); QCOMPARE(regions[0][0].toLongLong(), 100);
    QCOMPARE(preview.image().cacheKey(), page.cacheKey());
    preview.inverse({30, 30}); QCOMPARE(lastCommand(commands)[0].toString(), QString("preview-inverse"));
    preview.requestRegion({10, 10, 20, 20}, 100, 101); h = frame(preview, lastCommand(commands), bytes);
    receiveTestSurface(preview, lastCommand(commands), h, bytes); preview.sourceChanged(1); QTest::qWait(30); QCOMPARE(regions.size(), 1);
    preview.message({"preview-state", 2, 1, 2, true, 0}); QCOMPARE(lastCommand(commands)[12].toInt(), 1);
    h = frame(preview, lastCommand(commands), bytes); h["rasterId"] = 10; preview.receive(h, bytes); QTRY_VERIFY(preview.valid());
    preview.requestRegion({10, 10, 20, 20}, 100, 102); h = frame(preview, lastCommand(commands), bytes);
    preview.cancelRegion(); receiveTestSurface(preview, lastCommand(commands), h, bytes); QTest::qWait(30); QCOMPARE(regions.size(), 1);
}
void RenderingTest::surfaceCommand()
{
    TexpressoPreview preview; QSignalSpy commands(&preview, &TexpressoPreview::command);
    preview.setActive(true); preview.message({"preview-state", 1, 0, 1, true, 0});
    QCOMPARE(lastCommand(commands)[0].toString(), QString("preview-surface"));
    QCOMPARE(lastCommand(commands).size(), 14); // No legacy rendering negotiation.
}
void RenderingTest::asynchronousMagnifier()
{
    TexpressoPreview preview; preview.setWidth(8); QSignalSpy commands(&preview, &TexpressoPreview::command);
    preview.setCapabilities({{"regions", true}}); preview.setActive(true);
    preview.message({"preview-state", 1, 0, 1, true, 0});
    QImage red(8, 8, QImage::Format_RGB32); red.fill(Qt::red); const auto bytes = png(red);
    preview.receive(frame(preview, lastCommand(commands), bytes), bytes); QTRY_VERIFY(preview.valid());
    PDFDocumentConfig config{}; config.editTool = 1; config.magnifierSize = 120;
    config.magnifierShape = PDFDocumentConfig::Circle; config.magnifierBorder = true;
    QScrollArea area; area.resize(400, 400);
    auto canvas = new TexpressoCanvas(&config, &area); area.setWidget(canvas);
    canvas->pixels = preview.image(); canvas->pageBounds = preview.bounds(); canvas->scale = 4;
    canvas->fresh = true; canvas->resize(320, 320); canvas->setPreview(&preview);
    area.show(); QCoreApplication::processEvents();
    const QPoint point(160, 160);
    QTest::mousePress(canvas, Qt::LeftButton, Qt::NoModifier, point);
    auto lens = canvas->findChild<PDFMagnifier *>(); QVERIFY(lens && lens->isVisible());
    const auto color = [&] { const auto image = lens->grab().toImage(); return image.pixelColor(image.width() / 2, image.height() / 2); };
    QCOMPARE(color(), QColor(Qt::red)); // immediate crop while the native export is pending
    const auto request = lastCommand(commands); QCOMPARE(request[0].toString(), QString("preview-surface"));
    QImage blue(8, 8, QImage::Format_RGB32); blue.fill(Qt::blue); const auto detail = png(blue);
    auto h = frame(preview, request, detail);
    receiveTestSurface(preview, request, h, detail); QTRY_COMPARE(color(), QColor(Qt::blue));
    config.grayscale = true; config.invertColors = true; lens->update();
    const auto converted = convertImage(QPixmap::fromImage(blue), true, true).toImage();
    QCOMPARE(color(), converted.pixelColor(0, 0));
    // A fresh native frame arriving after a source edit must not reach the lens.
    QTest::mouseMove(canvas, point + QPoint(10, 10)); const auto obsolete = lastCommand(commands);
    h = frame(preview, obsolete, bytes);
    receiveTestSurface(preview, lastCommand(commands), h, bytes); preview.sourceChanged(1); canvas->fresh = false; canvas->resetTools();
    QTest::qWait(30); QVERIFY(!lens->isVisible());
}
void RenderingTest::externalBuildDisablesInteractions()
{
    const auto engine = qEnvironmentVariable("TEXPRESSO_TEST_ENGINE");
    if (engine.isEmpty()) QSKIP("Set TEXPRESSO_TEST_ENGINE for external-build viewer integration");
    QTemporaryDir dir; const auto root = dir.filePath("main.tex");
    QFile file(root); QVERIFY(file.open(QIODevice::WriteOnly));
    file.write("\\documentclass{article}\\begin{document}Build interaction test.\\end{document}\n"); file.close();
    TexpressoManager manager(nullptr, engine);
    PDFDocumentConfig config{}; config.editTool = 1; config.magnifierSize = 120;
    config.magnifierShape = PDFDocumentConfig::Circle;
    TexpressoWidget widget(&manager, &config, [](const QString &) { return QIcon(); });
    widget.resize(600, 600); widget.show(); manager.activate(root); manager.current()->setAutoRerun(false);
    auto canvas = widget.findChild<TexpressoCanvas *>(); QVERIFY(canvas);
    QTRY_VERIFY_WITH_TIMEOUT(canvas->fresh, 15000);
    QTest::mousePress(canvas, Qt::LeftButton, Qt::NoModifier, {100, 100});
    auto lens = canvas->findChild<PDFMagnifier *>(); QVERIFY(lens && lens->isVisible());
    manager.beginExternalBuild(root);
    QVERIFY(!canvas->fresh); QVERIFY(!lens->isVisible());
    QTRY_VERIFY(!widget.viewerActions()["gotoSource"]->isEnabled());
    QVERIFY(!widget.viewerActions()["rerunOnce"]->isEnabled());
    manager.endExternalBuild(root, false);
    QTRY_VERIFY(canvas->fresh); QVERIFY(!lens->isVisible());
}
void RenderingTest::cachedInverseUsesPublishedSourceMap()
{
    const auto engine = qEnvironmentVariable("TEXPRESSO_TEST_ENGINE");
    if (engine.isEmpty()) QSKIP("Set TEXPRESSO_TEST_ENGINE");
    const auto oldProfile = qgetenv("TEXPRESSO_PROFILE"); qputenv("TEXPRESSO_PROFILE", "1");
    const auto restore = qScopeGuard([&] { if (oldProfile.isNull()) qunsetenv("TEXPRESSO_PROFILE"); else qputenv("TEXPRESSO_PROFILE", oldProfile); });
    QTemporaryDir dir; const auto root = dir.filePath("main.tex");
    QFile file(root); QVERIFY(file.open(QIODevice::WriteOnly));
    file.write("\\documentclass{article}\n\\pagestyle{empty}\n\\begin{document}\nFirst source line.\n\\newpage\nSecond source line.\n\\newpage\nThird source line.\n\\end{document}\n"); file.close();
    TexpressoProcess process; TexpressoPreview preview; preview.setWidth(8); QString diagnostics;
    QSignalSpy images(&process, &TexpressoProcess::image), messages(&process, &TexpressoProcess::message), commands(&preview, &TexpressoPreview::command);
    connect(&process, &TexpressoProcess::diagnostic, &preview, [&](const QString &text) { diagnostics += text; });
    connect(&process, &TexpressoProcess::ready, &preview, [&](QJsonObject capabilities) {
        capabilities["backgroundRendering"] = false; capabilities["synctexPrecision"] = 0; preview.setCapabilities(capabilities);
        process.send({"rerun", false}); preview.setActive(true);
    });
    connect(&process, &TexpressoProcess::message, &preview, &TexpressoPreview::message);
    connect(&process, &TexpressoProcess::image, &preview, &TexpressoPreview::receive);
    connect(&preview, &TexpressoPreview::command, &process, &TexpressoProcess::send);
    process.start(engine, root); QTRY_VERIFY2_WITH_TIMEOUT(preview.valid(), qPrintable(diagnostics), 20000);
    const auto text = images.last()[0].toJsonObject()["textBounds"].toArray(); QCOMPARE(text.size(), 4);
    const QPointF point((text[0].toDouble() + text[2].toDouble()) / 2, (text[1].toDouble() + text[3].toDouble()) / 2);
    preview.setPage(1); QTRY_VERIFY_WITH_TIMEOUT(preview.valid() && preview.page() == 1, 10000);
    preview.setPage(0); QVERIFY(preview.valid());
    commands.clear(); messages.clear(); images.clear(); diagnostics.clear();
    QElapsedTimer timer; timer.start(); preview.inverse(point);
    const auto hasSource = [&] { for (const auto &row : messages) if (row[0].toJsonArray()[0] == "synctex") return true; return false; };
    QTRY_VERIFY2_WITH_TIMEOUT(hasSource(), qPrintable(diagnostics), 3000);
    qInfo() << "Cached inverse search returned in" << timer.elapsed() << "ms";
    QCOMPARE(commands.size(), 1); QCOMPARE(lastCommand(commands)[0].toString(), QString("preview-inverse"));
    QVERIFY(images.isEmpty());
    QVERIFY2(!diagnostics.contains("dvi-display-list"), qPrintable(diagnostics));
    QVERIFY2(!diagnostics.contains("compiler-restore"), qPrintable(diagnostics));
    for (const auto &row : messages) if (row[0].toJsonArray()[0] == "synctex")
        QCOMPARE(row[0].toJsonArray()[2].toInt(), 4);
}
void RenderingTest::realEngine()
{
    const auto engine = qEnvironmentVariable("TEXPRESSO_TEST_ENGINE");
    if (engine.isEmpty()) QSKIP("Set TEXPRESSO_TEST_ENGINE to exercise native patches and region rendering");
    QTemporaryDir dir; auto root = dir.filePath("main.tex");
    QString source = "\\documentclass{article}\n\\begin{document}\nSmall text 123456789.\\par\n";
    for (int i = 0; i < 12; ++i) source += "A whole line of unchanged text for raster patch comparison.\\par\n";
    source += "\\end{document}\n";
    QFile file(root); QVERIFY(file.open(QIODevice::WriteOnly)); file.write(source.toUtf8()); file.close();
    root = QFileInfo(root).canonicalFilePath();
    TexpressoProcess process; TexpressoPreview preview;
    QString diagnostics;
    connect(&process, &TexpressoProcess::diagnostic, &preview, [&](const QString &line) { diagnostics += line; });
    QSignalSpy images(&process, &TexpressoProcess::image), errors(&process, &TexpressoProcess::failed);
    QSignalSpy regions(&preview, &TexpressoPreview::regionReady);
    connect(&process, &TexpressoProcess::ready, &preview, [&](const QJsonObject &capabilities) {
        preview.setCapabilities(capabilities); process.send({"rerun", false}); preview.setActive(true);
    });
    connect(&process, &TexpressoProcess::message, &preview, &TexpressoPreview::message);
    connect(&process, &TexpressoProcess::image, &preview, &TexpressoPreview::receive);
    connect(&preview, &TexpressoPreview::command, &process, &TexpressoProcess::send);
    process.start(engine, root);
    QTRY_VERIFY_WITH_TIMEOUT(preview.valid() || !errors.isEmpty(), 20000); QVERIFY(errors.isEmpty());
    const auto textBounds = images.last()[0].toJsonObject()["textBounds"].toArray();
    QCOMPARE(textBounds.size(), 4);
    QVERIFY(!preview.horizontalTextRange().isEmpty());
    const auto fullBytes = images.last()[1].toByteArray().size();
    source.replace("123456789", "123456780");
    process.send({"open", root, source}); preview.sourceChanged(1); process.send({"preview-barrier", 1});
    QTRY_VERIFY2_WITH_TIMEOUT(preview.valid(), qPrintable(diagnostics), 10000);
    auto h = images.last()[0].toJsonObject(); QVERIFY(h.contains("patch"));
    QCOMPARE(h["textBounds"].toArray().size(), 4);
    const auto patchBytes = images.last()[1].toByteArray().size(); QVERIFY(patchBytes < fullBytes);
    process.send({"open", root, source + "\n"}); preview.sourceChanged(2); process.send({"preview-barrier", 2});
    QTRY_VERIFY_WITH_TIMEOUT(preview.valid(), 10000);
    h = images.last()[0].toJsonObject(); QVERIFY(h.contains("patch"));
    QCOMPARE(images.last()[1].toByteArray().size(), 0);
    QCOMPARE(h["textBounds"].toArray().size(), 4); // Metadata survives zero-byte updates.
    const auto page = preview.image();
    // Locate ink and request the same physical area at substantially higher
    // resolution. The decoded detail contains genuinely new samples.
    QPoint ink;
    for (int y = 0; y < page.height() && ink.isNull(); ++y)
        for (int x = 0; x < page.width(); ++x) if (qGray(page.pixel(x, y)) < 100) { ink = {x, y}; break; }
    QVERIFY(!ink.isNull());
    const QRect sample = QRect(ink - QPoint(8, 8), QSize(100, 50)).intersected(page.rect());
    const auto bounds = preview.bounds();
    const QRectF region(bounds.left() + sample.x() * bounds.width() / page.width(),
        bounds.top() + sample.y() * bounds.height() / page.height(), sample.width() * bounds.width() / page.width(),
        sample.height() * bounds.height() / page.height());
    preview.requestRegion(region, 600, 42);
    QTRY_COMPARE_WITH_TIMEOUT(regions.size(), 1, 10000);
    const auto detail = qvariant_cast<QImage>(regions[0][1]); QVERIFY(detail.width() >= 590);
    const auto enlarged = page.copy(sample).scaled(detail.size(), Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
    QVERIFY(detail != enlarged); QCOMPARE(preview.image().cacheKey(), page.cacheKey());
    qInfo() << "Native full PNG bytes:" << fullBytes << "small edit patch bytes:" << patchBytes
        << "no-op bytes: 0; region pixels:" << detail.size();
    process.stop();
}
void RenderingTest::preciseCachedSourceSearch()
{
    const auto engine = qEnvironmentVariable("TEXPRESSO_TEST_ENGINE");
    if (engine.isEmpty()) QSKIP("Set TEXPRESSO_TEST_ENGINE for native precise source search");
    QTemporaryDir project; const auto root = project.filePath("main.tex");
    QFile file(root); QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QString::fromUtf8("\\documentclass{article}\n\\pagestyle{empty}\n\\begin{document}\nAlpha office café repeated repeated finalword.\n\\newpage\nSecond page finalmarker.\n\\end{document}\n").toUtf8()); file.close();
    TexpressoProcess process; TexpressoPreview preview; QString diagnostics;
    QSignalSpy images(&process, &TexpressoProcess::image), messages(&process, &TexpressoProcess::message),
        commands(&preview, &TexpressoPreview::command), highlights(&preview, &TexpressoPreview::sourceHighlights),
        locations(&preview, &TexpressoPreview::sourceLocation);
    connect(&process, &TexpressoProcess::diagnostic, &preview, [&](const QString &text) { diagnostics += text; });
    connect(&process, &TexpressoProcess::ready, &preview, [&](QJsonObject capabilities) {
        capabilities["backgroundRendering"] = false; preview.setCapabilities(capabilities);
        process.send({"rerun", false}); preview.setActive(true);
    });
    connect(&process, &TexpressoProcess::message, &preview, &TexpressoPreview::message);
    connect(&process, &TexpressoProcess::image, &preview, &TexpressoPreview::receive);
    connect(&preview, &TexpressoPreview::command, &process, &TexpressoProcess::send);
    process.start(engine, root); QTRY_VERIFY2_WITH_TIMEOUT(preview.valid(), qPrintable(diagnostics), 25000);
    QVERIFY(preview.preciseSync());
    preview.forward(QFileInfo(root).canonicalFilePath(), 3, 9, "office");
    const auto wordRect = [&] {
        for (auto it = highlights.crbegin(); it != highlights.crend(); ++it)
            if ((*it)[0].toInt() == 0) return qvariant_cast<QList<QRectF>>((*it)[1]);
        return QList<QRectF>();
    };
    QTRY_VERIFY2_WITH_TIMEOUT(!wordRect().isEmpty(), qPrintable(diagnostics.right(10000)), 5000);
    QTest::qWait(100); QCOMPARE(wordRect().size(), 1); QVERIFY2(wordRect().first().width() < 50, qPrintable(diagnostics.right(1800)));
    const auto point = wordRect().first().center();
    preview.setPage(1); QTRY_VERIFY_WITH_TIMEOUT(preview.valid(), 10000);
    images.clear(); messages.clear(); commands.clear(); diagnostics.clear();
    preview.inverse(point, false, false, 0);
    QTRY_COMPARE_WITH_TIMEOUT(locations.size(), 1, 3000);
    QCOMPARE(locations.last()[1].toInt(), 4); QCOMPARE(locations.last()[3].toString(), QString("office"));
    QCOMPARE(commands.size(), 1); QVERIFY(images.isEmpty()); QCOMPARE(preview.page(), 1);
    QVERIFY2(!diagnostics.contains("dvi-display-list") && !diagnostics.contains("compiler-restore"), qPrintable(diagnostics));
    preview.setSyncInputTags(QJsonArray{}); preview.inverse(point, false, false, 0);
    const auto none = lastCommand(commands);
    const auto settled = [&] { for (const auto &row : messages) { const auto m = row[0].toJsonArray();
        if (m[0] == "preview-inverse-result" && m[1] == none[1] && m[5].isNull()) return true; } return false; };
    QTRY_VERIFY_WITH_TIMEOUT(settled(), 3000); QCOMPARE(locations.size(), 1);
    // Invalid new command shapes are rejected without corrupting the next valid query.
    process.send({"preview-search-precise", 99, root, 4, 0, -1, "office"});
    process.send({"preview-inverse-precise", 100, double(preview.revision()), 0, 0, 10, 10, QJsonArray{-1}, false});
    process.send({"preview-inverse-precise", 101, double(preview.revision()), 0, 0, 10, 10, QJsonValue::Null, 1});
    preview.setSyncInputTags(QJsonValue::Null); preview.inverse(point, false, false, 0);
    QTRY_COMPARE_WITH_TIMEOUT(locations.size(), 2, 3000); QCOMPARE(locations.last()[3].toString(), QString("office"));
}
QTEST_MAIN(RenderingTest)
#include "rendering_test.moc"
