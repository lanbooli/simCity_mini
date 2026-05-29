#!/bin/bash
# 编译 Swift 原生桌面宠物
cd "$(dirname "$0")/native"
echo "🔨 编译 Swift..."
swiftc -o PetAssistant PetWindow.swift -framework Cocoa -framework WebKit
echo "✅ 编译完成: ./PetAssistant"
echo "运行: ./PetAssistant"
