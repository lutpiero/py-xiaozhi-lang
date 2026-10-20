// Borderless resizable window base class
import QtQuick
import QtQuick.Window
import Qt5Compat.GraphicalEffects
import "../theme"

Window {
    id: root

    flags: Qt.FramelessWindowHint | Qt.Window
    color: "transparent"

    minimumWidth: 480
    minimumHeight: 360

    // Edge drag resize margins
    property int resizeMargin: 8

    // Whether to maximize or full screen
    property bool isMaximized: root.visibility === Window.Maximized || root.visibility === Window.FullScreen

    // Content area
    default property alias content: contentArea.data

    // Update the window width of the theme
    onWidthChanged: Theme.windowWidth = width

    // Main container (with rounded corners and borders)
    Rectangle {
        id: container
        anchors.fill: parent
        anchors.margins: root.isMaximized ? 0 : 1
        radius: root.isMaximized ? 0 : Theme.windowRadius
        color: Theme.background
        antialiasing: true
        border.width: root.isMaximized ? 0 : 1
        border.color: Theme.border

        // Use layer to achieve rounded corner cropping
        layer.enabled: !root.isMaximized
        layer.effect: OpacityMask {
            maskSource: Rectangle {
                width: container.width
                height: container.height
                radius: container.radius
            }
        }

        // Content area
        Item {
            id: contentArea
            anchors.fill: parent
        }
    }

    // Edge-resized MouseArea - placed on top (hidden when maximized)
    // left edge
    MouseArea {
        visible: !root.isMaximized
        width: resizeMargin
        height: parent.height - resizeMargin * 2
        x: 0
        y: resizeMargin
        cursorShape: Qt.SizeHorCursor
        onPressed: root.startSystemResize(Qt.LeftEdge)
    }

    // right edge
    MouseArea {
        visible: !root.isMaximized
        width: resizeMargin
        height: parent.height - resizeMargin * 2
        x: parent.width - resizeMargin
        y: resizeMargin
        cursorShape: Qt.SizeHorCursor
        onPressed: root.startSystemResize(Qt.RightEdge)
    }

    // Top edge
    MouseArea {
        visible: !root.isMaximized
        width: parent.width - resizeMargin * 2
        height: resizeMargin
        x: resizeMargin
        y: 0
        cursorShape: Qt.SizeVerCursor
        onPressed: root.startSystemResize(Qt.TopEdge)
    }

    // Lower edge
    MouseArea {
        visible: !root.isMaximized
        width: parent.width - resizeMargin * 2
        height: resizeMargin
        x: resizeMargin
        y: parent.height - resizeMargin
        cursorShape: Qt.SizeVerCursor
        onPressed: root.startSystemResize(Qt.BottomEdge)
    }

    // upper left corner
    MouseArea {
        visible: !root.isMaximized
        width: resizeMargin
        height: resizeMargin
        x: 0
        y: 0
        cursorShape: Qt.SizeFDiagCursor
        onPressed: root.startSystemResize(Qt.LeftEdge | Qt.TopEdge)
    }

    // Upper right corner
    MouseArea {
        visible: !root.isMaximized
        width: resizeMargin
        height: resizeMargin
        x: parent.width - resizeMargin
        y: 0
        cursorShape: Qt.SizeBDiagCursor
        onPressed: root.startSystemResize(Qt.RightEdge | Qt.TopEdge)
    }

    // lower left corner
    MouseArea {
        visible: !root.isMaximized
        width: resizeMargin
        height: resizeMargin
        x: 0
        y: parent.height - resizeMargin
        cursorShape: Qt.SizeBDiagCursor
        onPressed: root.startSystemResize(Qt.LeftEdge | Qt.BottomEdge)
    }

    // Lower right corner
    MouseArea {
        visible: !root.isMaximized
        width: resizeMargin
        height: resizeMargin
        x: parent.width - resizeMargin
        y: parent.height - resizeMargin
        cursorShape: Qt.SizeFDiagCursor
        onPressed: root.startSystemResize(Qt.RightEdge | Qt.BottomEdge)
    }
}
