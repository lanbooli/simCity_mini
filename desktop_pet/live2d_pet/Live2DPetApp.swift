import SwiftUI
import AppKit
import MetalKit
import AVFoundation

// MARK: - NPC
struct NpcItem: Identifiable {
    let id, name, mood, avatarUrl: String
}

// MARK: - Simple Metal Delegate (just calls L2DPetModel)
class PetMetalDelegate: NSObject, MTKViewDelegate {
    let petModel: L2DPetModel
    var commandQueue: MTLCommandQueue?
    
    init(petModel: L2DPetModel) {
        self.petModel = petModel
    }
    
    func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) {}
    
    func draw(in view: MTKView) {
        guard let drawable = view.currentDrawable,
              let cmdBuf = commandQueue?.makeCommandBuffer() else { return }
        petModel.draw(to: drawable, commandBuffer: cmdBuf)
        cmdBuf.present(drawable)
        cmdBuf.commit()
    }
}

// MARK: - Session
class Live2DSession: ObservableObject {
    @Published var connected = false
    @Published var statusText = "连接中..."
    @Published var npcs: [NpcItem] = []
    @Published var selectedNpcId = ""
    @Published var selectedNpcName = ""
    @Published var npcMood = ""
    @Published var showMenu = false
    @Published var showInfo = false
    @Published var inputText = ""
    @Published var npcBubble = ""
    @Published var playerBubble = ""
    @Published var showBubbles = false
    @Published var favChange = ""
    @Published var npcInfo = ""

    let petModel: L2DPetModel

    private var task: URLSessionWebSocketTask?
    private var session: URLSession?
    private var timer: Timer?
    private var lastTick = Date()
    private var player: AVAudioPlayer?

    let sceneNames: [String:String] = [
        "scene_coffee_shop":"阳光咖啡店","scene_park":"中心公园","scene_school":"小镇高中",
        "scene_library":"公共图书馆","scene_market":"便民超市","scene_hospital":"小镇医院",
        "scene_restaurant":"小镇餐厅","scene_bar":"夜色酒吧","scene_gym":"健身中心",
        "scene_cinema":"小镇影院","scene_clothing":"服装店","scene_station":"小镇车站",
        "scene_riverside":"河边步道","scene_office":"镇政府","scene_arcade":"游戏厅",
        "apt_a":"阳光公寓A","apt_b":"阳光公寓B","apt_c":"阳光公寓C","apt_d":"阳光公寓D",
        "home_player":"我的公寓"
    ]
    let relNames: [String:String] = [
        "stranger":"陌生人","acquaintance":"认识","friend":"朋友","best_friend":"好友",
        "boyfriend":"男友","girlfriend":"女友","spouse":"伴侣",
        "dislike":"讨厌","enemy":"仇敌","parent":"父母","sibling":"兄弟姐妹","child":"子女"
    ]

    init(petModel: L2DPetModel) {
        self.petModel = petModel
    }

    func connect() {
        session = URLSession(configuration: .default)
        guard let u = URL(string: "ws://localhost:8000/ws/game?player_id=player_001") else { return }
        task = session?.webSocketTask(with: u); task?.resume()
        receive(); loadNpcs()
        
        print("[Session] Model ready, drawables=\(petModel.drawableCount)")

        lastTick = Date()
        timer = Timer.scheduledTimer(withTimeInterval: 1.0/60.0, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            let now = Date(); let dt = Float(now.timeIntervalSince(self.lastTick))
            self.lastTick = now; self.petModel.update(withDeltaTime: min(dt, 0.1))
        }
    }

    func loadNpcs() {
        guard let u = URL(string: "http://localhost:8000/api/v1/npcs") else { return }
        URLSession.shared.dataTask(with: u) { [weak self] d, _, _ in
            guard let d = d, let j = try? JSONSerialization.jsonObject(with: d) as? [String:Any],
                  let list = j["data"] as? [[String:Any]] else { return }
            var infos: [NpcItem] = []
            for item in list {
                let id = item["id"] as? String ?? ""
                let name = item["name"] as? String ?? ""
                let mood = item["current_mood"] as? String ?? ""
                var av = ""
                if let ap = item["appearance"] as? [String:Any] { av = ap["avatar"] as? String ?? "" }
                infos.append(NpcItem(id: id, name: name, mood: mood, avatarUrl: av))
            }
            DispatchQueue.main.async {
                self?.npcs = infos; self?.connected = true; self?.statusText = "就绪"
                if let f = infos.first, self?.selectedNpcId.isEmpty == true { self?.select(f) }
            }
        }.resume()
    }

