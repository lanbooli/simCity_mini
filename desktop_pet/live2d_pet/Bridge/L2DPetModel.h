#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <MetalKit/MetalKit.h>

NS_ASSUME_NONNULL_BEGIN

/// Bridge wrapping the official Cubism Framework (CubismUserModel + CubismRenderer_Metal)
/// Handles model loading, rendering with masks, and copying to display drawable.
@interface L2DPetModel : NSObject

/// Load model from directory containing .model3.json and .moc3
- (nullable instancetype)initWithModelDir:(NSString *)dir
                                   device:(id<MTLDevice>)device
                                     size:(CGSize)viewSize;

/// Update animation parameters (breath, blink, sway)
- (void)updateWithDeltaTime:(float)dt;

/// Render model to internal offscreen, then copy to drawable
- (void)drawToDrawable:(id<CAMetalDrawable>)drawable
         commandBuffer:(id<MTLCommandBuffer>)commandBuffer;

/// Set a model parameter by name (e.g., "ParamMouthForm")
- (void)setParameter:(NSString *)name value:(float)value;

@property (nonatomic, readonly) int drawableCount;

@end

NS_ASSUME_NONNULL_END
