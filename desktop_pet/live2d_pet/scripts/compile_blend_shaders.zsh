#!/bin/zsh
set -e
SCRIPT_DIR="${0:a:h}"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$PROJECT_DIR/CubismFramework/Rendering/Metal/Shaders/BlendShaders"
OUT_DIR="$PROJECT_DIR/build/FrameworkMetallibs"

if [[ -x /Volumes/MetalToolchainCryptex/Metal.xctoolchain/usr/bin/metal ]]; then
    METAL_BIN="/Volumes/MetalToolchainCryptex/Metal.xctoolchain/usr/bin/metal"
elif METAL_PATH=$(xcrun --find metal 2>/dev/null); then
    METAL_BIN="$METAL_PATH"
else
    echo "ERROR: metal compiler not found."
    exit 1
fi
echo "Using metal: $METAL_BIN"

# Ensure clang module cache dir exists and is writable
mkdir -p "$HOME/.cache/clang/ModuleCache" 2>/dev/null || true

mkdir -p "$OUT_DIR"

typeset -A COLOR_MODES
COLOR_MODES=(Add 5 AddGlow 6 Darken 7 Multiply 8 ColorBurn 9 LinearBurn 10 Lighten 11 Screen 12 ColorDodge 13 Overlay 14 SoftLight 15 HardLight 16 LinearLight 17 Hue 18 Color 19)

typeset -A ALPHA_MODES
ALPHA_MODES=(Over 0 Atop 1 Out 2 ConjointOver 3 DisjointOver 4)

VERT_VARIANTS=(VertShaderSrcBlend VertShaderSrcMaskedBlend)

FRAG_BASES=(FragShaderSrcBlend FragShaderSrcMaskBlend FragShaderSrcMaskInvertedBlend FragShaderSrcPremultipliedAlphaBlend FragShaderSrcMaskPremultipliedAlphaBlend FragShaderSrcMaskInvertedPremultipliedAlphaBlend)

echo "Compiling blend shaders..."

for vert in $VERT_VARIANTS; do
    output="$OUT_DIR/${vert}.metallib"
    src="$SRC_DIR/${vert}.metal"
    if [[ -f "$src" ]]; then
        if "$METAL_BIN" -c "$src" -I "$SRC_DIR" -o "$output" 2>/dev/null; then
            echo "  $vert.metallib"
        else
            echo "  FAILED: $vert (run without 2>/dev/null to see error)"
            "$METAL_BIN" -c "$src" -I "$SRC_DIR" -o "$output" 2>&1 | head -5
        fi
    fi
done

for frag_base in $FRAG_BASES; do
    for color_name in ${(k)COLOR_MODES}; do
        for alpha_name in ${(k)ALPHA_MODES}; do
            cval=${COLOR_MODES[$color_name]}
            aval=${ALPHA_MODES[$alpha_name]}
            fname="${frag_base}${color_name}${alpha_name}"
            output="$OUT_DIR/${fname}.metallib"
            src="$SRC_DIR/${frag_base}.metal"
            if [[ -f "$src" ]]; then
                "$METAL_BIN" -c "$src" -I "$SRC_DIR" \
                    -D CSM_COLOR_BLEND_MODE=$cval \
                    -D CSM_ALPHA_BLEND_MODE=$aval \
                    -o "$output" 2>/dev/null && echo "  $fname.metallib" || true
            fi
        done
    done
done

echo "Done: $(ls "$OUT_DIR" 2>/dev/null | wc -l) files in $OUT_DIR"
