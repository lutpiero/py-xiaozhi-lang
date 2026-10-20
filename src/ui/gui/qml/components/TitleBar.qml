// Customized title bar - platform adaptive
import QtQuick
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    height: Theme.titleBarHeight
    color: Theme.backgroundSecondary  // Add background color

    property string title: ""
    property bool showMinimize: true
    property bool showMaximize: false  // Do not display maximized by default
    property bool showClose: true

    signal minimizeClicked()
    signal maximizeClicked()
    signal closeClicked()

    // Drag area
    MouseArea {
        id: dragArea
        anchors.fill: parent
        // macOS: Leave space on the left for the button, Windows/Linux: Leave space on the right for the button
        anchors.leftMargin: Theme.titleButtonsOnLeft ? (macButtons.width + Theme.spacingLg) : 0
        anchors.rightMargin: Theme.titleButtonsOnLeft ? 0 : (winButtons.width + Theme.spacingMd)

        onPressed: {
            // uses the system's native drag API and is compatible with all platforms (including Linux Wayland)
            let win = Window.window
            if (win) {
                win.startSystemMove()
            }
        }

        onDoubleClicked: {
            let win = Window.window
            if (win) {
                // macOS: Double-click to enter full screen, Windows/Linux: Double-click to maximize
                if (Theme.titleButtonsOnLeft) {
                    if (win.visibility === Window.FullScreen) {
                        win.showNormal()
                    } else {
                        win.showFullScreen()
                    }
                } else {
                    if (win.visibility === Window.Maximized) {
                        win.showNormal()
                    } else {
                        win.showMaximized()
                    }
                }
            }
        }
    }

    // ========== macOS style button (left) ==========
    MacTitleBarButtons {
        id: macButtons
        visible: Theme.titleButtonsOnLeft
        anchors.left: parent.left
        anchors.leftMargin: Theme.spacingMd
        anchors.verticalCenter: parent.verticalCenter
        showMaximize: root.showMaximize

        onCloseClicked: root.closeClicked()
        onMinimizeClicked: root.minimizeClicked()
        onMaximizeClicked: {
            // macOS: The green button enters full-screen mode
            let win = Window.window
            if (win) {
                if (win.visibility === Window.FullScreen) {
                    win.showNormal()
                } else {
                    win.showFullScreen()
                }
            }
        }
    }

    // Title text - centered on macOS, left-aligned on Windows
    Text {
        anchors.centerIn: Theme.titleButtonsOnLeft ? parent : undefined
        anchors.left: Theme.titleButtonsOnLeft ? undefined : parent.left
        anchors.leftMargin: Theme.titleButtonsOnLeft ? 0 : Theme.spacingLg
        anchors.verticalCenter: Theme.titleButtonsOnLeft ? undefined : parent.verticalCenter
        text: root.title
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeMd
        font.weight: Font.Medium
        color: Theme.textPrimary
    }

    // ========== Windows/Linux style button (right) ==========
    Row {
        id: winButtons
        visible: !Theme.titleButtonsOnLeft
        anchors.right: parent.right
        anchors.rightMargin: Theme.spacingSm
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.spacingXs

        // Minimize button
        Rectangle {
            visible: root.showMinimize
            width: 32
            height: 32
            radius: Theme.radiusSm
            color: minimizeArea.containsMouse ? Theme.backgroundHover : "transparent"

            Text {
                anchors.centerIn: parent
                text: "−"
                font.pixelSize: Theme.fontSizeLg
                color: Theme.textSecondary
            }

            MouseArea {
                id: minimizeArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.minimizeClicked()
            }
        }

        // Maximize button
        Rectangle {
            visible: root.showMaximize
            width: 32
            height: 32
            radius: Theme.radiusSm
            color: maximizeArea.containsMouse ? Theme.backgroundHover : "transparent"

            Text {
                anchors.centerIn: parent
                text: "□"
                font.pixelSize: Theme.fontSizeMd
                color: Theme.textSecondary
            }

            MouseArea {
                id: maximizeArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.maximizeClicked()
            }
        }

        // Close button
        Rectangle {
            visible: root.showClose
            width: 32
            height: 32
            radius: Theme.radiusSm
            color: closeArea.containsMouse ? (closeArea.pressed ? Theme.error : Theme.errorHover) : "transparent"

            Text {
                anchors.centerIn: parent
                text: "×"
                font.pixelSize: Theme.fontSizeXl
                font.weight: Font.Bold
                color: closeArea.containsMouse ? "white" : Theme.textSecondary
            }

            MouseArea {
                id: closeArea
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.closeClicked()
            }
        }
    }
}
