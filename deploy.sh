#!/bin/bash
echo "🚀 开始部署交易策略回测系统到Railway..."

# 检查是否已安装Git
if ! command -v git &> /dev/null; then
    echo "❌ Git未安装，请先安装Git"
    exit 1
fi

# 检查是否已登录GitHub
echo "📋 检查GitHub配置..."
git config --global user.name
git config --global user.email

if [ $? -ne 0 ]; then
    echo "⚠️ 请先配置Git用户信息："
    echo "git config --global user.name \"您的用户名\""
    echo "git config --global user.email \"您的邮箱\""
    exit 1
fi

# 初始化Git仓库
echo "📁 初始化Git仓库..."
git init
git add .
git commit -m "feat: 部署交易策略回测系统"

echo "✅ Git仓库初始化完成！"

# 创建GitHub仓库说明
echo ""
echo "📝 下一步操作："
echo "1. 在GitHub上创建新仓库：https://github.com/new"
echo "2. 将本地仓库推送到GitHub："
echo "   git remote add origin https://github.com/您的用户名/仓库名.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "3. 访问Railway：https://railway.app/"
echo "4. 点击'New Project' -> 'Deploy from GitHub repo'"
echo "5. 选择您的仓库进行部署"
echo ""
echo "6. 在Railway项目设置中配置环境变量："
echo "   OKX_API_KEY=您的API密钥"
echo "   OKX_API_SECRET=您的API密钥"
echo "   OKX_API_PASSPHRASE=您的API密码"
echo ""
echo "🎯 部署完成后，访问Railway提供的URL即可使用系统！"

echo ""
echo "📊 系统功能："
echo "• 3种技术指标组合策略回测"
echo "• OKX交易所真实数据"
echo "• Web可视化界面"
echo "• 实时市场数据分析"