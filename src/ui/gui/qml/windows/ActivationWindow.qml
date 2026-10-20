// Device activation window
import QtQuick
import QtQuick.Layouts
import "../theme"
import "../components"
import "../controls"

AppWindow {
    id: root

    width: 520
    height: 340
    minimumWidth: 450
    minimumHeight: 300
    title: i18n.t("设备激活")
    visible: true

    // Signal
    signal activationCompleted(bool success)

    // Use platform adaptive title bar
    TitleBar {
        id: titleBar
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        title: i18n.t("设备激活")
        showMaximize: false
        onMinimizeClicked: root.showMinimized()
        onCloseClicked: root.close()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: titleBar.height
        anchors.margins: Theme.spacingXl
        spacing: Theme.spacingLg

        // Status indicator - placed independently at the top of the content area
        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignRight
            spacing: Theme.spacingSm

            Rectangle {
                width: 8
                height: 8
                radius: Theme.radiusSm
                color: activationModel ? activationModel.statusColor : Theme.textPlaceholder

                // Flashing animation during activation
                SequentialAnimation on opacity {
                    running: activationModel ? activationModel.isActivating : false
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.3; duration: 500 }
                    NumberAnimation { to: 1.0; duration: 500 }
                }
            }

            Text {
                text: activationModel ? activationModel.activationStatus : ""
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSm
                color: Theme.textSecondary
            }
        }

        // Device information card
        XCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 90
            hoverable: true

            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.spacingMd

                Text {
                    text: i18n.t("设备信息")
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeMd
                    font.weight: Font.Medium
                    color: Theme.textSecondary
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: Theme.spacingXxl
                    rowSpacing: Theme.spacingXs

                    // Serial number
                    Text {
                        text: i18n.t("设备序列号")
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPlaceholder
                    }

                    Text {
                        text: i18n.t("MAC 地址")
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPlaceholder
                    }

                    Text {
                        text: activationModel ? activationModel.serialNumber : ""
                        font.family: Theme.fontFamilyMono
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        elide: Text.ElideMiddle
                        Layout.maximumWidth: 200
                    }

                    Text {
                        text: activationModel ? activationModel.macAddress : ""
                        font.family: Theme.fontFamilyMono
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                    }
                }
            }
        }

        // Activation code card
        XCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 70
            hoverable: true

            RowLayout {
                anchors.fill: parent
                spacing: Theme.spacingLg

                Text {
                    text: i18n.t("激活验证码")
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeMd
                    font.weight: Font.Medium
                    color: Theme.textSecondary
                }

                // Verification code display box
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    radius: Theme.radiusSm
                    color: Theme.background
                    border.width: 1
                    border.color: Theme.border

                    Text {
                        anchors.centerIn: parent
                        text: activationModel ? activationModel.activationCode : "------"
                        font.family: Theme.fontFamilyMono
                        font.pixelSize: Theme.fontSizeLg
                        font.weight: Font.Bold
                        font.letterSpacing: 4
                        color: (activationModel && activationModel.activationCode !== "------") ? Theme.error : Theme.textPlaceholder
                    }
                }

                // Copy button
                XButton {
                    text: i18n.t("复制")
                    enabled: activationModel ? activationModel.activationCode !== "------" : false
                    onClicked: {
                        if (typeof activationController !== 'undefined') {
                            activationController.copyActivationCode()
                        }
                        copyToast.show()
                    }
                }
            }
        }

        // Operation button
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            XButton {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                text: i18n.t("打开激活页面")
                enabled: activationModel ? !activationModel.isActivated : true
                onClicked: {
                    if (typeof activationController !== 'undefined') {
                        activationController.openActivationUrl()
                    }
                }
            }
        }

        // Prompt message
        Text {
            Layout.fillWidth: true
            text: (activationModel && activationModel.isActivated)
                ? i18n.t("设备已激活，窗口即将关闭...")
                : i18n.t("请在激活页面输入验证码完成设备激活")
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSm
            color: Theme.textPlaceholder
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        Item { Layout.fillHeight: true }
    }

    // Copy success prompt
    Rectangle {
        id: copyToast
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.spacingXl
        anchors.horizontalCenter: parent.horizontalCenter
        width: toastText.implicitWidth + Theme.spacingLg * 2
        height: 36
        radius: Theme.radiusMd
        color: Theme.success
        opacity: 0
        visible: opacity > 0

        function show() {
            opacity = 1
            hideTimer.restart()
        }

        Timer {
            id: hideTimer
            interval: 2000
            onTriggered: copyToast.opacity = 0
        }

        Behavior on opacity {
            NumberAnimation { duration: Theme.animationNormal }
        }

        Text {
            id: toastText
            anchors.centerIn: parent
            text: i18n.t("验证码已复制")
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSm
            color: "white"
        }
    }
}
