import Foundation

class Live2DModelController: ObservableObject {
    let modelDir: String
    private var wrapper: Live2DWrapper?

    private var breathPhase: Float = 0
    private var blinkTimer: Float = 0
    private var blinkState: Float = 0
    private var swayPhase: Float = 0
    private var tiltPhase: Float = Float.random(in: 0...(Float.pi*2))
    private var elapsed: Float = 0

    var canvasWidth: Float = 1
    var canvasHeight: Float = 1


    init(modelDir: String) {
        self.modelDir = modelDir
    }

    func load() -> Bool {
        guard let w = Live2DWrapper(modelDir: modelDir) else { return false }
        wrapper = w
        w.getCanvasWidth(&canvasWidth, height: &canvasHeight)
        return true
    }

    func tick(deltaTime: Float) {
        guard let w = wrapper else { return }
        elapsed += deltaTime
        w.update()

        // Breathing: gentle chest rise/fall
        breathPhase += deltaTime * 0.8
        if breathPhase > Float.pi * 2 { breathPhase -= Float.pi * 2 }
        w.setParameter("ParamBreath", value: sin(breathPhase) * 0.5 + 0.5)

        // Blinking: brief close every 2-6 seconds
        blinkTimer -= deltaTime
        if blinkTimer <= 0 {
            blinkState = blinkState > 0.5 ? 0 : 1
            blinkTimer = blinkState > 0.5 ? 0.08 : Float.random(in: 2...6)
        }
        w.setParameter("ParamEyeLOpen", value: 1 - blinkState)
        w.setParameter("ParamEyeROpen", value: 1 - blinkState)

        // Slow head/body sway (like natural idle)
        swayPhase += deltaTime * 0.3
        let sway = sin(swayPhase) * 0.03
        w.setParameter("ParamAngleX", value: sway)
        w.setParameter("ParamAngleY", value: cos(swayPhase * 1.3) * 0.02)
        w.setParameter("ParamAngleZ", value: sin(swayPhase * 0.7) * 0.015)
        w.setParameter("ParamBodyAngleX", value: sway * 0.5)

        // Occasional head tilt (every ~8 seconds)
        tiltPhase += deltaTime
        if tiltPhase > 8 {
            tiltPhase = 0
            w.setParameter("ParamAngleZ", value: Float.random(in: -0.08...0.08))
        }
    }

    func drawableCount() -> Int { Int(wrapper?.drawableCount() ?? 0) }
    func vertexCount(for i: Int) -> Int { Int(wrapper?.vertexCount(forDrawable: Int32(i)) ?? 0) }
    func vertices(for i: Int) -> (UnsafeMutablePointer<Float>, Int)? {
        var count: Int32 = 0
        if let ptr = wrapper?.vertices(forDrawable: Int32(i), outVertCount: &count) {
            return (ptr, Int(count))
        }
        return nil
    }
    func indexCount(for i: Int) -> Int { Int(wrapper?.indexCount(forDrawable: Int32(i)) ?? 0) }
    func indices(for i: Int) -> UnsafePointer<UInt16>? { wrapper?.indices(forDrawable: Int32(i)) }
    func textureIndex(for i: Int) -> Int { Int(wrapper?.textureIndex(forDrawable: Int32(i)) ?? 0) }
    func opacity(for i: Int) -> Float { wrapper?.opacity(forDrawable: Int32(i)) ?? 0 }
    func isVisible(for i: Int) -> Bool { wrapper?.isVisible(forDrawable: Int32(i)) != 0 }
    func renderOrders() -> UnsafePointer<Int32>? { wrapper?.renderOrders() }
    func drawableMaskCount(for i: Int) -> Int { Int(wrapper?.maskCount(forDrawable: Int32(i)) ?? 0) }
    func drawableMaskIndices(for i: Int, count: Int32) -> UnsafePointer<Int32>? {
        var c: Int32 = 0
        return wrapper?.maskIndices(forDrawable: Int32(i), count: &c)
    }
    func offscreenCount() -> Int { Int(wrapper?.offscreenCount() ?? 0) }

    func setMood(_ mood: String) {
        guard let w = wrapper else { return }
        switch mood {
        case "开心", "happy": w.setParameter("ParamMouthForm", value: 0.6)
        case "难过", "sad":    w.setParameter("ParamMouthForm", value: -0.5)
        default: break
        }
    }

    func setParameter(_ id: String, value: Float) {
        wrapper?.setParameter(id, value: value)
    }

    func parameterCount() -> Int { Int(wrapper?.parameterCount() ?? 0) }
    func parameterId(at index: Int) -> String? { wrapper?.parameterId(at: Int32(index)) }
    func parameterValue(at index: Int) -> Float { wrapper?.parameterValue(at: Int32(index)) ?? 0 }
}
