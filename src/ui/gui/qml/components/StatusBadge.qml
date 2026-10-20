// Status badge component
import QtQuick
import "../theme"

Rectangle {
    id: root

    property string status: "offline"  // "online", "offline", "warning"
    property string text: ""

    implicitWidth: row.width + Theme.spacingMd * 2
    implicitHeight: 24
    radius: Theme.radiusLg
    color: {
        switch (status) {
            case "online": return Theme.successLight
            case "warning": return Theme.warningLight
            default: return Theme.errorLight
        }
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: Theme.spacingXs

        Rectangle {
            width: 6
            height: 6
            // Small dots: Use radiusSm(4) to approach the full circle and avoid the magic number 3
            radius: Theme.radiusSm
            anchors.verticalCenter: parent.verticalCenter
            color: {
                switch (root.status) {
                    case "online": return Theme.success
                    case "warning": return Theme.warning
                    default: return Theme.error
                }
            }
        }

        Text {
            text: root.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeXs
            color: Theme.textSecondary
        }
    }
}
