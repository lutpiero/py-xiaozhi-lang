// Camera settings page
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../theme"
import "../../controls"

ScrollView {
    id: root
    clip: true

    // Test status
    property bool cameraTesting: false
    property bool cameraTestPassed: false
    property bool cameraTestFailed: false
    property string testResult: ""

    // Scan again when entering the camera page (do not scan OpenCV during startup to avoid cold start lag)
    Component.onCompleted: {
        if (settingsModel) {
            var list = settingsModel.getCameras()
            if (list.length === 0) {
                settingsModel.refreshCameras()
            } else {
                cameraCombo.model = list
                cameraCombo.currentIndex = settingsModel.selectedCameraIndex
            }
        }
    }

    Connections {
        target: settingsModel
        function onDevicesChanged() {
            if (settingsModel) {
                cameraCombo.model = settingsModel.getCameras()
                // model Resynchronize after setting currentIndex
                cameraCombo.currentIndex = settingsModel.selectedCameraIndex
            }
        }
        function onStatusMessage(message) {
            root.testResult = message
        }
        function onTestComplete(kind, success) {
            if (kind !== "camera") return
            root.cameraTesting = false
            root.cameraTestPassed = success
            root.cameraTestFailed = !success
        }
    }

    ColumnLayout {
        width: root.availableWidth
        spacing: Theme.spacingLg

        // Page title
        Text {
            text: i18n.t("摄像头设置")
            font.pixelSize: Theme.fontSizeXl
            font.weight: Font.DemiBold
            color: Theme.textPrimary
        }

        // Device selection
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: i18n.t("设备选择")
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingMd

                Text {
                    text: i18n.t("摄像头")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 80
                }

                XComboBox {
                    id: cameraCombo
                    Layout.fillWidth: true
                    currentIndex: settingsModel ? settingsModel.selectedCameraIndex : 0
                    onActivated: function(index) {
                        if (settingsModel) settingsModel.selectedCameraIndex = index
                    }
                    font.pixelSize: Theme.fontSizeSm
                }

                Button {
                    text: root.cameraTesting ? i18n.t("测试中...") : i18n.t("测试")
                    enabled: !root.cameraTesting
                    Layout.preferredWidth: 70
                    Layout.preferredHeight: 32

                    background: Rectangle {
                        color: parent.enabled ? (parent.pressed ? Theme.primaryPressed : (parent.hovered ? Theme.primaryHover : Theme.primary)) : Theme.textPlaceholder
                        radius: Theme.radiusSm
                    }

                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: "white"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    onClicked: {
                        root.cameraTesting = true
                        root.cameraTestPassed = false
                        root.cameraTestFailed = false
                        root.testResult = ""
                        if (settingsModel) settingsModel.testCamera()
                    }
                }

                Button {
                    text: i18n.t("刷新")
                    Layout.preferredWidth: 70
                    Layout.preferredHeight: 32

                    background: Rectangle {
                        color: parent.pressed ? Theme.divider : (parent.hovered ? Theme.backgroundSecondary : Theme.backgroundHover)
                        radius: Theme.radiusSm
                    }

                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textSecondary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    onClicked: if (settingsModel) settingsModel.refreshCameras()
                }
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.divider
        }

        // Video parameters
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: i18n.t("视频参数")
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: Theme.spacingMd
                columnSpacing: Theme.spacingLg

                Text {
                    text: i18n.t("分辨率")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 80
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.spacingSm

                    XSpinBox {
                        Layout.preferredWidth: 100
                        from: 320
                        to: 1920
                        stepSize: 160
                        value: settingsModel ? settingsModel.frameWidth : 640
                        onValueModified: if (settingsModel) settingsModel.frameWidth = value
                        font.pixelSize: Theme.fontSizeSm
                    }

                    Text {
                        text: "x"
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textSecondary
                    }

                    XSpinBox {
                        Layout.preferredWidth: 100
                        from: 240
                        to: 1080
                        stepSize: 120
                        value: settingsModel ? settingsModel.frameHeight : 480
                        onValueModified: if (settingsModel) settingsModel.frameHeight = value
                        font.pixelSize: Theme.fontSizeSm
                    }
                }

                Text {
                    text: i18n.t("帧率")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 80
                }

                RowLayout {
                    spacing: Theme.spacingSm

                    XSpinBox {
                        Layout.preferredWidth: 100
                        from: 10
                        to: 60
                        stepSize: 5
                        value: settingsModel ? settingsModel.fps : 30
                        onValueModified: if (settingsModel) settingsModel.fps = value
                    }

                    Text {
                        text: "FPS"
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textSecondary
                    }
                }
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.divider
        }

        // VL API configuration
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: i18n.t("视觉语言模型 (VL API)")
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: Theme.spacingMd
                columnSpacing: Theme.spacingLg

                Text {
                    text: i18n.t("API 地址")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 80
                }
                TextField {
                    id: vlApiUrlField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.vlApiUrl : ""
                    onEditingFinished: if (settingsModel) settingsModel.vlApiUrl = text
                    placeholderText: "https://..."
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: vlApiUrlField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: "API Key"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 80
                }
                XTextField {
                    id: vlApiKeyField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.vlApiKey : ""
                    onEditingFinished: if (settingsModel) settingsModel.vlApiKey = text
                    isPassword: true
                }

                Text {
                    text: i18n.t("模型")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 80
                }
                TextField {
                    id: vlModelsField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.vlModels : ""
                    onEditingFinished: if (settingsModel) settingsModel.vlModels = text
                    placeholderText: "glm-4v-plus"
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: vlModelsField.activeFocus ? Theme.primary : "transparent"
                    }
                }
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.divider
        }

        // Test results
        Rectangle {
            Layout.fillWidth: true
            height: 48
            color: root.cameraTestPassed ? Theme.successLight :
                   root.cameraTestFailed ? Theme.errorLight : Theme.backgroundSecondary
            border.color: root.cameraTestPassed ? Theme.successBorder :
                          root.cameraTestFailed ? Theme.errorBorder : Theme.divider
            radius: Theme.radiusMd
            visible: root.testResult.length > 0 || root.cameraTesting

            RowLayout {
                anchors.fill: parent
                anchors.margins: Theme.spacingMd
                spacing: Theme.spacingSm

                BusyIndicator {
                    visible: root.cameraTesting
                    running: root.cameraTesting
                    Layout.preferredWidth: 24
                    Layout.preferredHeight: 24
                }

                Text {
                    Layout.fillWidth: true
                    text: root.cameraTesting ? i18n.t("正在测试摄像头...") : root.testResult
                    font.pixelSize: Theme.fontSizeSm
                    color: root.cameraTestPassed ? Theme.success :
                           root.cameraTestFailed ? Theme.error : Theme.textSecondary
                    elide: Text.ElideRight
                }
            }
        }

        // Prompt message
        Text {
            Layout.fillWidth: true
            text: i18n.t("摄像头用于视觉识别功能。如需使用本地 VL 模型，请配置 API 地址和密钥。")
            font.pixelSize: Theme.fontSizeSm
            color: Theme.textPlaceholder
            wrapMode: Text.WordWrap
        }

        Item { Layout.fillHeight: true }
    }
}
