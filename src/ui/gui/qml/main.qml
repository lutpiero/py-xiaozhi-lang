// The main entrance of the application
import QtQuick
import QtQuick.Window

import "windows"

// The main window is used as the root element; initially hidden, QmlAppHost.show_root determines whether to grab the front desk
MainWindow {
    id: mainWindow
    visible: false

    // Settings window - use Loader Lazy loading (as a standalone window)
    Loader {
        id: settingsLoader
        active: false
        source: "windows/SettingsWindow.qml"

        onLoaded: {
            item.visible = true
            item.raise()
            item.requestActivate()
        }
    }

    // Listens to the eventBridge signal to control the setting window
    Connections {
        target: eventBridge

        function onShowSettingsWindow() {
            if (settingsLoader.active) {
                // is loaded, directly displayed
                settingsLoader.item.visible = true
                settingsLoader.item.raise()
                settingsLoader.item.requestActivate()
            } else {
                // first load
                settingsLoader.active = true
            }
        }
    }
}