    func select(_ n: NpcItem) {
        selectedNpcId = n.id; selectedNpcName = n.name; npcMood = n.mood
        npcBubble = ""; playerBubble = ""; showBubbles = false; showInfo = false
        setMood(n.mood); fetchNpcInfo()
    }

    func selectNpc(id: String, name: String, mood: String) {
        select(NpcItem(id: id, name: name, mood: mood, avatarUrl: ""))
    }

    func setMood(_ mood: String) {
        switch mood {
        case "开心", "happy": petModel.setParameter("ParamMouthForm", value: 0.6)
        case "难过", "sad": petModel.setParameter("ParamMouthForm", value: -0.5)
        default: break
        }
    }

    func fetchNpcInfo() {
        guard !selectedNpcId.isEmpty, let u = URL(string: "http://localhost:8000/api/v1/npc/\(selectedNpcId)") else { return }
        URLSession.shared.dataTask(with: u) { [weak self] d, _, _ in
            guard let d = d, let j = try? JSONSerialization.jsonObject(with: d) as? [String:Any],
                  let data = j["data"] as? [String:Any] else { return }
            guard let self = self else { return }
            let sc = data["current_scene_id"] as? String ?? "?"
            let scName = self.sceneNames[sc] ?? (data["current_scene_name"] as? String ?? sc)
            let loc = data["current_room"] as? String ?? ""
            let phys = data["physiology"] as? [String:Any] ?? [:]
            let hu = (phys["hunger"] as? Int) ?? 50
            let en = (phys["energy"] as? Int) ?? 50

            var relText = ""
            if let ru = URL(string: "http://localhost:8000/api/v1/npc/\(self.selectedNpcId)/relationship/player_001") {
                if let rd = try? Data(contentsOf: ru),
                   let rj = try? JSONSerialization.jsonObject(with: rd) as? [String:Any],
                   let rd2 = rj["data"] as? [String:Any] {
                    let rt = rd2["relationship_type"] as? String ?? ""
                    let fav = rd2["favorability"] as? Int ?? 0
                    let fam = rd2["familiarity"] as? Int ?? 0
                    relText = "\n\u{1F465} \(self.relNames[rt] ?? rt) \u{2764}\u{FE0F}\(fav) \u{1F44B}\(fam)"
                }
            }

            DispatchQueue.main.async {
                self.npcInfo = "📍 \(scName) \(loc)\n🍽️\(hu) ⚡\(en)\(relText)"
            }
        }.resume()
    }

    func sendMessage(_ text: String) {
        guard !text.isEmpty, !selectedNpcId.isEmpty else { return }
        let msg: [String:Any] = [
            "type":"npc_chat","npc_id":selectedNpcId,"player_id":"player_001","message":text
        ]
        guard let jd = try? JSONSerialization.data(withJSONObject: msg),
              let js = String(data: jd, encoding: .utf8) else { return }
        let wm = URLSessionWebSocketTask.Message.string(js)
        task?.send(wm) { _ in }
        DispatchQueue.main.async {
            self.playerBubble = text; self.showBubbles = true
        }
    }

    func receive() {
        task?.receive { [weak self] r in
            guard let self = self else { return }
            switch r {
            case .success(let msg):
                if case .string(let s) = msg,
                   let d = s.data(using: .utf8),
                   let j = try? JSONSerialization.jsonObject(with: d) as? [String:Any],
                   let t = j["type"] as? String {
                    DispatchQueue.main.async {
                        if t == "npc_reply" || t == "npc_chat" {
                            self.npcBubble = j["message"] as? String ?? s
                            self.showBubbles = true
                            self.favChange = j["fav_change"] as? String ?? ""
                            if let voice = j["voice"] as? String {
                                self.playVoice(voice)
                            }
                        } else if t == "npc_action" {
                            self.npcBubble = j["description"] as? String ?? s
                            self.showBubbles = true
                            if let mood = j["mood"] as? String { self.setMood(mood) }
                        }
                    }
                }
            default: break
            }
            self.receive()
        }
    }

