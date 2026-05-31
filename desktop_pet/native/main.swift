import AppKit

let app = NSApplication.shared
let d = AppDelegate()
app.delegate = d
app.setActivationPolicy(.accessory)
app.run()
_ = d
