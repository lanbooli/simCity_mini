import MetalKit
import SwiftUI
import AppKit

struct Live2DMetalView: NSViewRepresentable {
    let model: Live2DModelController

    func makeCoordinator() -> Coordinator {
        Coordinator(model: model)
    }

    func makeNSView(context: Context) -> MTKView {
        guard let device = MTLCreateSystemDefaultDevice() else {
            fatalError("Metal not available")
        }

        let view = MTKView(frame: .zero, device: device)
        view.clearColor = MTLClearColor(red: 0, green: 0, blue: 0, alpha: 0)
        view.colorPixelFormat = .bgra8Unorm
        view.delegate = context.coordinator
        view.preferredFramesPerSecond = 60
        view.enableSetNeedsDisplay = false

        // Enable transparency on the layer
        view.wantsLayer = true
        view.layer?.isOpaque = false
        view.layer?.backgroundColor = NSColor.clear.cgColor

        context.coordinator.setupRenderer(device: device, view: view)
        print("[Live2D] MTKView created, frame: \(view.frame)")
        return view
    }

    func updateNSView(_ nsView: MTKView, context: Context) {}

    class Coordinator: NSObject, MTKViewDelegate {
        let model: Live2DModelController
        private var device: MTLDevice!
        private var pipeline: MTLRenderPipelineState!
        private var commandQueue: MTLCommandQueue!
        private var textureManager: Live2DTextureManager!
        private var texturePaths: [Int: String] = [:]
        private var frameCount: Int = 0

        init(model: Live2DModelController) {
            self.model = model
            super.init()
        }

        func setupRenderer(device: MTLDevice, view: MTKView) {
            self.device = device
            commandQueue = device.makeCommandQueue()

            let src = """
            #include <metal_stdlib>
            using namespace metal;

            struct VertexIn {
                float2 position [[attribute(0)]];
                float2 texCoord [[attribute(1)]];
            };
            struct VertexOut {
                float4 position [[position]];
                float2 texCoord;
            };
            struct Uniforms {
                float4x4 projectionMatrix;
            };

            vertex VertexOut live2d_vertex(VertexIn in [[stage_in]],
                                            constant Uniforms &uniforms [[buffer(1)]]) {
                VertexOut out;
                out.position = uniforms.projectionMatrix * float4(in.position, 0.0, 1.0);
                out.texCoord = in.texCoord;
                return out;
            }

            fragment float4 live2d_fragment(VertexOut in [[stage_in]],
                                            texture2d<float> texture [[texture(0)]],
                                            sampler sampler [[sampler(0)]]) {
                return texture.sample(sampler, in.texCoord);
            }
            """

            do {
                let library = try device.makeLibrary(source: src, options: nil)
                let desc = MTLRenderPipelineDescriptor()
                desc.vertexFunction = library.makeFunction(name: "live2d_vertex")
                desc.fragmentFunction = library.makeFunction(name: "live2d_fragment")
                desc.colorAttachments[0].pixelFormat = view.colorPixelFormat
                desc.colorAttachments[0].isBlendingEnabled = true
                desc.colorAttachments[0].rgbBlendOperation = .add
                desc.colorAttachments[0].alphaBlendOperation = .add
                desc.colorAttachments[0].sourceRGBBlendFactor = .one
                desc.colorAttachments[0].destinationRGBBlendFactor = .oneMinusSourceAlpha
                desc.colorAttachments[0].sourceAlphaBlendFactor = .one
                desc.colorAttachments[0].destinationAlphaBlendFactor = .oneMinusSourceAlpha

                let vd = MTLVertexDescriptor()
                vd.attributes[0].format = .float2
                vd.attributes[0].offset = 0
                vd.attributes[0].bufferIndex = 0
                vd.attributes[1].format = .float2
                vd.attributes[1].offset = 8
                vd.attributes[1].bufferIndex = 0
                vd.layouts[0].stride = 16
                vd.layouts[0].stepFunction = .perVertex
                desc.vertexDescriptor = vd

                pipeline = try device.makeRenderPipelineState(descriptor: desc)
                print("[Live2D] Pipeline created successfully")
            } catch {
                print("[Live2D] Pipeline error: \(error)")
                return
            }

            textureManager = Live2DTextureManager(device: device, modelDir: model.modelDir)

            // Parse texture paths
            if let jsonData = try? Data(contentsOf: URL(fileURLWithPath: "\(model.modelDir)/Haru.model3.json")),
               let json = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any],
               let fileRefs = json["FileReferences"] as? [String: String] {
                for (key, value) in fileRefs where key.hasPrefix("Texture") {
                    if let idx = Int(key.dropFirst(7)) { texturePaths[idx] = value }
                }
                print("[Live2D] Texture paths parsed: \(texturePaths)")
            } else {
                print("[Live2D] Failed to parse texture paths")
            }
        }

