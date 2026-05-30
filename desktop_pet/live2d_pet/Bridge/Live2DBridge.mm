#import "Live2DBridge.h"
#import "Live2DCubismCore.h"
#import <Foundation/Foundation.h>
#include <vector>
#include <string>

struct Live2DModelData {
    csmMoc *moc;
    csmModel *model;
    unsigned char *mocBuffer;
    unsigned int mocSize;
    void *modelMemory;
    std::vector<std::string> paramIDs;
    std::vector<std::string> partIDs;
};

static unsigned char *ReadFile(const char *path, unsigned int *outSize) {
    FILE *f = fopen(path, "rb");
    if (!f) return nullptr;
    fseek(f, 0, SEEK_END);
    unsigned int size = (unsigned int)ftell(f);
    fseek(f, 0, SEEK_SET);
    unsigned char *buf = (unsigned char *)malloc(size);
    fread(buf, 1, size, f);
    fclose(f);
    *outSize = size;
    return buf;
}

Live2DModelHandle Live2DLoadModel(const char *modelJsonPath) {
    NSString *jsonPath = [NSString stringWithUTF8String:modelJsonPath];
    NSData *jsonData = [NSData dataWithContentsOfFile:jsonPath];
    if (!jsonData) return nullptr;

    NSError *err = nil;
    NSDictionary *dict = [NSJSONSerialization JSONObjectWithData:jsonData options:0 error:&err];
    if (!dict) return nullptr;

    NSString *mocName = dict[@"FileReferences"][@"Moc"];
    if (!mocName) return nullptr;

    NSString *dir = [jsonPath stringByDeletingLastPathComponent];
    NSString *mocPath = [dir stringByAppendingPathComponent:mocName];

    unsigned int mocSize = 0;
    unsigned char *mocBuffer = ReadFile([mocPath UTF8String], &mocSize);
    if (!mocBuffer) return nullptr;

    csmMoc *moc = csmReviveMocInPlace(mocBuffer, mocSize);
    if (!moc) { free(mocBuffer); return nullptr; }

    unsigned int modelSize = csmGetSizeofModel(moc);
    void *modelMem = malloc(modelSize);
    csmModel *model = csmInitializeModelInPlace(moc, modelMem, modelSize);
    if (!model) { free(mocBuffer); free(modelMem); return nullptr; }

    auto *data = new Live2DModelData();
    data->moc = moc;
    data->model = model;
    data->mocBuffer = mocBuffer;
    data->mocSize = mocSize;
    data->modelMemory = modelMem;

    int paramCount = csmGetParameterCount(model);
    const char **rawIDs = csmGetParameterIds(model);
    for (int i = 0; i < paramCount; i++) {
        data->paramIDs.push_back(rawIDs[i] ? rawIDs[i] : "");
    }

    int partCount = csmGetPartCount(model);
    const char **rawPartIDs = csmGetPartIds(model);
    for (int i = 0; i < partCount; i++) {
        data->partIDs.push_back(rawPartIDs[i] ? rawPartIDs[i] : "");
    }

    NSLog(@"[Bridge] Model loaded: moc=%p model=%p params=%d parts=%d drawables=%d",
          data->moc, data->model,
          csmGetParameterCount(model),
          csmGetPartCount(model),
          csmGetDrawableCount(model));
    return (Live2DModelHandle)data;
}

void Live2DReleaseModel(Live2DModelHandle handle) {
    if (!handle) return;
    auto *data = (Live2DModelData *)handle;
    if (data->modelMemory) free(data->modelMemory);
    if (data->mocBuffer) free(data->mocBuffer);
    delete data;
}

void Live2DUpdate(Live2DModelHandle handle) {
    if (!handle) return;
    csmUpdateModel(((Live2DModelData *)handle)->model);
}

void Live2DGetCanvasInfo(Live2DModelHandle handle, float *outWidth, float *outHeight, float *outOriginX, float *outOriginY, float *outPPU) {
    if (!handle) { *outWidth=1; *outHeight=1; *outOriginX=0; *outOriginY=0; *outPPU=1; return; }
    csmVector2 size, origin;
    float ppu;
    csmReadCanvasInfo(((Live2DModelData *)handle)->model, &size, &origin, &ppu);
    *outWidth = size.X; *outHeight = size.Y;
    *outOriginX = origin.X; *outOriginY = origin.Y;
    *outPPU = ppu;
}

void Live2DGetCanvasSize(Live2DModelHandle handle, float *outWidth, float *outHeight) {
    if (!handle) { *outWidth = 1; *outHeight = 1; return; }
    csmVector2 size, origin;
    float ppu;
    csmReadCanvasInfo(((Live2DModelData *)handle)->model, &size, &origin, &ppu);
    *outWidth = size.X;
    *outHeight = size.Y;
}

// ── Parameters ──

int Live2DGetParameterCount(Live2DModelHandle handle) {
    if (!handle) return 0;
    return csmGetParameterCount(((Live2DModelData *)handle)->model);
}

const char * const *Live2DGetParameterIDs(Live2DModelHandle handle) {
    if (!handle) return nullptr;
    return csmGetParameterIds(((Live2DModelData *)handle)->model);
}

float Live2DGetParameterValue(Live2DModelHandle handle, int index) {
    if (!handle) return 0;
    const float *vals = csmGetParameterValues(((Live2DModelData *)handle)->model);
    return vals ? vals[index] : 0;
}

void Live2DSetParameterValue(Live2DModelHandle handle, int index, float value) {
    if (!handle) return;
    float *vals = csmGetParameterValues(((Live2DModelData *)handle)->model);
    if (vals) vals[index] = value;
}

