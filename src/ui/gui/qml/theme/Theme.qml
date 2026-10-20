// Theme System - Define colors, fonts, spacing, etc.
pragma Singleton
import QtQuick

QtObject {
    id: theme

    // ========== Responsive Breakpoints ==========
    readonly property int breakpointSm: 480
    readonly property int breakpointMd: 768
    readonly property int breakpointLg: 1024

    // Current window width (set by AppWindow)
    property int windowWidth: 800

    // Scaling factor
    readonly property real scaleFactor: {
        if (windowWidth < breakpointSm) return 0.8
        if (windowWidth < breakpointMd) return 0.9
        return 1.0
    }

    // ========== Color ==========
    // Main Color System
    readonly property color primary: "#165DFF"
    readonly property color primaryHover: "#4080FF"
    readonly property color primaryPressed: "#0E42D2"
    readonly property color primaryLight: "#E8F3FF"      // Light blue background
    readonly property color primaryText: "#2196F3"       // Blue text

    // Function color
    readonly property color success: "#00B42A"
    readonly property color successLight: "#E8FFEA"      // Success light background
    readonly property color successBorder: "#B7EB8F"     // Success border

    readonly property color warning: "#FF7D00"
    readonly property color warningLight: "#FFF7E8"      // Warning light background
    readonly property color warningBorder: "#FFE58F"     // Warning border

    readonly property color error: "#F53F3F"
    readonly property color errorHover: "#FF7875"        // wrong hover
    readonly property color errorLight: "#FFF2F0"        // wrong light background
    readonly property color errorBorder: "#FFCCC7"       // wrong border

    // Background color
    readonly property color background: "#FFFFFF"
    readonly property color backgroundSecondary: "#F7F8FA"
    readonly property color backgroundHover: "#F2F3F5"

    // Text color
    readonly property color textPrimary: "#1D2129"
    readonly property color textSecondary: "#4E5969"
    readonly property color textPlaceholder: "#86909C"

    // Border dividing line
    readonly property color border: "#E5E6EB"
    readonly property color divider: "#F2F3F5"

    // ========== Font Size ==========
    readonly property int fontSizeXs: Math.round(10 * scaleFactor)
    readonly property int fontSizeSm: Math.round(12 * scaleFactor)
    readonly property int fontSizeMd: Math.round(14 * scaleFactor)
    readonly property int fontSizeLg: Math.round(16 * scaleFactor)
    readonly property int fontSizeXl: Math.round(20 * scaleFactor)
    readonly property int fontSizeXxl: Math.round(24 * scaleFactor)

    // ========== Spacing ==========
    readonly property int spacingXs: Math.round(4 * scaleFactor)
    readonly property int spacingSm: Math.round(8 * scaleFactor)
    readonly property int spacingMd: Math.round(12 * scaleFactor)
    readonly property int spacingLg: Math.round(16 * scaleFactor)
    readonly property int spacingXl: Math.round(20 * scaleFactor)
    readonly property int spacingXxl: Math.round(24 * scaleFactor)

    // ========== Rounded Corners ==========
    readonly property int radiusSm: 4
    readonly property int radiusMd: 8
    readonly property int radiusLg: 12
    readonly property int radiusXl: 16

    // ========== Shade ==========
    readonly property color shadowColor: "#15000000"      // main shadow color
    readonly property color shadowLight: "#08000000"      // Light shadow (outer layer)
    readonly property color shadowMedium: "#06000000"     // medium shadow (middle layer)
    readonly property color shadowSubtle: "#04000000"     // micro shadow (Outermost layer)
    readonly property int shadowRadius: 12

    // ========== Animation ==========
    readonly property int animationFast: 150
    readonly property int animationNormal: 200
    readonly property int animationSlow: 300

    // ========== Window ==========
    readonly property int windowRadius: 8
    readonly property int titleBarHeight: Math.round(40 * scaleFactor)
    readonly property int resizeMargin: 8

    // ========== Font Family ==========
    readonly property string fontFamily: Qt.platform.os === "osx" ? "PingFang SC" : (Qt.platform.os === "windows" ? "Microsoft YaHei UI" : "sans-serif")
    readonly property string fontFamilyMono: Qt.platform.os === "osx" ? "SF Mono" : "monospace"

    // ========== Platform Detection ==========
    readonly property string currentPlatform: Qt.platform.os  // "osx", "windows", "linux"
    readonly property bool isMacOS: Qt.platform.os === "osx"
    readonly property bool isWindows: Qt.platform.os === "windows"
    readonly property bool isLinux: Qt.platform.os === "linux"
    readonly property bool titleButtonsOnLeft: isMacOS  // macOS button on the left
}
