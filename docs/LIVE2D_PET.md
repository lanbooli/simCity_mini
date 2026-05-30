# Live2D 桌面宠物

独立于主游戏窗口的桌面悬浮宠物，使用 Live2D Cubism 5 引擎渲染，具备完整的角色动画、语音对话和交互能力。

## 概述

- **定位**：macOS 原生桌面悬浮宠物（非 Web 内嵌）
- **引擎**：Live2D Cubism SDK for Native 5 + Metal 渲染
- **语言**：Swift + Objective-C++ 桥接
- **后端**：复用 city-town 现有 API + WebSocket
- **模型**：Haru（Cubism 示例角色，后续替换为自定义角色）

## 技术架构

```
┌────────────────────────────────────────────┐
│               SwiftUI Layer                │
│  ┌──────────────────────────────────────┐  │
│  │  PetWindow (NSWindow, transparent)   │  │
│  │  ├─ AvatarView (Metal rendering)     │  │
│  │  ├─ BubbleView (对话气泡)            │  │
│  │  ├─ MenuView (NPC选择)              │  │
│  │  └─ InputBar (输入框)               │  │
│  └──────────────────────────────────────┘  │
│                    │                        │
│  ┌─────────────────▼────────────────────┐  │
│  │     PetViewModel (ObservableObject)  │  │
│  │  ├─ WebSocket → city-town API        │  │
│  │  ├─ TTS audio playback               │  │
│  │  └─ NPC list / dialogue state        │  │
│  └──────────────────────────────────────┘  │
└────────────────────┬───────────────────────┘
                     │
┌────────────────────▼───────────────────────┐
│        Objective-C++ Bridge Layer          │
│  ┌──────────────────────────────────────┐  │
│  │  L2DPetBridge (.mm)                  │  │
│  │  ├─ init(modelPath) → load moc3      │  │
│  │  ├─ update(deltaTime) → anim tick    │  │
│  │  ├─ render(drawableSize) → Metal     │  │
│  │  ├─ startMotion(name) → play anim    │  │
│  │  └─ setExpression(name) → switch     │  │
│  └──────────────────────────────────────┘  │
└────────────────────┬───────────────────────┘
                     │
┌────────────────────▼───────────────────────┐
│       Cubism Native Framework (C++)        │
│  ┌──────────────────────────────────────┐  │
│  │  CubismUserModel                     │  │
│  │  ├─ CubismMoc (moc3 loader)          │  │
│  │  ├─ CubismModel (model state)        │  │
│  │  ├─ CubismMotion (motion player)     │  │
│  │  ├─ CubismExpressionMotion (表情)    │  │
│  │  ├─ CubismPhysics (物理模拟)         │  │
│  │  ├─ CubismEyeBlink (眨眼)           │  │
│  │  ├─ CubismBreath (呼吸)             │  │
│  │  └─ CubismRenderer_Metal (渲染)     │  │
│  └──────────────────────────────────────┘  │
└────────────────────┬───────────────────────┘
                     │
┌────────────────────▼───────────────────────┐
│        Cubism Core (C, 闭源)               │
│         libLive2DCubismCore.dylib           │
│  ├─ csmReviveMocInPlace (加载 moc)         │
│  ├─ csmInitializeModelInPlace (初始化)     │
│  ├─ csmUpdateModel (更新顶点)              │
│  └─ csmGetParameterValues (参数读写)       │
└────────────────────────────────────────────┘
```

## 项目结构

