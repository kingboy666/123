#!/usr/bin/env python3
"""
交易策略回测系统启动脚本
启动Web界面服务
"""

import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def main():
    print("🚀 启动交易策略回测系统...")
    
    # 检查环境变量
    required_env_vars = ['OKX_API_KEY', 'OKX_API_SECRET', 'OKX_API_PASSPHRASE']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"⚠️ 缺少环境变量: {', '.join(missing_vars)}")
        print("请在Railway项目设置中配置以下环境变量:")
        print("OKX_API_KEY=您的API密钥")
        print("OKX_API_SECRET=您的API密钥")  
        print("OKX_API_PASSPHRASE=您的API密码")
        print("\n本地测试时，请在.env文件中配置这些变量")
        return
    
    print("✅ 环境变量检查通过")
    
    # 启动Web服务
    try:
        from web_backtest import app
        print("🌐 启动Flask Web服务...")
        print("访问地址: http://localhost:5000")
        print("按 Ctrl+C 停止服务")
        
        # 启动Flask应用
        app.run(host='0.0.0.0', port=5000, debug=False)
        
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        print("请检查依赖包是否安装完整")
        print("运行: pip install -r requirements.txt")

if __name__ == "__main__":
    main()