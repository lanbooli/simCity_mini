#!/bin/bash
# Live2D Desktop Pet Launcher
cd "$(dirname "$0")"
./build/Live2DPet &
echo "Live2D Pet started (PID: $!)"
