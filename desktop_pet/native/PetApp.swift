import SwiftUI
import AppKit
import AVFoundation

struct NpcItem: Identifiable {
    let id, name, mood, avatarUrl: String
    var loc: String = ""; var stamina = 50; var hunger = 50; var energy = 50
}

// MARK: - Session
class GameSession: ObservableObject {
    @Published var connected = false; @Published var statusText = "连接中..."
    @Published var npcs: [NpcItem] = []; @Published var npcNames: [String] = []
    @Published var selectedNpcId = ""; @Published var selectedNpcName = ""
    @Published var npcMood = ""; @Published var npcAvatar: NSImage?
    @Published var showMenu = false; @Published var showInfo = false
    @Published var inputText = ""
    @Published var npcBubble = ""; @Published var playerBubble = ""; @Published var showBubbles = false
    @Published var favChange = ""
    @Published var npcInfo = ""  // 角色信息

    private var task: URLSessionWebSocketTask?; private var session: URLSession?
    private var player: AVAudioPlayer?
    private let root = NSHomeDirectory() + "/lanbooassistent/city-town"

    func connect() {
        session = URLSession(configuration: .default)
        guard let u = URL(string: "ws://localhost:8000/ws/game?player_id=player_001") else { return }
        task = session?.webSocketTask(with: u); task?.resume()
        receive(); loadNpcs()
    }

    func loadNpcs() {
        guard let u = URL(string: "http://localhost:8000/api/v1/npcs") else { return }
        URLSession.shared.dataTask(with: u) { [weak self] d, _, _ in
            guard let d = d, let j = try? JSONSerialization.jsonObject(with: d) as? [String:Any],
                  let list = j["data"] as? [[String:Any]] else { return }
            var infos: [NpcItem] = []
            for item in list {
                let id = item["id"] as? String ?? ""; let name = item["name"] as? String ?? ""
                let mood = item["current_mood"] as? String ?? ""
                var av = ""
                if let ap = item["appearance"] as? [String:Any] { av = ap["avatar"] as? String ?? "" }
                infos.append(NpcItem(id: id, name: name, mood: mood, avatarUrl: av))
            }
            DispatchQueue.main.async {
                self?.npcs = infos; self?.npcNames = infos.map(\.name)
                self?.connected = true; self?.statusText = "就绪"
                if let f = infos.first, self?.selectedNpcId.isEmpty == true {
                    self?.select(f)
                }
            }
        }.resume()
    }

    func select(_ n: NpcItem) {
        selectedNpcId = n.id; selectedNpcName = n.name; npcMood = n.mood
        npcBubble = ""; playerBubble = ""; showBubbles = false; showInfo = false
        if !n.avatarUrl.isEmpty, let img = NSImage(contentsOfFile: root+"/frontend/"+n.avatarUrl) { npcAvatar = img }
        else { npcAvatar = nil }
        fetchNpcInfo()
    }

    // 场景名映射
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
    
    func fetchNpcInfo() {
        guard !selectedNpcId.isEmpty, let u = URL(string: "http://localhost:8000/api/v1/npc/\(selectedNpcId)") else { return }
        URLSession.shared.dataTask(with: u) { [weak self] d, _, _ in
            guard let d = d, let j = try? JSONSerialization.jsonObject(with: d) as? [String:Any],
                  let data = j["data"] as? [String:Any] else { return }
            guard let self = self else { return }
            let sc = data["current_scene_id"] as? String ?? "?"
            let scName = sceneNames[sc] ?? (data["current_scene_name"] as? String ?? sc)
            let loc = data["current_room"] as? String ?? ""
            let attrs = data["attributes"] as? [String:Any] ?? [:]
            let phys = data["physiology"] as? [String:Any] ?? [:]
            let st = (attrs["stamina"] as? Int) ?? (phys["stamina"] as? Int) ?? 50
            let hu = (phys["hunger"] as? Int) ?? 50
            let en = (phys["energy"] as? Int) ?? (attrs["energy"] as? Int) ?? 50
            
            // 立即设置基本信息（无需等待关系请求）
            DispatchQueue.main.async {
                var info = "📍 \(scName)"
                if !loc.isEmpty { info += " · \(loc)" }
                info += "\n💪体力:\(st) 🍖饱食:\(hu) ⚡精力:\(en)"
                if let career = data["career"] as? String, !career.isEmpty { info += "\n💼 \(career)" }
                self.npcInfo = info
            }
            
            // 异步获取关系信息（不阻塞）
            let relURL = "http://localhost:8000/api/v1/npc/\(selectedNpcId)/relationship/player_001"
            if let ru = URL(string: relURL) {
                URLSession.shared.dataTask(with: ru) { [weak self] rd, _, _ in
                    guard let self = self else { return }
                    if let rd = rd,
                       let rj = try? JSONSerialization.jsonObject(with: rd) as? [String:Any],
                       let rd2 = rj["data"] as? [String:Any] {
                        let rt = rd2["relationship_type"] as? String ?? ""
                        let fav = rd2["favorability"] as? Int ?? 0
                        let fam = rd2["familiarity"] as? Int ?? 0
                        let relText = "\n👥 \(relNames[rt] ?? rt) ❤️\(fav) 👋\(fam)"
                        DispatchQueue.main.async {
                            self.npcInfo += relText
                        }
                    }
                }.resume()
            }
        }.resume()
    }

