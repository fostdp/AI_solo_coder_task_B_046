#!/bin/bash
# ============================================================
#   古代水利工程遗迹功能复原与可持续性评估系统
#   启动脚本 (Linux / macOS)
# ============================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "============================================================"
echo "  古代水利工程遗迹功能复原与可持续性评估系统"
echo "  启动脚本 (Linux/macOS)"
echo "============================================================"
echo ""

# 1. 检查Python
echo "[1/5] 检查Python环境..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 未检测到Python3，请先安装Python 3.9+"
    exit 1
fi
python3 --version
echo "✅ Python环境就绪"
echo ""

# 2. 创建虚拟环境并安装依赖
echo "[2/5] 检查并安装后端依赖..."
cd "$PROJECT_DIR/backend"

if [ ! -d "venv" ]; then
    echo "创建Python虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt
echo "✅ 后端依赖安装完成"
echo ""

# 3. 生成模拟数据
echo "[3/5] 生成模拟数据..."
cd "$PROJECT_DIR"
python3 scripts/generate_data.py
echo "✅ 数据生成完成"
echo ""

# 4. 数据库初始化说明
echo "[4/5] 数据库初始化提示："
echo "  请确保PostgreSQL已启动，并执行以下SQL："
echo "    CREATE DATABASE water_heritage;"
echo "    \c water_heritage"
echo "    CREATE EXTENSION postgis;"
echo "  然后运行："
echo "    python3 scripts/init_database.py"
echo ""
cp -n backend/.env.example backend/.env || true

# 5. 启动服务
echo "[5/5] 启动FastAPI后端服务..."
cd "$PROJECT_DIR/backend"
source venv/bin/activate

echo ""
echo "============================================================"
echo "  后端服务地址: http://localhost:8000"
echo "  API文档:      http://localhost:8000/docs"
echo "============================================================"
echo "  前端: 请在浏览器打开 frontend/index.html"
echo "  或使用: python3 -m http.server 3000 --directory frontend"
echo "============================================================"
echo ""

python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
