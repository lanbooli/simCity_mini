# Live2D 桌面宠物设计方案

## 概述

在现有城市小镇项目中新增一个基于 Live2D Cubism 5 Native SDK 的桌面宠物，
使用 Metal 渲染，SwiftUI 窗口，连接现有游戏后端。

## 目录结构

```
desktop_pet/live2d_pet/
├── DESIGN.md              # 本文档
├── CubismCore/            # Cubism 5 Native SDK 核心
│   ├── include/           # C 头文件 (Live2DCubismCore.h)
│   └── lib/               # 静态库 (arm64 libLive2DCubismCore.a)
├── Model/                 # Live2D 模型文件
│   └── Haru/              # 默认模型：Haru（少女）
│       ├── Haru.moc3
│       ├── Haru.model3.json
│       ├── Haru.physics3.json
│       ├── Haru.cdi3.json
│       ├── Haru.2048/     # 纹理图集
│       ├── motions/       # 28 个动作
│       └── expressions/   # 9 种表情
├── Shaders/
│   └── Live2D.metal       # Metal 着色器
├── Bridge/
│   ├── Live2DBridge.h     # C/ObjC 桥接头
│   └── Live2DBridge.mm    # 桥接实现
├── Renderer/
│   ├── Live2DModel.swift      # 模型加载与控制
│   ├── Live2DRenderer.swift   # Metal 渲染器
│   └── Live2DTexture.swift    # 纹理管理
├── Live2DPetApp.swift     # 主程序入口
├── Live2DPetWindow.swift  # 透明窗口管理
└── Makefile               # 编译脚本
```

## 技术栈

| 层 | 选型 | 说明 |
|---|------|------|
| 窗口 | SwiftUI + AppKit | NSWindow 透明无边框 |
| 渲染 | Metal 3 | GPU 加速，macOS 原生 |
| 模型 | Cubism 5 Native C API | 官方静态库 arm64 |
| 桥接 | Objective-C++ (.mm) | Swift ↔ C++ 中间层 |
| 音频 | AVAudioEngine | TTS 音频播放 + 口型分析 |
| 后端 | WebSocket | 连城市小镇 localhost:8000 |

## 架构图

```
┌──────────────────────────────────────────┐
│              Live2DPetApp                 │
│  ┌────────────┐  ┌───────────────────┐   │
│  │ WebSocket   │  │  Live2DMetalView  │   │
│  │ (连后端)    │  │  (NSViewRepresent)│   │
│  │             │  │  ┌─────────────┐  │   │
│  │ 接收:       │  │  │ Metal 渲染  │  │   │
│  │ ·对话消息   │  │  │ ·模型绘制   │  │   │
│  │ ·TTS音频URL │  │  │ ·参数更新   │  │   │
│  │ ·NPC状态    │  │  │ ·表情/动作  │  │   │
│  └────────────┘  │  └─────────────┘  │   │
│                   └───────────────────┘   │
│  ┌────────────┐  ┌───────────────────┐   │
│  │ AVAudio     │  │  气泡对话框       │   │
│  │ ·播放TTS    │  │  (同现有PetApp)   │   │
│  │ ·口型分析   │  │                   │   │
│  └────────────┘  └───────────────────┘   │
└──────────────────────────────────────────┘
```

## 核心模块

### 1. Bridge 桥接层 (`Bridge/Live2DBridge.mm`)

封装 Cubism C API 为 Swift 可调用的接口：

```
Live2DBridge:
  模型加载:
    loadModel(path) → handle
    releaseModel(handle)
    update(handle)

  参数控制:
    getParameterIDs(handle) → [String]
    setParameter(handle, id, value)    // 口型、表情等
    getPartIDs(handle) → [String]
    setPartOpacity(handle, id, value)

  渲染数据:
    getDrawableVertexCount(handle, index) → Int
    getDrawableVertices(handle, index) → [Float]  // xy+uv
    getDrawableIndexCount(handle, index) → Int
    getDrawableIndices(handle, index) → [UInt16]
    getDrawableTextureIndex(handle, index) → Int
    getDrawableOpacity(handle, index) → Float
    getDrawableBlendMode(handle, index) → Int
```

### 2. Metal 渲染器 (`Renderer/Live2DRenderer.swift`)

- 用 `MTKView` 嵌在 SwiftUI 中（`NSViewRepresentable`）
- 每帧调用 bridge 获取顶点/索引/纹理数据
- 上传到 Metal Buffer
- 绘制到透明背景的 MTKView

### 3. 模型控制 (`Renderer/Live2DModel.swift`)

- 加载 `.model3.json` → 解析纹理、动作、表情
- 自动呼吸 + 眨眼参数循环
- 根据 NPC mood 切换表情
- TTS 播放时驱动口型参数

### 4. 窗口管理 (`Live2DPetWindow.swift`)

- 复用现有 `PetWindow.swift` 的透明无边框方案
- 窗口大小根据模型自适应
- 支持拖拽移动、右键菜单（选 NPC、退出）

### 5. WebSocket 集成

完全复用现有 `PetApp.swift` 的 WebSocket 逻辑：
- `dialogue_response` → 显示气泡 + 播 TTS + 口型同步
- `npc_state_update` → 更新表情、心情
- `dialogue_send` → 发送对话

## 口型同步流程

```
TTS音频 → AVAudioPlayer 播放
         → AVAudioEngine tap 获取 PCM
         → 计算元音权重 (A/E/I/O/U)
         → 映射 Live2D 口型参数:
            ParamMouthOpenY  ← 音量振幅
            ParamMouthForm   ← 元音形状
```

## 与现有 PetApp 的关系

- 现有 `desktop_pet/native/PetApp.swift` 保持不变
- 新宠物在 `desktop_pet/live2d_pet/` 独立目录
- `start.sh` 可通过环境变量切换：
  ```bash
  PET_MODE=live2d ./start.sh   # 启动 Live2D 宠物
  PET_MODE=native ./start.sh   # 启动原有宠物
  ```
