import Metal
import MetalKit
import AppKit

class Live2DTextureManager {
    private var textures: [Int: MTLTexture] = [:]
    private let device: MTLDevice
    private let modelDir: String

    init(device: MTLDevice, modelDir: String) {
        self.device = device
        self.modelDir = modelDir
    }

    func loadTexture(at relativePath: String, index: Int) -> MTLTexture? {
        if let cached = textures[index] { return cached }

        let fullPath = (modelDir as NSString).appendingPathComponent(relativePath)
        guard let image = NSImage(contentsOfFile: fullPath),
              let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
            return nil
        }

        let loader = MTKTextureLoader(device: device)
        do {
            let options: [MTKTextureLoader.Option: Any] = [
                .SRGB: false,
                .textureUsage: MTLTextureUsage.shaderRead.rawValue as NSNumber
            ]
            let texture = try loader.newTexture(cgImage: cgImage, options: options)
            textures[index] = texture
            return texture
        } catch {
            print("[Live2D] Texture load error: \(error)")
            return nil
        }
    }
}
