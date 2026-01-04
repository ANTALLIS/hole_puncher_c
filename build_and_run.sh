#!/bin/bash
# build_and_run.sh - Cross-platform build script for Linux and macOS

set -e  # Exit on error

echo "=== P2P Test Program - Build Script ==="
echo ""

# Detect OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     PLATFORM=Linux;;
    Darwin*)    PLATFORM=macOS;;
    *)          PLATFORM="UNKNOWN:${OS}"
esac

echo "Detected platform: $PLATFORM"
echo ""

# Compile
echo "Compiling p2p_test.c..."

if [ "$PLATFORM" = "Linux" ]; then
    gcc -o p2p_test p2p_test.c -Wall -O2
elif [ "$PLATFORM" = "macOS" ]; then
    clang -o p2p_test p2p_test.c -Wall -O2
else
    echo "Unsupported platform: $PLATFORM"
    exit 1
fi

if [ $? -eq 0 ]; then
    echo "✓ Compilation successful!"
    echo ""
    echo "=== Running P2P Test Program ==="
    echo ""
    ./p2p_test
else
    echo "✗ Compilation failed!"
    exit 1
fi

