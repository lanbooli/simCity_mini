#import "L2DPetModel.h"

#include <CubismFramework.hpp>
#include <CubismFrameworkConfig.hpp>
#include <Model/CubismUserModel.hpp>
#include <Model/CubismMoc.hpp>
#include <Model/CubismModel.hpp>
#include <CubismModelSettingJson.hpp>
#include <CubismDefaultParameterId.hpp>
#include <ICubismModelSetting.hpp>
#include <ICubismAllocator.hpp>
#include <Math/CubismModelMatrix.hpp>
#include <Math/CubismMatrix44.hpp>
#include <Rendering/Metal/CubismRenderer_Metal.hpp>
#include <Rendering/Metal/CubismRenderTarget_Metal.hpp>
#include <Id/CubismIdManager.hpp>
#include <Utils/CubismString.hpp>

#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <MetalKit/MetalKit.h>
#include <string>

using namespace Live2D::Cubism::Framework;
using namespace Live2D::Cubism::Framework::Rendering;
using namespace Live2D::Cubism::Framework::DefaultParameterId;

// ─── Allocator ────────────────────────────────────────────────────────────
class SimpleAllocator : public ICubismAllocator {
public:
    void* Allocate(const csmSizeType size) override { return malloc(size); }
    void Deallocate(void* memory) override { free(memory); }
    void* AllocateAligned(const csmSizeType size, const csmUint32 alignment) override {
        void* p = nullptr;
        posix_memalign(&p, alignment, size);
        return p;
    }
    void DeallocateAligned(void* alignedMemory) override { free(alignedMemory); }
};
static SimpleAllocator g_allocator;

// ─── Static initialisation ────────────────────────────────────────────────
static bool g_cubismInitialized = false;
static const CubismId* g_idBreath = nullptr;
static const CubismId* g_idEyeLOpen = nullptr;
static const CubismId* g_idEyeROpen = nullptr;
static const CubismId* g_idAngleX = nullptr;
static const CubismId* g_idAngleY = nullptr;
static const CubismId* g_idAngleZ = nullptr;
static const CubismId* g_idBodyAngleX = nullptr;
static const CubismId* g_idMouthForm = nullptr;

static void ensureCubismInit(id<MTLDevice> device) {
    if (g_cubismInitialized) return;
    
    CubismFramework::CleanUp();
    
    CubismFramework::Option opt;
    opt.LogFunction = [](const csmChar* msg) {
        NSLog(@"[Cubism] %s", msg);
    };
    CubismFramework::StartUp(&g_allocator, &opt);
    CubismFramework::Initialize();
    
    CubismIdManager* idMgr = CubismFramework::GetIdManager();
    g_idBreath = idMgr->GetId(ParamBreath);
    g_idEyeLOpen = idMgr->GetId(ParamEyeLOpen);
    g_idEyeROpen = idMgr->GetId(ParamEyeROpen);
    g_idAngleX = idMgr->GetId(ParamAngleX);
    g_idAngleY = idMgr->GetId(ParamAngleY);
    g_idAngleZ = idMgr->GetId(ParamAngleZ);
    g_idBodyAngleX = idMgr->GetId(ParamBodyAngleX);
    g_idMouthForm = idMgr->GetId(ParamMouthForm);
    
    CubismRenderer_Metal::SetConstantSettings(device);
    g_cubismInitialized = true;
    NSLog(@"[L2DPetModel] CubismFramework initialized");
}

// ─── File helpers ─────────────────────────────────────────────────────────
static unsigned char* readFile(const char* path, unsigned int* outSize) {
    FILE* f = fopen(path, "rb");
    if (!f) return nullptr;
    fseek(f, 0, SEEK_END);
    unsigned int size = (unsigned int)ftell(f);
    fseek(f, 0, SEEK_SET);
    unsigned char* buf = (unsigned char*)malloc(size);
    if (buf) fread(buf, 1, size, f);
    fclose(f);
    *outSize = size;
    return buf;
}

// ─── Simple Metal sprite for blitting model output to drawable ────────────
static id<MTLRenderPipelineState> g_spritePipeline = nil;
static id<MTLBuffer> g_spriteVertexBuffer = nil;

