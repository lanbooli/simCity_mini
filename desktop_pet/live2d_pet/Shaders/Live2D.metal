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
    float4 color = texture.sample(sampler, in.texCoord);
    // Premultiplied alpha (Live2D default)
    return color;
}
