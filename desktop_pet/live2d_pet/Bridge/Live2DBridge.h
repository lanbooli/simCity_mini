#ifndef Live2DBridge_h
#define Live2DBridge_h

#import <Foundation/Foundation.h>

typedef const void *Live2DModelHandle;

#ifdef __cplusplus
extern "C" {
#endif

Live2DModelHandle Live2DLoadModel(const char *modelJsonPath);
void Live2DReleaseModel(Live2DModelHandle handle);
void Live2DUpdate(Live2DModelHandle handle);

void Live2DGetCanvasSize(Live2DModelHandle handle, float *outWidth, float *outHeight);
void Live2DGetCanvasInfo(Live2DModelHandle handle, float *outWidth, float *outHeight, float *outOriginX, float *outOriginY, float *outPPU);

int Live2DGetParameterCount(Live2DModelHandle handle);
const char * const *Live2DGetParameterIDs(Live2DModelHandle handle);
float Live2DGetParameterValue(Live2DModelHandle handle, int index);
void Live2DSetParameterValue(Live2DModelHandle handle, int index, float value);
int Live2DFindParameterIndex(Live2DModelHandle handle, const char *paramId);

int Live2DGetPartCount(Live2DModelHandle handle);
const char * const *Live2DGetPartIDs(Live2DModelHandle handle);
void Live2DSetPartOpacity(Live2DModelHandle handle, int index, float opacity);

// Drawables — Cubism 5 API returns separate pos/uv arrays
int Live2DGetDrawableCount(Live2DModelHandle handle);
int Live2DGetDrawableVertexCount(Live2DModelHandle handle, int drawableIndex);
// Interleaved vertex data: [x,y,u,v, x,y,u,v, ...] — allocated, caller frees
float *Live2DGetDrawableVertices(Live2DModelHandle handle, int drawableIndex, int *outVertCount);
int Live2DGetDrawableIndexCount(Live2DModelHandle handle, int drawableIndex);
const unsigned short *Live2DGetDrawableIndices(Live2DModelHandle handle, int drawableIndex);
int Live2DGetDrawableTextureIndex(Live2DModelHandle handle, int drawableIndex);
float Live2DGetDrawableOpacity(Live2DModelHandle handle, int drawableIndex);
int Live2DGetDrawableIsVisible(Live2DModelHandle handle, int drawableIndex);
const int *Live2DGetRenderOrders(Live2DModelHandle handle);
int Live2DGetDrawableMaskCount(Live2DModelHandle handle, int drawableIndex);
const int *Live2DGetDrawableMasks(Live2DModelHandle handle, int drawableIndex);
int Live2DGetOffscreenCount(Live2DModelHandle handle);
const int *Live2DGetOffscreenOwnerIndices(Live2DModelHandle handle);

void Live2DFreeVertices(float *data);

// Vertex stride info
int Live2DGetVertexPositionStride(void); // 2 (x,y)
int Live2DGetVertexUVStride(void);       // 2 (u,v)
int Live2DGetVertexTotalStride(void);    // 4 (xyuv)

#ifdef __cplusplus
}
#endif

#endif
