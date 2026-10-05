// The lock screen (spec QSL): one ext-session-lock held by this process, a surface on
// every screen (also one that comes while locked, QSL-8), the password checked by PAM.
// Same look as the old hyprlock.conf. theme.py writes theme.json beside this file.
// INV-1: the session unlocks only in the PAM success handler below; a crash, a kill or
// any error leaves it locked. INV-3: every value read from outside has a default.
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Services.Pam
import QtQuick
import QtQuick.Effects

ShellRoot {
    id: root

    property string buffer: ""      // the password typed so far, shared by every screen
    property string submitted: ""   // what PAM is asked for, then cleared
    property int attempts: 0
    property string error: ""       // "Wrong password (N)" or a PAM error; "" when none
    property bool capsLock: false
    property string layout: "EN"
    readonly property string home: Quickshell.env("HOME")

    // theme.json (QSL-3): a missing file or key gives these defaults (INV-3)
    FileView {
        path: Quickshell.shellDir + "/theme.json"
        blockLoading: true
        adapter: JsonAdapter {
            id: theme
            property string fg: "#ffffff"
            property string bg0: "#1e2326"
            property string green: "#a7c080"
            property string yellow: "#dbbc7f"
            property string red: "#e67e80"
            property string edge_deep: "#475258"
            property string wallpaper: ""
            property string font: "sans-serif"
            property string gif: ""
        }
    }

    // a command run every `every` ms; the last text stays when a run fails or, for
    // `keepWhenEmpty`, prints nothing (QSL-10, INV-3)
    component Poll: Item {
        id: poll
        property var command: []
        property int every: 1000
        property bool keepWhenEmpty: true
        property string text: ""
        Process {
            id: proc
            command: poll.command
            stdout: StdioCollector {
                onStreamFinished: {
                    const out = this.text.trim();
                    if (out !== "" || !poll.keepWhenEmpty) poll.text = out;
                }
            }
        }
        Timer {
            interval: poll.every
            running: true
            repeat: true
            triggeredOnStart: true
            onTriggered: if (!proc.running) proc.running = true
        }
    }

    Poll {
        id: clock
        command: [root.home + "/.config/waybar/scripts/clock.sh", "now", "+%H:%M"]
        every: 1000
    }
    Poll {
        id: dateLine
        command: [root.home + "/.config/waybar/scripts/clock.sh", "now", "+%A, %d %B"]
        every: 60000
    }
    Poll {
        id: statusLine
        command: [root.home + "/.config/hypr/scripts/lockinfo.sh"]
        every: 5000
        keepWhenEmpty: false   // no battery and nothing playing is an empty line
    }

    // caps lock: asked of Hyprland at start and after each key
    Process {
        id: capsProc
        command: ["hyprctl", "devices", "-j"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const keyboards = JSON.parse(this.text).keyboards;
                    root.capsLock = keyboards.some(k => k.capsLock === true);
                } catch (e) {
                    root.capsLock = false;
                }
            }
        }
    }
    Component.onCompleted: capsProc.running = true
    Timer {
        id: capsSoon
        interval: 50
        onTriggered: if (!capsProc.running) capsProc.running = true
    }

    // lock.sh switches to the first layout (EN) before it starts this
    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (event.name !== "activelayout") return;
            root.layout = /persian|farsi/i.test(event.data) ? "FA" : "EN";
        }
    }

    PamContext {
        id: pam
        config: "gear5-lock"
        onPamMessage: {
            if (!responseRequired) return;
            respond(root.submitted);
            root.submitted = "";
        }
        onCompleted: result => {
            if (result === PamResult.Success) {
                // the only place the session unlocks (INV-1); quit is exit status 0
                lock.locked = false;
                Qt.quit();
            } else if (result === PamResult.Failed) {
                root.attempts += 1;
                root.error = "Wrong password (" + root.attempts + ")";
                console.warn(root.error);  // lock.log shows it too (tests/live_lock.py); qs hides console.log
            } else {
                root.error = "Authentication error";
            }
        }
        onError: root.error = "Authentication error"
    }

    function press(event) {
        if (pam.active) return;
        if (event.key === Qt.Key_CapsLock || event.key === Qt.Key_Shift) {
            capsSoon.restart();
            return;
        }
        capsSoon.restart();
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            // an empty password goes to PAM like any other and is refused there
            root.submitted = root.buffer;
            root.buffer = "";
            pam.start();
        } else if (event.key === Qt.Key_Backspace) {
            root.error = "";
            root.buffer = root.buffer.slice(0, -1);
        } else if (event.key === Qt.Key_Escape) {
            root.buffer = "";
        } else if (event.text.length > 0 && event.text.charCodeAt(0) >= 32
                   && event.text.charCodeAt(0) !== 127
                   && !(event.modifiers & Qt.ControlModifier)) {
            root.error = "";
            root.buffer += event.text;
        }
    }

    WlSessionLock {
        id: lock
        locked: true

        WlSessionLockSurface {
            color: theme.bg0

            FocusScope {
                anchors.fill: parent
                focus: true
                Component.onCompleted: forceActiveFocus()
                Keys.onPressed: event => {
                    root.press(event);
                    event.accepted = true;
                }

                Image {
                    id: wall
                    anchors.fill: parent
                    source: theme.wallpaper !== "" ? "file://" + theme.wallpaper : ""
                    fillMode: Image.PreserveAspectCrop
                    visible: false
                }
                MultiEffect {
                    anchors.fill: parent
                    source: wall
                    visible: wall.status === Image.Ready
                    blurEnabled: true
                    blur: 1.0
                    blurMax: 48
                    brightness: -0.4
                }

                // centered; `up` is hyprlock's position y: pixels above the center
                component Spot: Item {
                    property int up: 0
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.verticalCenterOffset: -up
                }

                // the theme's GIF, 200 px (QSL-9); none when the theme has none
                Spot {
                    up: 330
                    visible: theme.gif !== ""
                    AnimatedImage {
                        anchors.centerIn: parent
                        width: 200
                        height: 200
                        source: theme.gif !== "" ? "file://" + theme.gif : ""
                        fillMode: Image.PreserveAspectFit
                        playing: true
                    }
                }
                Spot {
                    up: 160
                    Text {
                        anchors.centerIn: parent
                        text: clock.text
                        color: theme.fg
                        font.family: theme.font
                        font.pointSize: 96
                        font.bold: true
                    }
                }
                Spot {
                    up: 70
                    Text {
                        anchors.centerIn: parent
                        text: dateLine.text
                        color: theme.green
                        font.family: theme.font
                        font.pointSize: 22
                        font.bold: true
                    }
                }
                Spot {
                    up: -40
                    Rectangle {
                        anchors.centerIn: parent
                        width: 320
                        height: 56
                        radius: 12
                        color: theme.bg0
                        border.width: 4
                        border.color: root.error !== "" ? theme.red
                                      : root.capsLock ? theme.yellow : theme.edge_deep
                        clip: true

                        Row {
                            anchors.centerIn: parent
                            spacing: 4
                            Repeater {
                                model: Math.min(root.buffer.length, 16)
                                Rectangle {
                                    width: 14
                                    height: 14
                                    radius: 7
                                    color: theme.fg
                                }
                            }
                        }
                        Text {
                            anchors.centerIn: parent
                            visible: root.buffer.length === 0
                            text: root.error !== "" ? root.error + "   " + root.layout
                                                    : "Password…   " + root.layout
                            color: root.error !== "" ? theme.red : theme.fg
                            font.family: theme.font
                            font.pointSize: 14
                            font.italic: root.error === ""
                        }
                    }
                }
                Spot {
                    up: -120
                    Text {
                        anchors.centerIn: parent
                        text: statusLine.text
                        textFormat: Text.StyledText   // lockinfo.sh escapes & < >
                        color: theme.fg
                        font.family: theme.font
                        font.pointSize: 15
                        font.bold: true
                    }
                }
            }
        }
    }
}