int Live2DFindParameterIndex(Live2DModelHandle handle, const char *paramId) {
    if (!handle) return -1;
    auto *data = (Live2DModelData *)handle;
    for (size_t i = 0; i < data->paramIDs.size(); i++) {
        if (data->paramIDs[i] == paramId) return (int)i;
    }
    return -1;
}

// ── Parts ──

int Live2DGetPartCount(Live2DModelHandle handle) {
    if (!handle) return 0;
    return csmGetPartCount(((Live2DModelData *)handle)->model);
}

const char * const *Live2DGetPartIDs(Live2DModelHandle handle) {
    if (!handle) return nullptr;
    return csmGetPartIds(((Live2DModelData *)handle)->model);
}

void Live2DSetPartOpacity(Live2DModelHandle handle, int index, float opacity) {
    if (!handle) return;
    float *ops = csmGetPartOpacities(((Live2DModelData *)handle)->model);
    if (ops) ops[index] = opacity;
}

// ── Drawables (Cubism 5 API) ──

int Live2DGetDrawableCount(Live2DModelHandle handle) {
    if (!handle) return 0;
    return csmGetDrawableCount(((Live2DModelData *)handle)->model);
}

int Live2DGetDrawableVertexCount(Live2DModelHandle handle, int drawableIndex) {
    if (!handle) return 0;
    const int *counts = csmGetDrawableVertexCounts(((Live2DModelData *)handle)->model);
    return counts ? counts[drawableIndex] : 0;
}

float *Live2DGetDrawableVertices(Live2DModelHandle handle, int drawableIndex, int *outVertCount) {
    if (!handle || !outVertCount) return nullptr;
    auto *model = ((Live2DModelData *)handle)->model;
    const int *counts = csmGetDrawableVertexCounts(model);
    if (!counts) return nullptr;
    const csmVector2 **positions = csmGetDrawableVertexPositions(model);
    const csmVector2 **uvs = csmGetDrawableVertexUvs(model);
    if (!positions || !uvs) return nullptr;

    int vc = counts[drawableIndex];
    if (vc <= 0) return nullptr;

    // Interleave: [x,y,u,v, x,y,u,v, ...] — 4 floats per vertex
    float *out = (float *)malloc(vc * 4 * sizeof(float));
    if (!out) return nullptr;
    for (int i = 0; i < vc; i++) {
        out[i * 4 + 0] = positions[drawableIndex][i].X;
        out[i * 4 + 1] = positions[drawableIndex][i].Y;
        out[i * 4 + 2] = uvs[drawableIndex][i].X;
        out[i * 4 + 3] = uvs[drawableIndex][i].Y;
    }
    *outVertCount = vc;
    return out;
}

void Live2DFreeVertices(float *data) {
    if (data) free(data);
}

int Live2DGetDrawableIndexCount(Live2DModelHandle handle, int drawableIndex) {
    if (!handle) return 0;
    const int *counts = csmGetDrawableIndexCounts(((Live2DModelData *)handle)->model);
    return counts ? counts[drawableIndex] : 0;
}

const unsigned short *Live2DGetDrawableIndices(Live2DModelHandle handle, int drawableIndex) {
    if (!handle) return nullptr;
    const unsigned short **indices = csmGetDrawableIndices(((Live2DModelData *)handle)->model);
    return indices ? indices[drawableIndex] : nullptr;
}

int Live2DGetDrawableTextureIndex(Live2DModelHandle handle, int drawableIndex) {
    if (!handle) return 0;
    const int *texIndices = csmGetDrawableTextureIndices(((Live2DModelData *)handle)->model);
    return texIndices ? texIndices[drawableIndex] : 0;
}

float Live2DGetDrawableOpacity(Live2DModelHandle handle, int drawableIndex) {
    if (!handle) return 1.0f;
    const float *opacities = csmGetDrawableOpacities(((Live2DModelData *)handle)->model);
    return opacities ? opacities[drawableIndex] : 1.0f;
}

int Live2DGetDrawableIsVisible(Live2DModelHandle handle, int drawableIndex) {
    if (!handle) return 0;
    const csmFlags *flags = csmGetDrawableDynamicFlags(((Live2DModelData *)handle)->model);
    return flags ? ((flags[drawableIndex] & csmIsVisible) != 0) : 0;
}

const int *Live2DGetRenderOrders(Live2DModelHandle handle) {
    if (!handle) return nullptr;
    return csmGetRenderOrders(((Live2DModelData *)handle)->model);
}

int Live2DGetDrawableMaskCount(Live2DModelHandle handle, int drawableIndex) {
    if (!handle) return 0;
    const int *counts = csmGetDrawableMaskCounts(((Live2DModelData *)handle)->model);
    return counts ? counts[drawableIndex] : 0;
}

const int *Live2DGetDrawableMasks(Live2DModelHandle handle, int drawableIndex) {
    if (!handle) return nullptr;
    const int **masks = csmGetDrawableMasks(((Live2DModelData *)handle)->model);
    return masks ? masks[drawableIndex] : nullptr;
}

int Live2DGetOffscreenCount(Live2DModelHandle handle) {
    if (!handle) return 0;
    return csmGetOffscreenCount(((Live2DModelData *)handle)->model);
}

const int *Live2DGetOffscreenOwnerIndices(Live2DModelHandle handle) {
    if (!handle) return nullptr;
    return csmGetOffscreenOwnerIndices(((Live2DModelData *)handle)->model);
}

// Vertex layout constants
int Live2DGetVertexPositionStride(void) { return 2; }
int Live2DGetVertexUVStride(void) { return 2; }
int Live2DGetVertexTotalStride(void) { return 4; }
