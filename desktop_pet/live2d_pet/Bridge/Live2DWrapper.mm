#import "Live2DWrapper.h"
#import "Live2DBridge.h"

@implementation Live2DWrapper {
    Live2DModelHandle _handle;
}

- (instancetype)initWithModelDir:(NSString *)modelDir {
    self = [super init];
    if (self) {
        NSString *jsonPath = [modelDir stringByAppendingPathComponent:@"Haru.model3.json"];
        _handle = Live2DLoadModel([jsonPath UTF8String]);
        if (!_handle) {
            NSLog(@"[Live2D] Failed to load model from %@", jsonPath);
            return nil;
        }
        NSLog(@"[Live2D] Model loaded successfully");
    }
    return self;
}

- (void)dealloc {
    if (_handle) Live2DReleaseModel(_handle);
}

- (void)update { Live2DUpdate(_handle); }

- (int)drawableCount { return Live2DGetDrawableCount(_handle); }
- (int)vertexCountForDrawable:(int)index { return Live2DGetDrawableVertexCount(_handle, index); }
- (float *)verticesForDrawable:(int)index outVertCount:(int *)outVertCount {
    return Live2DGetDrawableVertices(_handle, index, outVertCount);
}
- (int)indexCountForDrawable:(int)index { return Live2DGetDrawableIndexCount(_handle, index); }
- (const unsigned short *)indicesForDrawable:(int)index { return Live2DGetDrawableIndices(_handle, index); }
- (int)textureIndexForDrawable:(int)index { return Live2DGetDrawableTextureIndex(_handle, index); }
- (float)opacityForDrawable:(int)index { return Live2DGetDrawableOpacity(_handle, index); }
- (int)isVisibleForDrawable:(int)index { return Live2DGetDrawableIsVisible(_handle, index); }
- (const int *)renderOrders { return Live2DGetRenderOrders(_handle); }
- (int)maskCountForDrawable:(int)index { return Live2DGetDrawableMaskCount(_handle, index); }
- (const int *)masksForDrawable:(int)index { return Live2DGetDrawableMasks(_handle, index); }
- (const int *)maskIndicesForDrawable:(int)index count:(int *)outCount { *outCount = Live2DGetDrawableMaskCount(_handle, index); return Live2DGetDrawableMasks(_handle, index); }
- (int)offscreenCount { return Live2DGetOffscreenCount(_handle); }

- (void)getCanvasWidth:(float *)w height:(float *)h {
    Live2DGetCanvasSize(_handle, w, h);
}

- (int)parameterCount { return Live2DGetParameterCount(_handle); }

- (NSString *)parameterIdAtIndex:(int)index {
    const char * const *ids = Live2DGetParameterIDs(_handle);
    if (!ids || index >= Live2DGetParameterCount(_handle)) return nil;
    const char *id = ids[index];
    return id ? [NSString stringWithUTF8String:id] : nil;
}

- (float)parameterValueAtIndex:(int)index {
    return Live2DGetParameterValue(_handle, index);
}

- (float)parameterValue:(NSString *)paramId {
    int idx = Live2DFindParameterIndex(_handle, [paramId UTF8String]);
    if (idx < 0) return 0;
    return Live2DGetParameterValue(_handle, idx);
}

- (void)setParameter:(NSString *)paramId value:(float)value {
    int idx = Live2DFindParameterIndex(_handle, [paramId UTF8String]);
    if (idx < 0) return;
    Live2DSetParameterValue(_handle, idx, value);
}

@end