static const float kQuadVertices[] = {
    -1.0f, -1.0f,  0.0f, 1.0f,
     1.0f, -1.0f,  1.0f, 1.0f,
    -1.0f,  1.0f,  0.0f, 0.0f,
     1.0f,  1.0f,  1.0f, 0.0f,
};

static void ensureSpritePipeline(id<MTLDevice> device) {
    if (g_spritePipeline) return;
    
    NSError* err = nil;
    NSString* shaderSrc = @"\
#include <metal_stdlib>\n\
using namespace metal;\n\
struct VOut { float4 pos [[position]]; float2 uv; };\n\
vertex VOut vs_main(uint vid [[vertex_id]]) {\n\
    const float2 positions[4] = { {-1,-1}, {1,-1}, {-1,1}, {1,1} };\n\
    const float2 uvs[4] = { {0,1}, {1,1}, {0,0}, {1,0} };\n\
    VOut o; o.pos = float4(positions[vid], 0.0, 1.0); o.uv = uvs[vid]; return o;\n\
}\n\
fragment float4 fs_main(VOut in [[stage_in]], texture2d<float> tex [[texture(0)]]) {\n\
    constexpr sampler s(filter::linear);\n\
    return tex.sample(s, in.uv);\n\
}";
    
    id<MTLLibrary> lib = [device newLibraryWithSource:shaderSrc options:nil error:&err];
    if (!lib) { NSLog(@"[L2DPetModel] Shader error: %@", err); return; }
    
    MTLRenderPipelineDescriptor* desc = [[MTLRenderPipelineDescriptor alloc] init];
    desc.vertexFunction = [lib newFunctionWithName:@"vs_main"];
    desc.fragmentFunction = [lib newFunctionWithName:@"fs_main"];
    desc.colorAttachments[0].pixelFormat = MTLPixelFormatBGRA8Unorm;
    desc.colorAttachments[0].blendingEnabled = YES;
    desc.colorAttachments[0].rgbBlendOperation = MTLBlendOperationAdd;
    desc.colorAttachments[0].alphaBlendOperation = MTLBlendOperationAdd;
    desc.colorAttachments[0].sourceRGBBlendFactor = MTLBlendFactorOne;
    desc.colorAttachments[0].sourceAlphaBlendFactor = MTLBlendFactorOne;
    desc.colorAttachments[0].destinationRGBBlendFactor = MTLBlendFactorOneMinusSourceAlpha;
    desc.colorAttachments[0].destinationAlphaBlendFactor = MTLBlendFactorOneMinusSourceAlpha;
    
    g_spritePipeline = [device newRenderPipelineStateWithDescriptor:desc error:&err];
    if (!g_spritePipeline) { NSLog(@"[L2DPetModel] Pipeline error: %@", err); return; }
    
    g_spriteVertexBuffer = [device newBufferWithBytes:kQuadVertices
                                               length:sizeof(kQuadVertices)
                                              options:MTLResourceStorageModeShared];
    NSLog(@"[L2DPetModel] Sprite pipeline created");
}


// ─── L2DPetModel implementation ───────────────────────────────────────────

@implementation L2DPetModel {
    CubismUserModel* _userModel;
    ICubismModelSetting* _modelSetting;
    std::string _modelHomeDir;
    
    id<MTLDevice> _device;
    CGSize _viewSize;
    
    float _breathPhase;
    float _blinkTimer;
    float _blinkState;
    float _swayPhase;
}