```
desktop_pet/live2d_pet/
├── CubismCore/                    # 从 CubismSdkForNative 复制
│   ├── include/
│   │   └── Live2DCubismCore.h     # Core C API 头文件
│   └── lib/
│       └── libLive2DCubismCore.dylib
├── CubismFramework/               # 从 CubismNativeFramework 复制
│   ├── CubismFramework.cpp/.hpp
│   ├── Model/                     # CubismMoc, CubismModel, CubismUserModel
│   ├── Motion/                    # CubismMotion, CubismExpressionMotion, Physics
│   ├── Effect/                    # CubismEyeBlink, CubismBreath, CubismPose
│   ├── Physics/                   # CubismPhysics
│   ├── Math/                      # CubismModelMatrix, CubismViewMatrix
│   ├── Id/                        # CubismIdManager
│   ├── Type/                      # csmString, csmVector
│   ├── Utils/                     # CubismJson, CubismString, CubismDebug
│   └── Rendering/
│       └── Metal/                 # CubismRenderer_Metal, Shaders
├── Bridge/                        # OC++ 桥接层
│   ├── L2DPetBridge.h
│   └── L2DPetBridge.mm
├── App/                           # SwiftUI 应用
│   ├── Live2DPetApp.swift         # 入口 + NSApplication
│   ├── PetWindow.swift            # 透明浮动窗口
│   ├── PetViewModel.swift         # 状态管理 + API 对接
│   ├── MetalView.swift            # MTKView 封装
│   ├── BubbleView.swift           # 对话气泡
│   └── MenuView.swift             # NPC 选择菜单
├── Resources/                     # 模型资源
│   └── Haru/
│       ├── Haru.moc3              # Live2D 模型文件
│       ├── Haru.model3.json       # 模型配置
│       ├── Haru.physics3.json     # 物理参数
│       ├── Haru.pose3.json        # 姿态参数
│       ├── Haru.cdi3.json         # 显示信息
│       ├── Haru.2048/             # 纹理贴图
│       ├── expressions/           # 表情定义
│       └── motions/               # 动作文件 (.motion3.json)
├── Shaders/                       # Metal Shader 源码
│   ├── Live2D.vertex.metal
│   └── Live2D.fragment.metal
├── BridgingHeader.h               # Swift → OC++ 桥接头
└── Makefile                       # 编译脚本
```

## 依赖来源

| 组件 | 来源 | 路径 |
|------|------|------|
| Cubism Core | Live2D 官网下载 (闭源) | `/tmp/CubismSdkForNative-5-r.5/Core/` |
| Cubism Native Framework | GitHub 开源 (MIT) | `~/Downloads/CubismNativeFramework-develop/src/` |
| Haru 模型 | Cubism SDK 示例 | `/tmp/CubismSdkForNative-5-r.5/Samples/Resources/Haru/` |

## 编译 & 运行

### 前置条件

- macOS 14.0+ (Sonoma)
- Xcode Command Line Tools（含 Metal shader 编译器）
- Swift 5.9+
- Python 3.14+（city-town 后端运行中）

### 构建

```bash
cd desktop_pet/live2d_pet

# 1. 编译 Metal shaders
xcrun -sdk macosx metal -c Shaders/Live2D.vertex.metal -o build/Live2D.vertex.air
xcrun -sdk macosx metal -c Shaders/Live2D.fragment.metal -o build/Live2D.fragment.air
xcrun -sdk macosx metallib build/*.air -o build/Live2DShaders.metallib

# 2. 编译 OC++ 桥接层 + Framework C++
swiftc -c Bridge/L2DPetBridge.mm \
  -I CubismCore/include \
  -I CubismFramework \
  -o build/L2DPetBridge.o

# 3. 编译 Framework .cpp 文件
# (列出所有 .cpp 并编译)

# 4. 链接最终可执行文件
swiftc App/*.swift build/*.o \
  -I CubismCore/include \
  -L CubismCore/lib -lLive2DCubismCore \
  -framework Metal -framework MetalKit \
  -framework SwiftUI -framework AppKit \
  -framework AVFoundation \
  -o Live2DPet
```

### 运行

```bash
# 确保 city-town 后端已启动
cd /Users/lanboo/lanbooassistent/city-town
source venv/bin/activate
python -m src.supervisor start

# 启动桌面宠物
./desktop_pet/live2d_pet/Live2DPet
```

## 功能规格

### 窗口特性

| 属性 | 值 |
|------|-----|
| 窗口样式 | `NSWindow.StyleMask.borderless` |
| 背景 | 透明 (`.clear`) |
| 层级 | `.floating`（悬浮于所有窗口之上） |
| 行为 | `.canJoinAllSpaces` + `.stationary`（跨 Space 停留） |
| 初始位置 | 屏幕右下角 |
| 拖动 | `isMovableByWindowBackground = true` |
| 大小 | 可缩放（头像区域 80~200px） |

### 角色动画

#### 空闲动画（自动循环）
- **呼吸**：`CubismBreath`，参数 `ParamBreath` 正弦波动
- **眨眼**：`CubismEyeBlink`，每 2-5 秒随机触发
- **物理**：`CubismPhysics`，头发/衣物摆动物理模拟
- **空闲动作**：随机播放 `motions/idle/` 下的动作文件（每 10-30 秒）

#### 触发动画
- **说话时**：播放 `motions/talk/` 动作
- **被点击**：播放 `motions/tap/` 反应动作
- **收到消息**：播放 `motions/surprised/` 惊喜动作
- **好感变化**：根据 fav 增减播放开心/难过动作

#### 表情切换
- 默认表情：normal
- 对话中：根据 NPC 心情切换（happy/surprised/sad/angry）
- 支持 {exp_name}.exp3.json 表情文件