    func playVoice(_ path: String) {
        guard let u = URL(string: "http://localhost:8000/\(path)") else { return }
        URLSession.shared.dataTask(with: u) { [weak self] d, _, _ in
            guard let d = d, let self = self else { return }
            DispatchQueue.main.async {
                self.player = try? AVAudioPlayer(data: d)
                self.player?.play()
            }
        }.resume()
    }
}

// MARK: - Overlay UI
struct OverlayView: View {
    @ObservedObject var session: Live2DSession

    var body: some View {
        ZStack {
            // Transparent background — Metal renders underneath
            Color.clear
            
            VStack(spacing: 0) {
                // Top bar
                HStack {
                    Text(session.selectedNpcName.isEmpty ? "选择角色" : session.selectedNpcName)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color.black.opacity(0.6))
                        .cornerRadius(4)
                    Spacer()
                    Button(action: { session.showMenu.toggle() }) {
                        Image(systemName: "line.3.horizontal")
                            .font(.system(size: 12))
                            .foregroundColor(.white)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 6)
                .padding(.top, 4)
                
                Spacer()
                
                // Bubbles
                if session.showBubbles {
                    VStack(spacing: 4) {
                        if !session.playerBubble.isEmpty {
                            Text(session.playerBubble)
                                .font(.system(size: 11))
                                .foregroundColor(.black)
                                .padding(6)
                                .background(Color.white.opacity(0.85))
                                .cornerRadius(8)
                                .frame(maxWidth: 200, alignment: .trailing)
                        }
                        if !session.npcBubble.isEmpty {
                            Text(session.npcBubble)
                                .font(.system(size: 11))
                                .foregroundColor(.white)
                                .padding(6)
                                .background(Color.black.opacity(0.75))
                                .cornerRadius(8)
                                .frame(maxWidth: 200, alignment: .leading)
                        }
                    }
                    .padding(.horizontal, 8)
                }
                
                // Fav change
                if !session.favChange.isEmpty {
                    Text(session.favChange)
                        .font(.system(size: 10))
                        .foregroundColor(.yellow)
                        .padding(.bottom, 2)
                }
                
                // Input bar
                HStack(spacing: 4) {
                    TextField("输入...", text: $session.inputText)
                        .textFieldStyle(.plain)
                        .font(.system(size: 12))
                        .foregroundColor(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 3)
                        .background(Color.black.opacity(0.5))
                        .cornerRadius(4)
                        .onSubmit {
                            session.sendMessage(session.inputText)
                            session.inputText = ""
                        }
                    Button("发送") {
                        session.sendMessage(session.inputText)
                        session.inputText = ""
                    }
                    .font(.system(size: 11))
                    .foregroundColor(.white)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Color.blue.opacity(0.7))
                    .cornerRadius(4)
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 6)
                .padding(.bottom, 6)
            }
        }
        // NPC menu popup
        .overlay(alignment: .topTrailing) {
            if session.showMenu {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(session.npcs) { n in
                        Button(action: {
                            session.select(n); session.showMenu = false
                        }) {
                            HStack {
                                Text(n.name).font(.system(size: 11)).foregroundColor(.white)
                                Spacer()
                                if session.selectedNpcId == n.id {
                                    Image(systemName: "checkmark").font(.system(size: 10)).foregroundColor(.green)
                                }
                            }
                            .padding(.horizontal, 8).padding(.vertical, 3)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(4)
                .background(Color.black.opacity(0.8))
                .cornerRadius(6)
                .frame(width: 160)
                .offset(x: -4, y: 24)
            }
        }
        // NPC info popup (context menu style)
        .overlay(alignment: .topLeading) {
            if session.showInfo && !session.npcInfo.isEmpty {
                Text(session.npcInfo)
                    .font(.system(size: 10))
                    .foregroundColor(.white)
                    .padding(6)
                    .background(Color.black.opacity(0.75))
                    .cornerRadius(6)
                    .offset(x: 4, y: 24)
            }
        }
        .contextMenu {
            Button("角色信息") { session.showInfo.toggle(); session.fetchNpcInfo() }
        }
    }
}

// MARK: - App Delegate
class PetWindow: NSWindow { override var canBecomeKey: Bool { true } }

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: PetWindow!
    var session: Live2DSession!
    var mtkView: MTKView!
    var metalDelegate: PetMetalDelegate!
    
