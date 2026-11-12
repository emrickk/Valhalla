// SPDX-License-Identifier: AGPL-3.0-or-later
import AppKit

final class LoginHelper: NSObject, NSApplicationDelegate {
    let root = Bundle.main.bundleURL.deletingLastPathComponent().deletingLastPathComponent().path
    let node = Bundle.main.object(forInfoDictionaryKey: "NodeExecutable") as! String
    var window: NSWindow!
    let status = NSTextField(wrappingLabelWithString: "Waiting for the Lenovo login callback.\n\nFinish signing in, then choose Open MFD Login in your browser.")
    var busy = false
    lazy var loginButton = NSButton(title: "Start fresh login", target: self, action: #selector(startLogin))

    func applicationDidFinishLaunching(_ notification: Notification) {
        showWindow()
    }

    func showWindow() {
        if window == nil {
            window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 560, height: 220),
                              styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
            window.title = "MFD Login"
            window.isReleasedWhenClosed = false
            status.frame = NSRect(x: 24, y: 70, width: 512, height: 120)
            status.font = .systemFont(ofSize: 16)
            status.isSelectable = true
            window.contentView!.addSubview(status)
            loginButton.frame = NSRect(x: 20, y: 18, width: 180, height: 34)
            window.contentView!.addSubview(loginButton)
            window.center()
        }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func startLogin() {
        guard !busy else { return }
        busy = true
        loginButton.isEnabled = false
        status.stringValue = "Requesting a fresh Lenovo login…"
        DispatchQueue.global().async { [self] in
            var loginURL: URL?
            do {
                let task = Process()
                task.executableURL = URL(fileURLWithPath: node)
                task.arguments = [root + "/tools/razr2024/lmsa.mjs", "prepare"]
                let output = Pipe()
                task.standardOutput = output
                task.standardError = FileHandle.nullDevice
                try task.run()
                let data = output.fileHandleForReading.readDataToEndOfFile()
                task.waitUntilExit()
                if task.terminationStatus == 0, let text = String(data: data, encoding: .utf8) {
                    loginURL = text.split(separator: "\n").compactMap { URL(string: String($0)) }.first {
                        $0.scheme == "https" && $0.host == "passport-glb.lenovo.com" && $0.path == "/v1.0/utility/lenovoid/oauth2/authorize"
                    }
                }
                if loginURL != nil {
                    try Data().write(to: URL(fileURLWithPath: root + "/.razr-work/auth/armed"), options: .atomic)
                    try Data("{\"success\":false}".utf8).write(to: URL(fileURLWithPath: root + "/.razr-work/auth/result.json"), options: .atomic)
                }
            } catch { loginURL = nil }
            let url = loginURL
            DispatchQueue.main.async { [self] in
                busy = false
                loginButton.isEnabled = true
                if let url = url {
                    status.stringValue = "A fresh login has opened in your default browser.\n\nSign in, then allow the browser to open MFD Login."
                    NSWorkspace.shared.open(url)
                } else {
                    status.stringValue = "Could not obtain a fresh Lenovo login. Please try again."
                }
            }
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showWindow()
        return true
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        showWindow()
        guard !busy, urls.count == 1 else { return }
        busy = true
        loginButton.isEnabled = false
        status.stringValue = "Callback received. Checking the Lenovo session…"
        let uri = urls[0].absoluteString
        DispatchQueue.global().async { [self] in
            var message = "The callback could not be processed. Start a fresh login."
            let callback = URL(fileURLWithPath: root + "/.razr-work/auth/callback.txt")
            do {
                try Data(uri.utf8).write(to: callback, options: .atomic)
                try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: callback.path)
                let task = Process()
                task.executableURL = URL(fileURLWithPath: root + "/.razr-runtime/venv/bin/python")
                task.arguments = [root + "/tools/razr2024/callback.py"]
                let output = Pipe()
                task.standardOutput = output
                task.standardError = FileHandle.nullDevice
                try task.run()
                let data = output.fileHandleForReading.readDataToEndOfFile()
                task.waitUntilExit()
                if task.terminationStatus == 0, let text = String(data: data, encoding: .utf8), !text.isEmpty {
                    message = text.trimmingCharacters(in: .whitespacesAndNewlines)
                }
            } catch {
                try? Data().write(to: callback)
            }
            let result = message
            DispatchQueue.main.async { [self] in
                status.stringValue = result
                busy = false
                loginButton.isEnabled = true
                showWindow()
            }
        }
    }
}

let app = NSApplication.shared
let delegate = LoginHelper()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