- (instancetype)initWithModelDir:(NSString *)dir
                          device:(id<MTLDevice>)device
                            size:(CGSize)viewSize {
    self = [super init];
    if (!self) return nil;
    
    _device = device;
    _viewSize = viewSize;
    
    ensureCubismInit(device);
    ensureSpritePipeline(device);
    
    NSString* modelName = [dir lastPathComponent];
    NSString* jsonPath = [dir stringByAppendingPathComponent:
                          [NSString stringWithFormat:@"%@.model3.json", modelName]];
    
    if (![[NSFileManager defaultManager] fileExistsAtPath:jsonPath]) {
        NSLog(@"[L2DPetModel] model3.json not found: %@", jsonPath);
        return nil;
    }
    
    unsigned int jsonSize = 0;
    unsigned char* jsonBuffer = readFile([jsonPath UTF8String], &jsonSize);
    if (!jsonBuffer) { NSLog(@"[L2DPetModel] Failed to read model3.json"); return nil; }
    
    _modelSetting = new CubismModelSettingJson(jsonBuffer, jsonSize);
    free(jsonBuffer);
    
    _modelHomeDir = [[dir stringByAppendingString:@"/"] UTF8String];
    
    const char* mocName = _modelSetting->GetModelFileName();
    if (!mocName || strlen(mocName) == 0) {
        NSLog(@"[L2DPetModel] No moc file in setting");
        return nil;
    }
    
    std::string mocPath = _modelHomeDir + mocName;
    unsigned int mocSize = 0;
    unsigned char* mocBuffer = readFile(mocPath.c_str(), &mocSize);
    if (!mocBuffer) {
        NSLog(@"[L2DPetModel] Failed to read moc: %s", mocPath.c_str());
        return nil;
    }
    
    _userModel = new CubismUserModel();
    _userModel->LoadModel(mocBuffer, mocSize);
    free(mocBuffer);
    
    if (!_userModel->GetModel()) {
        NSLog(@"[L2DPetModel] Failed to create CubismModel");
        return nil;
    }
    
    CubismModel* model = _userModel->GetModel();
    NSLog(@"[L2DPetModel] Model loaded: drawables=%d params=%d",
          model->GetDrawableCount(), model->GetParameterCount());
    
    csmUint32 rw = (csmUint32)viewSize.width;
    csmUint32 rh = (csmUint32)viewSize.height;
    
    _userModel->CreateRenderer(rw, rh);
    
    CubismRenderer_Metal* renderer = _userModel->GetRenderer<CubismRenderer_Metal>();
    if (!renderer) {
        NSLog(@"[L2DPetModel] Failed to create CubismRenderer_Metal");
        return nil;
    }
    
    // Note: model matrix stays identity (like official sample)
    // SetWidth would divide by zero since _width=0 from default constructor
    
    [self bindTextures];
    
    _breathPhase = 0;
    _blinkTimer = 0;
    _blinkState = 0;
    _swayPhase = 0;
    
    _userModel->IsInitialized(true);
    _userModel->IsUpdating(true);
    
    NSLog(@"[L2DPetModel] Init complete, renderSize=%dx%d", rw, rh);
    return self;
}

- (void)bindTextures {
    CubismRenderer_Metal* renderer = _userModel->GetRenderer<CubismRenderer_Metal>();
    if (!renderer) return;
    
    int texCount = _modelSetting->GetTextureCount();
    MTKTextureLoader* loader = [[MTKTextureLoader alloc] initWithDevice:_device];
    
    for (int i = 0; i < texCount; i++) {
        const char* texName = _modelSetting->GetTextureFileName(i);
        if (!texName || strlen(texName) == 0) continue;
        
        std::string texPath = _modelHomeDir + texName;
        NSString* path = [NSString stringWithUTF8String:texPath.c_str()];
        
        NSError* err = nil;
        id<MTLTexture> texture = [loader newTextureWithContentsOfURL:[NSURL fileURLWithPath:path]
                                                              options:@{MTKTextureLoaderOptionSRGB: @NO}
                                                                error:&err];
        if (texture) {
            renderer->BindTexture(i, texture);
        } else {
            NSLog(@"[L2DPetModel] Texture %d failed: %s", i, texName);
        }
    }
    
    renderer->IsPremultipliedAlpha(false);
    NSLog(@"[L2DPetModel] %d textures bound", texCount);
}

- (void)dealloc {
    if (_userModel) {
        _userModel->DeleteRenderer();
        delete _userModel;
    }
    if (_modelSetting) delete _modelSetting;
}