    func send(_ t: String) {
        guard let task, !selectedNpcId.isEmpty else { return }
        let m: [String:Any] = ["type":"dialogue_send","data":["npc_id":selectedNpcId,"content":t]]
        if let d = try? JSONSerialization.data(withJSONObject: m), let s = String(data:d, encoding:.utf8) {
            task.send(.string(s)) { _ in }
        }
        playerBubble = t; npcBubble = ""; showBubbles = true
    }

    private func receive() {
        task?.receive { [weak self] r in
            defer { self?.receive() }
            guard case .success(let m) = r, case .string(let t) = m,
                  let d = t.data(using: .utf8),
                  let j = try? JSONSerialization.jsonObject(with: d) as? [String:Any],
                  let ty = j["type"] as? String, let dt = j["data"] as? [String:Any] else {
                DispatchQueue.main.asyncAfter(deadline: .now()+3) { self?.connect() }; return
            }
            DispatchQueue.main.async {
                switch ty {
                case "dialogue_response":
                    if let c = dt["content"] as? String, !c.isEmpty {
                        self?.npcBubble = c; self?.playerBubble = ""; self?.showBubbles = true
                    }
                    if let fc = dt["favorability_change"] as? String, let fv = Int(fc), fv != 0 {
                        self?.favChange = fv > 0 ? "❤️+\(fv)" : "💔\(fv)"
                        DispatchQueue.main.asyncAfter(deadline: .now()+3) { self?.favChange = "" }
                    }
                    if let m = dt["new_mood"] as? String { self?.npcMood = m }
                    self?.fetchNpcInfo()
                case "tts_audio":
                    if let u = dt["audio_url"] as? String { self?.playAudio(u) }
                case "greeting":
                    if let c = dt["content"] as? String, let n = dt["npc_name"] as? String {
                        self?.npcBubble = "\(n): \(c)"; self?.playerBubble = ""; self?.showBubbles = true
                    }
                    self?.fetchNpcInfo()
                default: break
                }
            }
        }
    }

    func playAudio(_ u: String) {
        var p = u; if u.hasPrefix("/assets/") { p = root+"/frontend"+u }
        guard FileManager.default.fileExists(atPath: p),
              let pl = try? AVAudioPlayer(contentsOf: URL(fileURLWithPath: p)) else { return }
        player = pl; pl.play()
    }
}

// MARK: - 气泡
struct BubbleBox: View {
    let text: String; let isPlayer: Bool
    @State private var y: CGFloat = 10; @State private var o: Double = 0

    func clean(_ s: String) -> String {
        var t = s
        t = t.replacingOccurrences(of: "favorability_change", with: "❤️")
        t = t.replacingOccurrences(of: "favorability", with: "❤️")
        t = t.replacingOccurrences(of: "好感度", with: "❤️")
        t = t.replacingOccurrences(of: "familiarity", with: "👋")
        t = t.replacingOccurrences(of: "熟悉度", with: "👋")
        t = t.replacingOccurrences(of: "mood", with: "😊")
        t = t.replacingOccurrences(of: "心情", with: "😊")
        return t
    }

