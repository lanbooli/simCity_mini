#!/bin/bash
cd "$(dirname "$0")/native"
echo "🔨 编译 Swift 桌面宠物..."
swiftc PetApp.swift -o PetApp -framework SwiftUI -framework AppKit -framework AVFoundation
echo "✅ 编译完成"
echo "运行: ./PetApp"
./PetApp