    static let modelPath: String = {
        // Resolve model path relative to the app bundle or source tree
        let fm = FileManager.default
        let bundleModel = Bundle.main.resourcePath.map { $0 + "/Model/Haru" } ?? ""
        if fm.fileExists(atPath: bundleModel + "/Haru.model3.json") {
            return bundleModel
        }
        // Fallback: relative to executable
        let exeDir = NSString(string: Bundle.main.executablePath ?? ".").deletingLastPathComponent
        let srcModel = exeDir + "/Model/Haru"
        if fm.fileExists(atPath: srcModel + "/Haru.model3.json") {
            return srcModel
        }
        // Development fallback
        return NSString(string: exeDir).deletingLastPathComponent + "/Model/Haru"
    }()

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard let device = MTLCreateSystemDefaultDevice() else { fatalError("No Metal") }
        
        // Create L2DPetModel (official Cubism renderer)
        let petModel = L2DPetModel(modelDir: AppDelegate.modelPath, device: device, size: CGSize(width: 320, height: 480))
        guard let model = petModel else {
            fatalError("Failed to create L2DPetModel")
        }
        
        let s = Live2DSession(petModel: model)
        self.session = s
        
        // Metal delegate
        metalDelegate = PetMetalDelegate(petModel: model)
        metalDelegate.commandQueue = device.makeCommandQueue()
        
        // MTKView
        mtkView = MTKView(frame: NSRect(x: 0, y: 0, width: 320, height: 480), device: device)
        mtkView.clearColor = MTLClearColor(red: 0, green: 0, blue: 0, alpha: 0)
        mtkView.colorPixelFormat = .bgra8Unorm
        mtkView.preferredFramesPerSecond = 60
        mtkView.enableSetNeedsDisplay = false
        mtkView.wantsLayer = true
        mtkView.layer?.isOpaque = false
        mtkView.layer?.backgroundColor = NSColor.clear.cgColor
        mtkView.delegate = metalDelegate
        
        // Overlay UI
        let overlay = OverlayView(session: s)
        let hostView = NSHostingView(rootView: overlay)
        hostView.frame = NSRect(x: 0, y: 0, width: 320, height: 480)
        hostView.wantsLayer = true
        hostView.layer?.isOpaque = false
        hostView.layer?.backgroundColor = NSColor.clear.cgColor
        
        // Container
        let container = NSView(frame: NSRect(x: 0, y: 0, width: 320, height: 480))
        container.wantsLayer = true
        container.addSubview(mtkView)
        container.addSubview(hostView)
        
        // Window
        window = PetWindow(contentRect: NSRect(x: 0, y: 0, width: 320, height: 480),
                           styleMask: [.borderless], backing: .buffered, defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .stationary]
        window.isMovableByWindowBackground = true
        window.contentView = container
        
        if let screen = NSScreen.main {
            window.setFrameOrigin(NSPoint(x: screen.visibleFrame.maxX - 340,
                                          y: screen.visibleFrame.minY + 40))
        }
        window.makeKeyAndOrderFront(nil)
        
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { e in
            if e.modifierFlags.contains(.command),
               e.charactersIgnoringModifiers == "w" || e.charactersIgnoringModifiers == "q" {
                NSApplication.shared.terminate(nil); return nil
            }; return e
        }
        
        s.connect()
        print("[App] Window created, Metal view: \(mtkView.frame), session started")
    }
}

// MARK: - main (called from App/main.swift)
func runLive2DPetApp() {
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.setActivationPolicy(.accessory)
    app.run()
}
