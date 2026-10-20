// Settings window - Refer to the old PyQt5 implementation
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"
import "settings"

AppWindow {
    id: root

    width: 700
    height: 550
    minimumWidth: 600
    minimumHeight: 450
    title: i18n.t("参数设置")
    visible: false

    // Tab configuration
    readonly property var tabConfig: [
        { name: i18n.t("系统选项"), component: "SystemOptionsTab.qml" },
        { name: i18n.t("MCP 工具"), component: "McpToolsTab.qml" },
        { name: i18n.t("唤醒词"), component: "WakeWordTab.qml" },
        { name: i18n.t("摄像头"), component: "CameraTab.qml" },
        { name: i18n.t("音频设备"), component: "AudioDeviceTab.qml" },
        { name: i18n.t("快捷键"), component: "ShortcutsTab.qml" },
        { name: i18n.t("音乐"), component: "MusicTab.qml" }
    ]

    // Use ColumnLayout directly, no additional Rectangle required Layer
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

            // Customized title bar - platform adaptive
            TitleBar {
                Layout.fillWidth: true
                title: i18n.t("参数设置")
                showMaximize: true
                onMinimizeClicked: root.showMinimized()
                onMaximizeClicked: {
                    if (root.visibility === Window.FullScreen || root.visibility === Window.Maximized) {
                        root.showNormal()
                    } else {
                        root.showMaximized()
                    }
                }
                onCloseClicked: root.close()
            }

            // Content area
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Theme.background

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 0
                    spacing: 0

                    // Left navigation bar
                    Rectangle {
                        Layout.preferredWidth: 150
                        Layout.fillHeight: true
                        color: Theme.backgroundSecondary

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.spacingMd
                            spacing: Theme.spacingXs

                            Repeater {
                                model: tabConfig

                                delegate: Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 40
                                    radius: Theme.radiusMd
                                    color: tabBar.currentIndex === index ? Theme.primaryLight : (navMouse.containsMouse ? Theme.backgroundHover : "transparent")

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: Theme.spacingMd
                                        anchors.rightMargin: Theme.spacingMd
                                        spacing: Theme.spacingSm

                                        // Icon area (optional)
                                        Rectangle {
                                            width: 4
                                            height: 20
                                            radius: 2
                                            color: tabBar.currentIndex === index ? Theme.primary : "transparent"
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: modelData.name
                                            font.pixelSize: Theme.fontSizeMd
                                            color: tabBar.currentIndex === index ? Theme.primary : Theme.textSecondary
                                            elide: Text.ElideRight
                                        }
                                    }

                                    MouseArea {
                                        id: navMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: tabBar.currentIndex = index
                                    }
                                }
                            }

                            Item { Layout.fillHeight: true }
                        }
                    }

                    // Separator
                    Rectangle {
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        color: Theme.border
                    }

                    // Right content area
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: Theme.background

                        StackLayout {
                            id: tabBar
                            anchors.fill: parent
                            anchors.margins: Theme.spacingXl
                            currentIndex: 0

                            // System options
                            SystemOptionsTab {}

                            // MCP tool
                            McpToolsTab {}

                            // Wake word
                            WakeWordTab {}

                            // Camera
                            CameraTab {}

                            // Audio device
                            AudioDeviceTab {}

                            // Shortcut keys
                            ShortcutsTab {}

                            // Music
                            MusicTab {}
                        }
                    }
                }
            }

            // Bottom button bar
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 60
                color: Theme.backgroundSecondary

                // Top divider
                Rectangle {
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 1
                    color: Theme.border
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.spacingXl
                    anchors.rightMargin: Theme.spacingXl
                    spacing: Theme.spacingMd

                    // Status message
                    Text {
                        id: statusText
                        Layout.fillWidth: true
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPlaceholder
                        elide: Text.ElideRight

                        Connections {
                            target: settingsModel
                            function onStatusMessage(msg) {
                                statusText.text = msg
                                statusTimer.restart()
                            }
                        }

                        Timer {
                            id: statusTimer
                            interval: 5000
                            onTriggered: statusText.text = ""
                        }
                    }

                    // Reset button
                    Button {
                        id: resetBtn
                        Layout.preferredWidth: 80
                        Layout.preferredHeight: 34
                        text: i18n.t("重置")

                        background: Rectangle {
                            color: resetBtn.pressed ? Theme.errorLight : (resetBtn.hovered ? Theme.errorLight : "transparent")
                            border.color: Theme.error
                            border.width: 1
                            radius: Theme.radiusSm
                        }

                        contentItem: Text {
                            text: resetBtn.text
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.error
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: {
                            settingsModel.reload()
                        }
                    }

                    // Cancel button
                    Button {
                        id: cancelBtn
                        Layout.preferredWidth: 80
                        Layout.preferredHeight: 34
                        text: i18n.t("取消")

                        background: Rectangle {
                            color: cancelBtn.pressed ? Theme.divider : (cancelBtn.hovered ? Theme.backgroundHover : Theme.backgroundSecondary)
                            radius: Theme.radiusSm
                            border.width: 1
                            border.color: Theme.border
                        }

                        contentItem: Text {
                            text: cancelBtn.text
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textSecondary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: root.close()
                    }

                    // Save button
                    Button {
                        id: saveBtn
                        Layout.preferredWidth: 80
                        Layout.preferredHeight: 34
                        text: i18n.t("保存")

                        background: Rectangle {
                            color: saveBtn.pressed ? Theme.primaryPressed : (saveBtn.hovered ? Theme.primaryHover : Theme.primary)
                            radius: Theme.radiusSm
                        }

                        contentItem: Text {
                            text: saveBtn.text
                            font.pixelSize: Theme.fontSizeSm
                            color: "white"
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: {
                            // grabs the focus first and lets the current TextField trigger editingFinished Write back model
                            saveBtn.forceActiveFocus()
                            settingsModel.save()
                            root.close()
                        }
                    }
            }
        }
    }
}
