#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface Live2DWrapper : NSObject

- (nullable instancetype)initWithModelDir:(NSString *)modelDir;
- (void)update;
- (int)drawableCount;
- (int)vertexCountForDrawable:(int)index;
- (float * _Nullable)verticesForDrawable:(int)index outVertCount:(int *)outVertCount;
- (int)indexCountForDrawable:(int)index;
- (const unsigned short * _Nullable)indicesForDrawable:(int)index;
- (int)textureIndexForDrawable:(int)index;
- (float)opacityForDrawable:(int)index;
- (int)isVisibleForDrawable:(int)index;
- (const int *)renderOrders;
- (int)maskCountForDrawable:(int)index;
- (const int *)masksForDrawable:(int)index;
- (const int *)maskIndicesForDrawable:(int)index count:(int *)outCount;
- (int)offscreenCount;
- (void)getCanvasWidth:(float *)w height:(float *)h;
- (int)parameterCount;
- (nullable NSString *)parameterIdAtIndex:(int)index;
- (float)parameterValueAtIndex:(int)index;
- (float)parameterValue:(NSString *)paramId;
- (void)setParameter:(NSString *)paramId value:(float)value;

@end

NS_ASSUME_NONNULL_END