- (void)updateWithDeltaTime:(float)dt {
    if (!_userModel || !_userModel->GetModel()) return;
    CubismModel* model = _userModel->GetModel();
    
    _breathPhase += dt * 0.8f;
    if (_breathPhase > M_PI * 2) _breathPhase -= M_PI * 2;
    model->SetParameterValue(g_idBreath, sinf(_breathPhase) * 0.5f + 0.5f);
    
    _blinkTimer -= dt;
    if (_blinkTimer <= 0) {
        _blinkState = (_blinkState > 0.5f) ? 0.0f : 1.0f;
        _blinkTimer = (_blinkState > 0.5f) ? 0.08f : ((float)(arc4random() % 400) / 100.0f + 2.0f);
    }
    float eye = 1.0f - _blinkState;
    model->SetParameterValue(g_idEyeLOpen, eye);
    model->SetParameterValue(g_idEyeROpen, eye);
    
    _swayPhase += dt * 0.3f;
    float sw = sinf(_swayPhase) * 0.03f;
    model->SetParameterValue(g_idAngleX, sw);
    model->SetParameterValue(g_idAngleY, cosf(_swayPhase * 1.3f) * 0.02f);
    model->SetParameterValue(g_idAngleZ, sinf(_swayPhase * 0.7f) * 0.015f);
    model->SetParameterValue(g_idBodyAngleX, sw * 0.5f);
    
    model->Update();
}

- (void)setParameter:(NSString *)name value:(float)value {
    if (!_userModel || !_userModel->GetModel()) return;
    const CubismId* pid = CubismFramework::GetIdManager()->GetId([name UTF8String]);
    _userModel->GetModel()->SetParameterValue(pid, value);
}

- (int)drawableCount {
    if (!_userModel || !_userModel->GetModel()) return 0;
    return _userModel->GetModel()->GetDrawableCount();
}

- (void)drawToDrawable:(id<CAMetalDrawable>)drawable
         commandBuffer:(id<MTLCommandBuffer>)commandBuffer {
    static int frameCount = 0;
    if (!_userModel) return;
    
    CubismRenderer_Metal* renderer = _userModel->GetRenderer<CubismRenderer_Metal>();
    if (!renderer) return;
    
    CubismModel* model = _userModel->GetModel();
    float canvasW = model->GetCanvasWidth();
    float canvasH = model->GetCanvasHeight();
    float displayW = (float)_viewSize.width;
    float displayH = (float)_viewSize.height;
    float canvasRatio = canvasH / canvasW;      // e.g. 4500/2400 = 1.875
    float displayRatio = displayH / displayW;    // e.g. 480/320 = 1.5
    
    CubismModelMatrix* mm = _userModel->GetModelMatrix();
    CubismMatrix44 projection;
    
    // Match official sample: choose SetWidth or SetHeight based on aspect ratio
    if (canvasRatio < displayRatio) {
        // Wide model: fit by width
        mm->SetWidth(2.0f);
        projection.Scale(1.0f, displayW / displayH);
    } else {
        // Tall model (Haru): fit by height
        mm->SetHeight(2.0f);
        projection.Scale(displayH / displayW, 1.0f);
    }
    
    CubismMatrix44 mvp = projection;
    mvp.MultiplyByMatrix(mm);
    renderer->SetMvpMatrix(&mvp);
    
    // StartFrame with the drawable's texture as render target
    MTLRenderPassDescriptor* rpDesc = [MTLRenderPassDescriptor renderPassDescriptor];
    rpDesc.colorAttachments[0].texture = drawable.texture;
    rpDesc.colorAttachments[0].loadAction = MTLLoadActionClear;
    rpDesc.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 0);
    rpDesc.colorAttachments[0].storeAction = MTLStoreActionStore;
    renderer->StartFrame(commandBuffer, rpDesc);
    
    // Set render viewport (matches official sample)
    MTLViewport vp = {0, 0, (double)_viewSize.width, (double)_viewSize.height, 0.0, 1.0};
    renderer->SetRenderViewport(vp);

    // DrawModel handles everything:
    //   - IsBlendMode: renders to model RT, then AfterDraw copies to drawable
    //   - Direct mode: renders directly to drawable via _renderPassDescriptor
    renderer->DrawModel();
    
    if (++frameCount <= 3) {
        NSLog(@"[L2DPetModel] Frame %d rendered", frameCount);
    }
    
    // DrawModel already handles rendering (modelRT → drawable or direct).
    // No manual blit needed.
}

@end
