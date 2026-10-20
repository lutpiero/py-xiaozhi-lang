// Main window - matches the original layout
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"
import "../components"

AppWindow {
    id: root

    width: 420
    height: 520
    minimumWidth: 360
    minimumHeight: 420
    title: ""
    // Controlled by QmlAppHost.show_root for display; avoid QML loading moment grabbing focus
    visible: false

    // Use ColumnLayout directly, no additional Rectangle required Layer
    // AppWindow has provided a container with rounded corners
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

            // Customized title bar - platform adaptive
            TitleBar {
                Layout.fillWidth: true
                showMaximize: true
                onMinimizeClicked: root.showMinimized()
                onMaximizeClicked: {
                    if (root.visibility === Window.FullScreen || root.visibility === Window.Maximized) {
                        root.showNormal()
                    } else {
                        root.showMaximized()
                    }
                }
                onCloseClicked: {
                    if (eventBridge) eventBridge.onQuitRequest()
                }
            }

            // Status card area
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "transparent"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.spacingMd
                    spacing: Theme.spacingMd

                    // Status label
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        color: Theme.primaryLight
                        radius: Theme.radiusMd

                        Text {
                            anchors.centerIn: parent
                            text: (mainModel && mainModel.statusText) ? mainModel.statusText : i18n.t("待命")
                            font.pixelSize: Theme.fontSizeMd
                            font.weight: Font.Bold
                            color: Theme.primaryText
                        }
                    }

                    // Expression display area
                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 80

                        property string currentEmotionUrl: (mainModel && mainModel.emotionUrl) ? mainModel.emotionUrl : ""

                        AnimatedImage {
                            anchors.centerIn: parent
                            width: Math.max(Math.min(parent.width, parent.height) * 0.7, 60)
                            height: width
                            source: parent.currentEmotionUrl
                            fillMode: Image.PreserveAspectFit
                            playing: true
                            visible: parent.currentEmotionUrl.length > 0 && parent.currentEmotionUrl.indexOf("file://") === 0
                        }

                        Text {
                            anchors.centerIn: parent
                            text: parent.currentEmotionUrl.indexOf("file://") !== 0 ? (parent.currentEmotionUrl || "😊") : ""
                            font.pixelSize: 80
                            visible: parent.currentEmotionUrl.indexOf("file://") !== 0
                        }
                    }

                    // Dialog Music row
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 72
                        color: "transparent"

                        Column {
                            anchors.fill: parent
                            anchors.margins: Theme.spacingSm
                            spacing: Theme.spacingXs

                            Text {
                                width: parent.width
                                height: parent.height - (musicLineText.visible ? 22 : 0)
                                text: (mainModel && mainModel.ttsText) ? mainModel.ttsText : i18n.t("待命")
                                font.pixelSize: Theme.fontSizeSm
                                color: Theme.textSecondary
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                wrapMode: Text.WordWrap
                                elide: Text.ElideRight
                            }

                            Text {
                                id: musicLineText
                                width: parent.width
                                visible: mainModel && mainModel.musicLine && mainModel.musicLine.length > 0
                                text: mainModel ? mainModel.musicLine : ""
                                font.pixelSize: Theme.fontSizeXs
                                color: Theme.textPlaceholder
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }

            // Button area
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 72
                color: Theme.backgroundSecondary

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.spacingMd
                    anchors.rightMargin: Theme.spacingMd
                    anchors.bottomMargin: 10
                    spacing: Theme.spacingSm

                    // Manual mode button (click to switch recording)
                    Button {
                        id: manualBtn
                        Layout.preferredWidth: 100
                        Layout.fillWidth: true
                        Layout.maximumWidth: 140
                        Layout.preferredHeight: 38
                        text: (mainModel && mainModel.buttonText) ? mainModel.buttonText : i18n.t("按住后说话")
                        visible: !(mainModel && mainModel.autoMode)

                        background: Rectangle {
                            color: manualBtn.pressed ? Theme.primaryPressed : (manualBtn.hovered ? Theme.primaryHover : Theme.primary)
                            radius: Theme.radiusMd
                        }

                        contentItem: Text {
                            text: manualBtn.text
                            font.pixelSize: Theme.fontSizeSm
                            color: "white"
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: if (eventBridge) eventBridge.onManualToggle()
                    }

                    // Auto mode button
                    Button {
                        id: autoBtn
                        Layout.preferredWidth: 100
                        Layout.fillWidth: true
                        Layout.maximumWidth: 140
                        Layout.preferredHeight: 38
                        text: (mainModel && mainModel.buttonText) ? mainModel.buttonText : i18n.t("开始对话")
                        visible: mainModel && mainModel.autoMode

                        background: Rectangle {
                            color: autoBtn.pressed ? Theme.primaryPressed : (autoBtn.hovered ? Theme.primaryHover : Theme.primary)
                            radius: Theme.radiusMd
                        }

                        contentItem: Text {
                            text: autoBtn.text
                            font.pixelSize: Theme.fontSizeSm
                            color: "white"
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: if (eventBridge) eventBridge.onAutoStart()
                    }

                    // Interrupt conversation
                    Button {
                        id: abortBtn
                        Layout.preferredWidth: 80
                        Layout.fillWidth: true
                        Layout.maximumWidth: 120
                        Layout.preferredHeight: 38
                        text: i18n.t("打断对话")

                        background: Rectangle {
                            color: abortBtn.pressed ? Theme.divider : (abortBtn.hovered ? Theme.backgroundHover : Theme.backgroundSecondary)
                            radius: Theme.radiusMd
                            border.width: 1
                            border.color: Theme.border
                        }

                        contentItem: Text {
                            text: abortBtn.text
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textPrimary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: if (eventBridge) eventBridge.onAbort()
                    }

                    // Input Send
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 120
                        Layout.preferredHeight: 38
                        spacing: Theme.spacingSm

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            color: Theme.background
                            radius: Theme.radiusMd
                            border.color: textInput.activeFocus ? Theme.primary : Theme.border
                            border.width: 1

                            TextInput {
                                id: textInput
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                verticalAlignment: TextInput.AlignVCenter
                                font.pixelSize: Theme.fontSizeSm
                                color: Theme.textPrimary
                                selectByMouse: true
                                clip: true

                                Text {
                                    anchors.fill: parent
                                    text: i18n.t("输入文字...")
                                    font: textInput.font
                                    color: Theme.textPlaceholder
                                    verticalAlignment: Text.AlignVCenter
                                    visible: !textInput.text && !textInput.activeFocus
                                }

                                Keys.onReturnPressed: sendText()
                            }
                        }

                        Button {
                            id: sendBtn
                            Layout.preferredWidth: 60
                            Layout.maximumWidth: 84
                            Layout.preferredHeight: 38
                            text: i18n.t("发送")

                            background: Rectangle {
                                color: sendBtn.pressed ? Theme.primaryPressed : (sendBtn.hovered ? Theme.primaryHover : Theme.primary)
                                radius: Theme.radiusMd
                            }

                            contentItem: Text {
                                text: sendBtn.text
                                font.pixelSize: Theme.fontSizeSm
                                color: "white"
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }

                            onClicked: sendText()
                        }
                    }

                    // Mode switching
                    Button {
                        id: modeBtn
                        Layout.preferredWidth: 80
                        Layout.fillWidth: true
                        Layout.maximumWidth: 120
                        Layout.preferredHeight: 38
                        text: (mainModel && mainModel.modeText) ? mainModel.modeText : i18n.t("手动对话")

                        background: Rectangle {
                            color: modeBtn.pressed ? Theme.divider : (modeBtn.hovered ? Theme.backgroundHover : Theme.backgroundSecondary)
                            radius: Theme.radiusMd
                            border.width: 1
                            border.color: Theme.border
                        }

                        contentItem: Text {
                            text: modeBtn.text
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textPrimary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: if (eventBridge) eventBridge.onAutoToggle()
                    }

                    // Parameter settings
                    Button {
                        id: settingsBtn
                        Layout.preferredWidth: 80
                        Layout.fillWidth: true
                        Layout.maximumWidth: 120
                        Layout.preferredHeight: 38
                        text: i18n.t("参数设置")

                        background: Rectangle {
                            color: settingsBtn.pressed ? Theme.divider : (settingsBtn.hovered ? Theme.backgroundHover : Theme.backgroundSecondary)
                            radius: Theme.radiusMd
                            border.width: 1
                            border.color: Theme.border
                        }

                        contentItem: Text {
                            text: settingsBtn.text
                            font.pixelSize: Theme.fontSizeSm
                            color: Theme.textPrimary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }

                        onClicked: if (eventBridge) eventBridge.onOpenSettings()
                    }
            }
        }
    }

    function sendText() {
        let text = textInput.text.trim()
        if (text.length > 0 && eventBridge) {
            eventBridge.onSendText(text)
            textInput.text = ""
        }
    }
}
