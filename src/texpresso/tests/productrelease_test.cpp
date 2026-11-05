#include <QtTest>
#include "../productrelease.h"

class ProductReleaseTest : public QObject {
    Q_OBJECT
private slots:
    void versions() {
        using namespace TeXstudioProductRelease;
        QVERIFY(version("4.9.9").isEmpty());
        QVERIFY(version("4.9.9-espresso-0").isEmpty());
        QVERIFY(version("4.9.9-espresso-999999999999").isEmpty());
        QVERIFY(version("4.9.9-espresso-1") < version("4.9.9-espresso-10"));
        QVERIFY(version("4.9.9-espresso-10") < version("4.10.0-espresso-1"));
        QCOMPARE(version("v4.9.9-espresso-1"), version("4.9.9-espresso-1"));
    }
    void releases() {
        const QByteArray response = R"JSON([
          {"tag_name":"4.10.0-espresso-1","draft":true},
          {"tag_name":"4.9.9-espresso-20","prerelease":true},
          {"tag_name":"4.9.9-espresso-3"},
          {"tag_name":"9.0.0"},
          {"tag_name":"4.9.9-espresso-10"}
        ])JSON";
        QCOMPARE(TeXstudioProductRelease::latest(response, false), QString("4.9.9-espresso-10"));
        QCOMPARE(TeXstudioProductRelease::latest(response, true), QString("4.9.9-espresso-20"));
        QVERIFY(TeXstudioProductRelease::latest("{\"message\":\"API error\"}", true).isEmpty());
        QVERIFY(TeXstudioProductRelease::latest("[]", false).isEmpty());
    }
};
QTEST_GUILESS_MAIN(ProductReleaseTest)
#include "productrelease_test.moc"