        func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) {
            print("[Live2D] Drawable size changed: \(size)")
        }

        func draw(in view: MTKView) {
            frameCount += 1

            guard let drawable = view.currentDrawable,
                  let desc = view.currentRenderPassDescriptor,
                  let queue = commandQueue,
                  let pipeline = pipeline else {
                if frameCount <= 3 { print("[Live2D] Draw skip: no drawable/desc/queue/pipeline") }
                return
            }

            let dc = model.drawableCount()
            if frameCount == 1 {
                print("[Live2D] First frame: drawableCount=\(dc), canvas=\(model.canvasWidth)x\(model.canvasHeight)")
            }
            if frameCount % 60 == 0 {
                print("[Live2D] Frame \(frameCount): \(dc) drawables, canvas \(model.canvasWidth)x\(model.canvasHeight)")
            }

            guard dc > 0 else { return }

            let vw = Float(view.drawableSize.width)
            let vh = Float(view.drawableSize.height)
            let cw = model.canvasWidth
            let ch = model.canvasHeight

            // Simple orthographic projection: scale model to fit view, centered
            let modelAspect = cw / max(ch, 1)
            let viewAspect = vw / max(vh, 1)
            // Scale to fit view
            let aspectScale: Float = modelAspect > viewAspect
                ? 2.0 / cw
                : 2.0 / ch

            // Column-major ortho projection that centers the model
            let left: Float = -1.0
            let right: Float = 1.0
            let bottom: Float = -1.0
            let top: Float = 1.0
            let near: Float = -1.0
            let far: Float = 1.0

            let projection: [Float] = [
                2/(right-left), 0,              0,  0,
                0,              2/(top-bottom), 0,  0,
                0,              0,              -2/(far-near), 0,
                -(right+left)/(right-left), -(top+bottom)/(top-bottom), -(far+near)/(far-near), 1
            ]

            let cmdBuf = queue.makeCommandBuffer()!
            let encoder = cmdBuf.makeRenderCommandEncoder(descriptor: desc)!
            encoder.setRenderPipelineState(pipeline)

            var drawCount = 0
            for i in 0..<dc {
                guard model.isVisible(for: i) else { continue }
                let op = model.opacity(for: i)
                guard op > 0.01 else { continue }

                let texIdx = model.textureIndex(for: i)
                guard let texPath = texturePaths[texIdx] else { continue }
                guard let tex = textureManager.loadTexture(at: texPath, index: texIdx) else {
                    if frameCount <= 3 { print("[Live2D] Texture \(texIdx) failed to load: \(texPath)") }
                    continue
                }

                guard let (vData, vCount) = model.vertices(for: i), vCount > 0 else { continue }
                let iCount = model.indexCount(for: i)
                guard iCount > 0 else { continue }
                guard let iData = model.indices(for: i) else { continue }

                let vBytes = vCount * 4 * MemoryLayout<Float>.stride
                let iBytes = iCount * MemoryLayout<UInt16>.stride

                guard let vb = device.makeBuffer(bytes: vData, length: vBytes, options: []),
                      let ib = device.makeBuffer(bytes: iData, length: iBytes, options: []) else { continue }

                encoder.setFragmentTexture(tex, index: 0)
                encoder.setVertexBuffer(vb, offset: 0, index: 0)
                var proj = projection
                encoder.setVertexBytes(&proj, length: 16 * MemoryLayout<Float>.stride, index: 1)
                encoder.drawIndexedPrimitives(type: .triangle, indexCount: iCount, indexType: .uint16, indexBuffer: ib, indexBufferOffset: 0)
                drawCount += 1
            }

            encoder.endEncoding()
            cmdBuf.present(drawable)
            cmdBuf.commit()

            if frameCount <= 5 {
                print("[Live2D] Frame \(frameCount): drew \(drawCount) drawables")
            }
        }
    }
}
