// Control panel
import QtQuick
import QtQuick.Layouts
import "../theme"
import "../controls"

Rectangle {
    id: root

    color: Theme.backgroundSecondary

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingMd

        // Input area
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            XTextField {
                id: inputField
                Layout.fillWidth: true
                placeholderText: i18n.t("输入文本消息...")

                Keys.onReturnPressed: sendText()
            }

            XButton {
                text: i18n.t("发送")
                onClicked: sendText()
            }
        }

        // Control button area
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            // Manual/automatic mode switching
            XButton {
                Layout.fillWidth: true
                text: mainModel.autoMode ? i18n.t("切换到手动") : i18n.t("切换到自动")
                variant: "secondary"
                onClicked: eventBridge.onAutoToggle()
            }

            // Speak button (manual mode)
            XButton {
                Layout.fillWidth: true
                text: mainModel.buttonText
                visible: !mainModel.autoMode
                onPressed: eventBridge.onButtonPress()
                onReleased: eventBridge.onButtonRelease()
            }

            // Interrupt button
            XButton {
                Layout.preferredWidth: 80
                text: i18n.t("中断")
                variant: "secondary"
                onClicked: eventBridge.onAbort()
            }
        }
    }

    function sendText() {
        let text = inputField.text.trim()
        if (text.length > 0) {
            eventBridge.onSendText(text)
            inputField.text = ""
        }
    }
}
