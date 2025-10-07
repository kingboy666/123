#!/usr/bin/env python3
"""
API配置测试脚本
用于测试OKX交易所API配置是否正确
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def test_api_config():
    """测试API配置"""
    print("=== OKX API配置测试 ===")
    
    # 检查环境变量
    api_key = os.getenv('OKX_API_KEY')
    secret_key = os.getenv('OKX_SECRET_KEY') 
    passphrase = os.getenv('OKX_PASSPHRASE')
    
    print(f"OKX_API_KEY: {'已设置' if api_key else '未设置'}")
    print(f"OKX_SECRET_KEY: {'已设置' if secret_key else '未设置'}")
    print(f"OKX_PASSPHRASE: {'已设置' if passphrase else '未设置'}")
    
    if all([api_key, secret_key, passphrase]):
        print("\n✅ 所有API配置都已正确设置！")
        print("配置信息:")
        print(f"API Key长度: {len(api_key)}")
        print(f"Secret Key长度: {len(secret_key)}")
        print(f"Passphrase长度: {len(passphrase)}")
        return True
    else:
        print("\n❌ API配置不完整！")
        print("\n请按照以下方式设置API配置:")
        print("\n方式1 - 创建.env文件:")
        print("在项目根目录创建.env文件，内容如下:")
        print("""
OKX_API_KEY=your_api_key_here
OKX_SECRET_KEY=your_secret_key_here  
OKX_PASSPHRASE=your_passphrase_here
        """)
        
        print("\n方式2 - 设置环境变量:")
        print("Windows:")
        print("set OKX_API_KEY=your_api_key_here")
        print("set OKX_SECRET_KEY=your_secret_key_here")
        print("set OKX_PASSPHRASE=your_passphrase_here")
        
        print("\nLinux/Mac:")
        print("export OKX_API_KEY=your_api_key_here")
        print("export OKX_SECRET_KEY=your_secret_key_here")
        print("export OKX_PASSPHRASE=your_passphrase_here")
        
        return False

if __name__ == "__main__":
    test_api_config()