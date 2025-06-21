#!/bin/bash

# DataVisSUS Web Interface Startup Script

echo "🚀 Starting DataVisSUS Web Interface..."
echo "=" | head -c 50; echo

# Check if Node.js is available
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 16+ and try again."
    exit 1
fi

# Check if Python bridge is working
echo "🐍 Testing Python bridge..."
if python3 python_bridge.py health > /dev/null 2>&1; then
    echo "✅ Python bridge is working"
else
    echo "⚠️  Python bridge test failed - some features may not work"
    echo "   Make sure Ollama is running and dependencies are installed"
fi

# Check if dependencies are installed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing Node.js dependencies..."
    npm install
fi

# Start the server
echo "🌐 Starting web server..."
echo "   Interface will be available at: http://localhost:3000"
echo "   Press Ctrl+C to stop"
echo "=" | head -c 50; echo

# Start in development mode if DEV environment variable is set
if [ "$DEV" = "1" ]; then
    echo "🔧 Starting in development mode..."
    npm run dev
else
    npm start
fi