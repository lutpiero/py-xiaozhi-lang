// System option setting page
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../theme"
import "../../controls"

ScrollView {
    id: root
    clip: true

    ColumnLayout {
        width: root.availableWidth
        spacing: Theme.spacingLg

        // Page title
        Text {
            text: i18n.t("系统选项")
            font.pixelSize: Theme.fontSizeXl
            font.weight: Font.DemiBold
            color: Theme.textPrimary
        }

        // Basic information area
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            // Area title
            Text {
                text: i18n.t("基本信息")
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            // Form item
            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: Theme.spacingMd
                columnSpacing: Theme.spacingLg

                Text {
                    text: i18n.t("客户端 ID")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: clientIdField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.clientId : ""
                    onEditingFinished: if (settingsModel) settingsModel.clientId = text
                    placeholderText: i18n.t("自动生成")
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: clientIdField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: i18n.t("设备 ID")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: deviceIdField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.deviceId : ""
                    onEditingFinished: if (settingsModel) settingsModel.deviceId = text
                    placeholderText: i18n.t("自动生成")
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: deviceIdField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: i18n.t("界面语言")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    XComboBox {
                        id: languageCombo
                        Layout.fillWidth: true
                        property var languageCodes: ["auto", "zh_CN", "en_US"]
                        model: [i18n.t("跟随系统"), i18n.t("简体中文"), "English"]
                        currentIndex: settingsModel ? Math.max(0, languageCodes.indexOf(settingsModel.language)) : 0
                        onActivated: function(index) {
                            if (settingsModel) settingsModel.language = languageCodes[index]
                        }
                        font.pixelSize: Theme.fontSizeSm
                    }
                    Text {
                        text: i18n.t("修改后重启生效；也可用 --lang 或 XIAOZHI_LANG 覆盖")
                        font.pixelSize: Theme.fontSizeXs
                        color: Theme.textPlaceholder
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
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

        // Echo cancellation area
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: i18n.t("回声消除")
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
                    text: i18n.t("启用")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                XSwitch {
                    id: aecEnabledSwitch
                    checked: settingsModel ? settingsModel.aecEnabled : false
                    onToggled: if (settingsModel) settingsModel.aecEnabled = checked
                }

                Text {
                    text: i18n.t("音乐并行播放")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                    opacity: aecEnabledSwitch.checked ? 1 : 0.45
                }
                XSwitch {
                    enabled: aecEnabledSwitch.checked
                    opacity: aecEnabledSwitch.checked ? 1 : 0.45
                    checked: settingsModel ? settingsModel.aecMusicParallel : true
                    onToggled: if (settingsModel) settingsModel.aecMusicParallel = checked
                }

                Text {
                    text: i18n.t("延迟补偿帧数")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                    opacity: aecEnabledSwitch.checked ? 1 : 0.45
                }
                XSpinBox {
                    Layout.preferredWidth: 120
                    enabled: aecEnabledSwitch.checked
                    opacity: aecEnabledSwitch.checked ? 1 : 0.45
                    from: 0
                    to: 20
                    value: settingsModel ? settingsModel.aecFrameDelay : 3
                    onValueModified: if (settingsModel) settingsModel.aecFrameDelay = value
                    font.pixelSize: Theme.fontSizeSm
                }

                Text {
                    text: i18n.t("噪声抑制预处理")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                    opacity: aecEnabledSwitch.checked ? 1 : 0.45
                }
                XSwitch {
                    enabled: aecEnabledSwitch.checked
                    opacity: aecEnabledSwitch.checked ? 1 : 0.45
                    checked: settingsModel ? settingsModel.aecEnablePreprocess : true
                    onToggled: if (settingsModel) settingsModel.aecEnablePreprocess = checked
                }
            }

            Text {
                Layout.fillWidth: true
                text: i18n.t("消除本应用 TTS/音乐的回声，启用后进入实时对话模式；音乐并行=TTS 播放时音乐闪避不暂停；延迟补偿=40ms+N×协议帧长，蓝牙设备可适当调大。修改后重启生效。")
                font.pixelSize: Theme.fontSizeXs
                color: Theme.textSecondary
                wrapMode: Text.WordWrap
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.divider
        }

        // Network configuration area
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: i18n.t("网络配置")
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
                    text: "WebSocket URL"
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: wsUrlField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.websocketUrl : ""
                    onEditingFinished: if (settingsModel) settingsModel.websocketUrl = text
                    placeholderText: "wss://..."
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: wsUrlField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: i18n.t("访问令牌")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                XTextField {
                    id: wsTokenField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.websocketToken : ""
                    onEditingFinished: if (settingsModel) settingsModel.websocketToken = text
                    isPassword: true
                }

                Text {
                    text: i18n.t("OTA 版本 URL")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: otaUrlField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.otaUrl : ""
                    onEditingFinished: if (settingsModel) settingsModel.otaUrl = text
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: otaUrlField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: i18n.t("授权 URL")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: authUrlField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.authorizationUrl : ""
                    onEditingFinished: if (settingsModel) settingsModel.authorizationUrl = text
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: authUrlField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: i18n.t("激活版本")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                XComboBox {
                    id: activationCombo
                    Layout.preferredWidth: 120
                    model: ["v1", "v2"]
                    currentIndex: settingsModel && settingsModel.activationVersion === "v2" ? 1 : 0
                    onActivated: function(index) {
                        if (settingsModel) settingsModel.activationVersion = index === 1 ? "v2" : "v1"
                    }
                    font.pixelSize: Theme.fontSizeSm
                }
            }
        }

        // Separator
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.divider
        }

        // MQTT configuration area
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: i18n.t("MQTT 配置")
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
                    text: i18n.t("服务端点")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: mqttEndpointField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.mqttEndpoint : ""
                    onEditingFinished: if (settingsModel) settingsModel.mqttEndpoint = text
                    placeholderText: "mqtt.example.com"
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: mqttEndpointField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: i18n.t("客户端 ID")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: mqttClientIdField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.mqttClientId : ""
                    onEditingFinished: if (settingsModel) settingsModel.mqttClientId = text
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: mqttClientIdField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: i18n.t("用户名")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: mqttUsernameField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.mqttUsername : ""
                    onEditingFinished: if (settingsModel) settingsModel.mqttUsername = text
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: mqttUsernameField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: i18n.t("密码")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                XTextField {
                    id: mqttPasswordField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.mqttPassword : ""
                    onEditingFinished: if (settingsModel) settingsModel.mqttPassword = text
                    isPassword: true
                }

                Text {
                    text: i18n.t("发布主题")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: mqttPubField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.mqttPublishTopic : ""
                    onEditingFinished: if (settingsModel) settingsModel.mqttPublishTopic = text
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: mqttPubField.activeFocus ? Theme.primary : "transparent"
                    }
                }

                Text {
                    text: i18n.t("订阅主题")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: mqttSubField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.mqttSubscribeTopic : ""
                    onEditingFinished: if (settingsModel) settingsModel.mqttSubscribeTopic = text
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: mqttSubField.activeFocus ? Theme.primary : "transparent"
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

        // Writable directory (cache/log/ Music, etc.)
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingMd

            Text {
                text: i18n.t("数据目录")
                font.pixelSize: Theme.fontSizeMd
                font.weight: Font.Medium
                color: Theme.textSecondary
            }

            Text {
                Layout.fillWidth: true
                text: i18n.t("配置文件仍在用户数据目录。点「选择」打开系统文件夹对话框；「默认」清空为系统默认。保存后下次启动会从旧目录复制到新路径。")
                font.pixelSize: Theme.fontSizeXs
                color: Theme.textSecondary
                wrapMode: Text.WordWrap
            }

            // Cache
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Text {
                    text: i18n.t("缓存目录")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: pathCacheField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.pathCacheDir : ""
                    onTextEdited: if (settingsModel) settingsModel.pathCacheDir = text
                    onEditingFinished: if (settingsModel) settingsModel.pathCacheDir = text
                    placeholderText: settingsModel ? settingsModel.pathDefaultCacheDir : ""
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: pathCacheField.activeFocus ? Theme.primary : "transparent"
                    }
                }
                Button {
                    text: i18n.t("选择")
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        var p = settingsModel.browseDirectory("cache")
                        if (p) pathCacheField.text = p
                    }
                }
                Button {
                    text: i18n.t("默认")
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        settingsModel.clearPathDir("cache")
                        pathCacheField.text = ""
                    }
                }
            }

            // Log
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Text {
                    text: i18n.t("日志目录")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: pathLogField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.pathLogDir : ""
                    onTextEdited: if (settingsModel) settingsModel.pathLogDir = text
                    onEditingFinished: if (settingsModel) settingsModel.pathLogDir = text
                    placeholderText: settingsModel ? settingsModel.pathDefaultLogDir : ""
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: pathLogField.activeFocus ? Theme.primary : "transparent"
                    }
                }
                Button {
                    text: i18n.t("选择")
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        var p = settingsModel.browseDirectory("log")
                        if (p) pathLogField.text = p
                    }
                }
                Button {
                    text: i18n.t("默认")
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        settingsModel.clearPathDir("log")
                        pathLogField.text = ""
                    }
                }
            }

            // Music
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Text {
                    text: i18n.t("音乐缓存")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: pathMusicField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.pathMusicCacheDir : ""
                    onTextEdited: if (settingsModel) settingsModel.pathMusicCacheDir = text
                    onEditingFinished: if (settingsModel) settingsModel.pathMusicCacheDir = text
                    placeholderText: settingsModel ? settingsModel.pathDefaultMusicCacheDir : ""
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: pathMusicField.activeFocus ? Theme.primary : "transparent"
                    }
                }
                Button {
                    text: i18n.t("选择")
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        var p = settingsModel.browseDirectory("music")
                        if (p) pathMusicField.text = p
                    }
                }
                Button {
                    text: i18n.t("默认")
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        settingsModel.clearPathDir("music")
                        pathMusicField.text = ""
                    }
                }
            }

            // Wake word
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Text {
                    text: i18n.t("唤醒词目录")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: pathKeywordsField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.pathKeywordsDir : ""
                    onTextEdited: if (settingsModel) settingsModel.pathKeywordsDir = text
                    onEditingFinished: if (settingsModel) settingsModel.pathKeywordsDir = text
                    placeholderText: settingsModel ? settingsModel.pathDefaultKeywordsDir : ""
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: pathKeywordsField.activeFocus ? Theme.primary : "transparent"
                    }
                }
                Button {
                    text: i18n.t("选择")
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        var p = settingsModel.browseDirectory("keywords")
                        if (p) pathKeywordsField.text = p
                    }
                }
                Button {
                    text: i18n.t("默认")
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        settingsModel.clearPathDir("keywords")
                        pathKeywordsField.text = ""
                    }
                }
            }

            // MCP plugin
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingSm
                Text {
                    text: i18n.t("MCP 插件目录")
                    font.pixelSize: Theme.fontSizeSm
                    color: Theme.textSecondary
                    Layout.preferredWidth: 100
                }
                TextField {
                    id: pathMcpField
                    Layout.fillWidth: true
                    text: settingsModel ? settingsModel.pathMcpPluginsDir : ""
                    onTextEdited: if (settingsModel) settingsModel.pathMcpPluginsDir = text
                    onEditingFinished: if (settingsModel) settingsModel.pathMcpPluginsDir = text
                    placeholderText: settingsModel ? settingsModel.pathDefaultMcpPluginsDir : ""
                    font.pixelSize: Theme.fontSizeSm
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.backgroundSecondary
                        border.color: pathMcpField.activeFocus ? Theme.primary : "transparent"
                    }
                }
                Button {
                    text: i18n.t("选择")
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        var p = settingsModel.browseDirectory("mcp")
                        if (p) pathMcpField.text = p
                    }
                }
                Button {
                    text: i18n.t("默认")
                    font.pixelSize: Theme.fontSizeSm
                    Layout.preferredWidth: 64
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.pressed ? Theme.backgroundHover : Theme.backgroundSecondary
                        border.width: 1
                        border.color: Theme.divider
                    }
                    contentItem: Text {
                        text: parent.text
                        font.pixelSize: Theme.fontSizeSm
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (!settingsModel) return
                        settingsModel.clearPathDir("mcp")
                        pathMcpField.text = ""
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: settingsModel ? settingsModel.pathHints : ""
                font.pixelSize: Theme.fontSizeXs
                color: Theme.textSecondary
                wrapMode: Text.WordWrap
            }
        }

        Item { Layout.fillHeight: true }
    }
}
