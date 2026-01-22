#!/bin/bash
# CaseSim Quick Start Script
# Run this to get started immediately

set -e

echo "🚀 CaseSim Quick Start"
echo "===================="

# Check Python
echo "✓ Checking Python..."
python --version || (echo "❌ Python not found. Install Python 3.8+"; exit 1)

# Install dependencies
echo "✓ Installing dependencies..."
pip install -q -r requirements.txt

# Check/create secrets
echo "✓ Checking configuration..."
if [ ! -f ".streamlit/secrets.toml" ]; then
    echo "⚠️  Creating .streamlit/secrets.toml template..."
    mkdir -p .streamlit
    cat > .streamlit/secrets.toml << 'EOF'
# Add your API key here
ANTHROPIC_API_KEY = "sk-ant-..."
# OR use OpenAI:
# OPENAI_API_KEY = "sk-..."
EOF
    echo "⚠️  Edit .streamlit/secrets.toml with your API key"
    exit 1
fi

# Check API key
if ! grep -q "sk-ant-\|sk-" .streamlit/secrets.toml 2>/dev/null; then
    echo "❌ No valid API key found in .streamlit/secrets.toml"
    echo "   Please add ANTHROPIC_API_KEY or OPENAI_API_KEY"
    exit 1
fi

# Create data directories
mkdir -p data/db data/uploads

echo ""
echo "✅ Setup complete!"
echo ""
echo "Starting CaseSim..."
echo "🌐 Open: http://localhost:8501"
echo ""

# Run Streamlit
streamlit run app_casesim.py