    struct Seg { let t: String; let isStage: Bool }
    func parse(_ s: String) -> [Seg] {
        var segs: [Seg] = []; var cur = ""; var inP = false
        for ch in s {
            if ch == "（"||ch=="(" { if !cur.isEmpty{segs.append(Seg(t:cur,isStage:false));cur=""}; inP=true; cur.append(ch) }
            else if ch == "）"||ch==")" { cur.append(ch); segs.append(Seg(t:cur,isStage:true)); cur=""; inP=false }
            else { cur.append(ch) }
        }
        if !cur.isEmpty { segs.append(Seg(t:cur,isStage:inP)) }
        return segs.isEmpty ? [Seg(t:s,isStage:false)] : segs
    }

    var body: some View {
        let ct = clean(text)
        VStack(alignment:.leading, spacing:2) {
            ForEach(Array(parse(ct).enumerated()), id:\.offset) { _, seg in
                Text(seg.t).font(.system(size:11))
                    .foregroundColor(seg.isStage ? .gray : (isPlayer ? .black : Color(red:0.1,green:0.15,blue:0.3)))
                    .italic(seg.isStage).fixedSize(horizontal:false, vertical:true)
            }
        }
        .frame(maxWidth:190, alignment:isPlayer ? .trailing : .leading)
        .padding(.horizontal,10).padding(.vertical,7)
        .background(Color(red:0.92,green:0.92,blue:0.92))
        .overlay(RoundedRectangle(cornerRadius:10).stroke(Color.gray.opacity(0.4), lineWidth:1))
        .cornerRadius(10).offset(y:y).opacity(o)
        .onAppear { withAnimation(.spring(response:0.3,dampingFraction:0.7)) { y=0;o=1 } }
    }
}

// MARK: - 宠物视图
struct PetView: View {
    @StateObject var session = GameSession()
    @State private var avSize: CGFloat = 64

    func resize(to h: CGFloat) {
        guard let w = NSApplication.shared.windows.first(where:{$0 is PetWindow}) else { return }
        var f = w.frame; let nh = max(180, h+12)
        if abs(nh-f.height)<3 { return }
        f.size.height = nh; w.setFrame(f, display:true, animate:false)
    }

    var body: some View {
        VStack(spacing:2) {
            if session.showBubbles {
                if !session.npcBubble.isEmpty { BubbleBox(text:session.npcBubble,isPlayer:false) }
                if !session.playerBubble.isEmpty { BubbleBox(text:session.playerBubble,isPlayer:true) }
            }
            if !session.favChange.isEmpty {
                Text(session.favChange).font(.system(size:10)).foregroundColor(.pink)
            }
            if !session.selectedNpcName.isEmpty { nameLabel }
            avatarView
            if session.showInfo && !session.npcInfo.isEmpty { infoBubble }
            if session.showMenu { menuView }
            statusDot
            inputBar
        }
        .padding(6).frame(width:240)
        .background(GeometryReader{geo in Color.clear.onChange(of: geo.size.height) { _, h in resize(to: h) }})
        .contextMenu {
            Button("角色信息") { session.showInfo.toggle(); session.fetchNpcInfo() }
            Divider()
            Button("退出") { NSApplication.shared.terminate(nil) }
        }
        .onAppear { session.connect() }
    }

    var avatarView: some View {
        HStack(spacing:4) {
            Button(action:{ avSize=max(50,avSize-10) }){
                Text("−").font(.system(size:14,weight:.bold)).foregroundColor(.gray.opacity(0.6)).frame(width:18)
            }.buttonStyle(.plain).opacity(avSize>50 ? 1 : 0.3)
            ZStack {
                Circle().fill(Color.white.opacity(0.08)).frame(width:avSize,height:avSize).shadow(radius:4)
                if let a = session.npcAvatar {
                    Image(nsImage:a).resizable().aspectRatio(contentMode:.fill)
                        .frame(width:avSize-6,height:avSize-6).clipShape(Circle())
                } else {
                    Text(session.selectedNpcName.isEmpty ? "🐱" : String(session.selectedNpcName.prefix(1)))
                        .font(.system(size:avSize*0.38)).foregroundColor(.white)
                }
            }.onTapGesture { session.showMenu.toggle() }
            Button(action:{ avSize=min(160,avSize+10) }){
                Text("+").font(.system(size:14,weight:.bold)).foregroundColor(.gray.opacity(0.6)).frame(width:18)
            }.buttonStyle(.plain).opacity(avSize<160 ? 1 : 0.3)
        }
    }

