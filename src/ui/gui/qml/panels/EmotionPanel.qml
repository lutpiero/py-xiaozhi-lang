// Expression panel
import QtQuick
import QtQuick.Layouts
import "../theme"
import "../components"

Rectangle {
    id: root

    color: Theme.background

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        spacing: Theme.spacingMd

        // Expression display
        EmotionDisplay {
            Layout.fillWidth: true
            Layout.fillHeight: true
            source: mainModel.emotionUrl
        }
    }
}
