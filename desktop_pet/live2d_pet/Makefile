APP_NAME = Live2DPet
BUILD_DIR = build
export CLANG_MODULE_CACHE_PATH = $(shell pwd)/build/clang_cache
SWIFTC = $(shell xcrun --find swiftc)
CLANGXX = $(shell xcrun --find clang++)
SDK_ROOT = $(shell xcrun --show-sdk-path)

CORE_INCLUDE = CubismCore/include
FW_INCLUDE = CubismFramework
FW_RENDERING = CubismFramework/Rendering/Metal

FW_SRCS := $(shell find CubismFramework \( -name '*.cpp' -o -name '*.mm' \) \
              | grep -v '/OpenGL/' | grep -v '/Vulkan/' | grep -v '/D3D')
FW_OBJS = $(patsubst %.cpp,$(BUILD_DIR)/%.o,$(patsubst %.mm,$(BUILD_DIR)/%.o,$(FW_SRCS)))

SWIFT_FILES = App/main.swift Live2DPetApp.swift

FRAMEWORKS = -framework SwiftUI -framework AppKit -framework Metal -framework MetalKit \
             -framework AVFoundation -framework QuartzCore -framework Foundation

COMMON_INC = -I$(CORE_INCLUDE) -I$(FW_INCLUDE) -I$(FW_RENDERING)
COMMON_FLAGS = -arch arm64 -isysroot $(SDK_ROOT) -mmacosx-version-min=14.0 -std=c++17 -O2

SWIFT_FLAGS = -sdk $(SDK_ROOT) -target arm64-apple-macosx14.0 -O \
              -import-objc-header Bridge/L2DPetModel.h \
              -I Bridge

.PHONY: all clean run

all: $(BUILD_DIR)/$(APP_NAME)
	@echo "✅ Build complete: $(BUILD_DIR)/$(APP_NAME)"

# Pattern rules for Framework (no ARC)
$(BUILD_DIR)/%.o: %.cpp
	@mkdir -p $(dir $@)
	$(CLANGXX) $(COMMON_FLAGS) -fno-objc-arc $(COMMON_INC) -c $< -o $@

$(BUILD_DIR)/%.o: %.mm
	@mkdir -p $(dir $@)
	$(CLANGXX) $(COMMON_FLAGS) -fno-objc-arc $(COMMON_INC) -c $< -o $@

$(BUILD_DIR)/libCubismFramework.a: $(FW_OBJS)
	ar rcs $@ $(FW_OBJS)

# Our bridge (with ARC, specific rule overrides pattern)
$(BUILD_DIR)/Bridge/L2DPetModel.o: Bridge/L2DPetModel.mm Bridge/L2DPetModel.h
	@mkdir -p $(dir $@)
	$(CLANGXX) $(COMMON_FLAGS) -fobjc-arc $(COMMON_INC) -c $< -o $@

# Final link
$(BUILD_DIR)/$(APP_NAME): shaders $(SWIFT_FILES) $(BUILD_DIR)/Bridge/L2DPetModel.o $(BUILD_DIR)/libCubismFramework.a
	@mkdir -p $(BUILD_DIR)
	$(SWIFTC) $(SWIFT_FLAGS) \
		$(SWIFT_FILES) \
		$(BUILD_DIR)/Bridge/L2DPetModel.o \
		$(BUILD_DIR)/libCubismFramework.a \
		-L CubismCore/lib -lLive2DCubismCore \
		$(FRAMEWORKS) \
		-Xlinker -rpath -Xlinker @executable_path/../CubismCore/lib \
		-lc++ \
		-o $@

run: $(BUILD_DIR)/$(APP_NAME)
	@echo "Starting Live2D Pet..."
	cd $(CURDIR) && ./$(BUILD_DIR)/$(APP_NAME)

# ── Blend shader metallibs ──
SHADER_OUT_DIR = $(BUILD_DIR)/FrameworkMetallibs
SHADER_SCRIPT = scripts/compile_blend_shaders.zsh
.PHONY: shaders
shaders:
	@if [ ! -d "$(SHADER_OUT_DIR)" ] || [ -z "$$(ls -A $(SHADER_OUT_DIR) 2>/dev/null)" ]; then \
		echo "  Compiling blend shaders..."; \
		zsh $(SHADER_SCRIPT); \
	else \
		echo "  Blend shaders already compiled ($(SHADER_OUT_DIR))"; \
	fi

clean:
	rm -rf $(BUILD_DIR)