    var nameLabel: some View {
        HStack(spacing:6) {
            Text(session.selectedNpcName).font(.system(size:11,weight:.bold)).foregroundColor(.white)
            if !session.npcMood.isEmpty {
                Text("·").foregroundColor(.gray)
                Text(session.npcMood).font(.system(size:10)).foregroundColor(.gray)
            }
        }.padding(.horizontal,10).padding(.vertical,4).background(Color.black.opacity(0.7)).cornerRadius(6)
    }

    var infoBubble: some View {
        VStack(alignment:.leading, spacing:2) {
            ForEach(session.npcInfo.components(separatedBy:"\n"), id:\.self) { line in
                Text(line).font(.system(size:10)).foregroundColor(.white)
            }
        }
        .padding(8).frame(maxWidth:200)
        .background(Color.black.opacity(0.75)).cornerRadius(8)
        .overlay(
            HStack{Spacer()
                Button(action:{session.showInfo=false}){
                    Text("✕").font(.system(size:10)).foregroundColor(.gray)
                }.buttonStyle(.plain).padding(4)
            }, alignment:.topTrailing
        )
    }

    var statusDot: some View {
        HStack(spacing:4) {
            Circle().fill(session.connected ? Color.green : Color.red).frame(width:4,height:4)
            Text(session.statusText).font(.system(size:8)).foregroundColor(.gray)
        }
    }

    var menuView: some View {
        ScrollView {
            VStack(spacing:0) {
                ForEach(session.npcs) { n in
                    Button(action:{ session.select(n); session.showMenu=false }) {
                        HStack {
                            Text(n.name).font(.system(size:11)).foregroundColor(.white)
                            Spacer()
                            if session.selectedNpcName == n.name {
                                Image(systemName:"checkmark").font(.system(size:10)).foregroundColor(.green)
                            }
                        }.padding(.horizontal,10).padding(.vertical,4)
                    }.buttonStyle(.plain)
                    Divider().background(Color.white.opacity(0.1))
                }
            }
        }.frame(height:100).background(Color.black.opacity(0.8)).cornerRadius(8)
    }

    var inputBar: some View {
        HStack(spacing:4) {
            TextField("输入...", text:$session.inputText).textFieldStyle(.plain).frame(width:120)
                .padding(.horizontal,8).padding(.vertical,4)
                .background(Color(red:0.1,green:0.1,blue:0.15)).cornerRadius(6)
                .foregroundColor(.white).font(.system(size:11)).onSubmit{send()}
            Button(action:{send()}){
                Image(systemName:"arrow.up.circle.fill").font(.system(size:20)).foregroundColor(.white.opacity(0.7))
            }.buttonStyle(.plain)
        }.padding(.horizontal,8).padding(.vertical,6)
         .background(Color(red:0.06,green:0.06,blue:0.1)).cornerRadius(8)
    }

    func send() {
        let t = session.inputText.trimmingCharacters(in:.whitespaces)
        guard !t.isEmpty else { return }
        session.send(t); session.inputText = ""
    }
}

// MARK: - App
class PetWindow: NSWindow { override var canBecomeKey: Bool { true } }

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: PetWindow!
    func applicationDidFinishLaunching(_ n: Notification) {
        let view = PetView()
        let host = NSHostingView(rootView:view)
        host.frame = NSRect(x:0,y:0,width:240,height:200)
        window = PetWindow(contentRect: NSRect(x:0,y:0,width:240,height:200),
                           styleMask:[.borderless], backing:.buffered, defer:false)
        window.isOpaque = false; window.backgroundColor = .clear
        window.level = .floating; window.collectionBehavior = [.canJoinAllSpaces,.stationary]
        window.isMovableByWindowBackground = true; window.contentView = host
        if let s = NSScreen.main {
            window.setFrameOrigin(NSPoint(x:s.visibleFrame.maxX-260, y:s.visibleFrame.minY+20))
        }
        window.makeKeyAndOrderFront(nil)
        NSEvent.addLocalMonitorForEvents(matching:.keyDown) { e in
            if e.modifierFlags.contains(.command),
               e.charactersIgnoringModifiers=="w"||e.charactersIgnoringModifiers=="q" {
                NSApplication.shared.terminate(nil); return nil
            }; return e
        }
    }
}

let app = NSApplication.shared
let d = AppDelegate(); app.delegate = d
app.setActivationPolicy(.accessory); app.run()
_ = d