### 对话系统

#### 气泡样式
```
      ┌──────────────┐
      │ NPC 对话内容   │  ← 灰色背景，1px边框
      └──────┬───────┘
             │ (三角箭头)
         (头像)
```

- NPC 消息 → 气泡显示在头像上方
- 玩家消息 → 气泡显示在输入框上方
- 上次气泡在新消息到来时替换（不堆叠）
- 5 秒无新消息后气泡渐隐

#### 对话流程
1. 玩家输入文字 → WebSocket 发送到 city-town
2. 后端 Player Process 消费 → stream:dialogue:{npc_id}
3. NPC Process LLM 生成回复
4. 回复通过 WebSocket 推回 → 宠物显示气泡 + 播放 TTS
5. TTS 播放时嘴巴张合动画同步

#### TTS 语音
- 复用 city-town 现有 TTS gateway
- 语音和 Web 端共享单通道（先到先得）
- 播放时显示声波动画

### 角色选择

- 点击头像 → 弹出 NPC 列表下拉菜单
- 列表显示所有 NPC 名称，当前选中标记 ✓
- 选择后立即切换模型头像（暂用 Haru 模型 + 名字首字覆盖）
- 后续版本可支持不同 NPC 使用不同 Live2D 模型

### 右键菜单

右键点击宠物 → 弹出上下文菜单：
- **角色信息**：小气泡显示 NPC 详细信息
  - 名字、心情、所在场景（真实名称）
  - 生理指数（饥饿/口渴/精力/社交）
  - 好感度、熟悉度、关系类型（用中文）
  - 可关闭
- **切换角色**：打开 NPC 选择菜单
- **设置**：窗口大小、位置锁定
- **退出**：关闭宠物

### 信息气泡

点击"角色信息"后显示：
```
┌──────────────────┐
│ 苏晓萌    ·开心   │
│ 📍 阳光咖啡店     │
│ 🌡️ 饱腹60 口渴45  │
│ ⚡ 精力70 👥社交55 │
│ 👥 朋友 ❤️72 👋58  │
│          [✕]     │
└──────────────────┘
```

- 场景名使用真实名称（如"阳光咖啡店"而非"scene_coffee_shop"）
- 关系类型使用中文（如"朋友"而非"friend"）
- 好感/熟悉度用 ❤️/👋 符号代替 favorability/familiarity

## API 集成

### 依赖的后端端点

| 端点 | 用途 | 调用时机 |
|------|------|---------|
| `GET /api/v1/npcs` | 获取 NPC 列表 | 启动时 + 定期刷新 |
| `GET /api/v1/npc/{id}` | 获取 NPC 详情 | 切换角色 + 查看信息 |
| `GET /api/v1/npc/{id}/relationship/{player_id}` | 获取关系数据 | 查看信息 |
| `WS /ws/game?player_id=player_001` | 对话 WebSocket | 持续连接 |

### WebSocket 消息格式

```json
// 发送（玩家对话）
{"type": "dialogue", "target_npc_id": "npc_su_xiaomeng", "message": "你好"}

// 接收（NPC 回复）
{
  "type": "npc_message",
  "npc_id": "npc_su_xiaomeng",
  "message": "你好呀！",
  "npc_mood": "开心",
  "favorability_change": 2
}
```

## 与现有 PetApp 的区别

| 特性 | PetApp.swift (旧) | Live2DPet (新) |
|------|-------------------|----------------|
| 渲染 | SwiftUI 原生组件 | Metal + Live2D 引擎 |
| 角色表现 | 静态头像/首字 | 完整 Live2D 动画模型 |
| 动画 | 无 | 呼吸/眨眼/物理/动作/表情 |
| 对话气泡 | SwiftUI 布局 | 自定义气泡（含箭头） |
| 底层 | 纯 Swift | Swift + OC++ + C++ + C |
| 保留 | ✅ 继续保留 | 🆕 新增 |

两个宠物可同时运行，互不影响。

## 后续扩展

- [ ] 每个 NPC 使用独立 Live2D 模型
- [ ] 玩家自定义角色模型上传
- [ ] 连续对话模式（如打电话）
- [ ] 触摸/拖动交互（摸头、戳脸蛋 → NPC 反应动作）
- [ ] 好感度驱动换装
- [ ] 多角色同屏（双人互动动画）
- [ ] 天气/时间联动（晚上打哈欠、雨天撑伞）

## 许可证

- Cubism Core: Live2D Proprietary Software License
- Cubism Native Framework: MIT
- Haru 模型: Live2D Free Material License（仅限个人/评估使用）
- 本项目代码: MIT
