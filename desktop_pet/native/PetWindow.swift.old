import Cocoa
import WebKit

class PetWindow: NSObject, NSWindowDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    
    func start() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 360, height: 560),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "桌面小助手"
        window.level = .floating
        window.isMovableByWindowBackground = true
        window.titlebarAppearsTransparent = true
        window.backgroundColor = NSColor(red: 0.1, green: 0.1, blue: 0.18, alpha: 1)
        window.delegate = self
        
        // 右下角定位
        if let screen = NSScreen.main {
            let screenFrame = screen.visibleFrame
            let x = screenFrame.maxX - 370
            let y = screenFrame.minY + 60
            window.setFrameOrigin(NSPoint(x: x, y: y))
        }
        
        // WebView
        let config = WKWebViewConfiguration()
        webView = WKWebView(frame: window.contentView!.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.setValue(false, forKey: "drawsBackground")
        window.contentView?.addSubview(webView)
        
        // 加载游戏前端（复用已有 UI）
        webView.load(URLRequest(url: URL(string: "http://localhost:8000")!))
        
        window.makeKeyAndOrderFront(nil)
        app.run()
    }
}

let pet = PetWindow()
pet.start()
