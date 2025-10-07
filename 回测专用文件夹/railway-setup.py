#!/usr/bin/env python3
"""
Railway部署配置检查脚本
检查系统配置并生成部署报告
"""

import os
import sys
import json
import subprocess
from pathlib import Path

def check_requirements():
    """检查依赖包是否可用"""
    print("🔍 检查依赖包配置...")
    
    requirements = [
        "flask", "ccxt", "pandas", "numpy", "talib-binary", 
        "plotly", "python-dotenv", "requests"
    ]
    
    missing = []
    for req in requirements:
        try:
            __import__(req.replace("-", "_"))
            print(f"✅ {req}")
        except ImportError:
            missing.append(req)
            print(f"❌ {req}")
    
    return missing

def check_config_files():
    """检查配置文件"""
    print("\n📁 检查配置文件...")
    
    required_files = [
        "main.py", "data_fetcher.py", "real_backtest.py", 
        "web_backtest.py", "requirements.txt", "Procfile",
        "railway.json", "templates/index.html"
    ]
    
    missing_files = []
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file}")
        else:
            missing_files.append(file)
            print(f"❌ {file}")
    
    return missing_files

def check_environment():
    """检查环境配置"""
    print("\n🌐 检查环境配置...")
    
    # 检查Python版本
    python_version = sys.version_info
    print(f"Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # 检查当前目录
    current_dir = os.getcwd()
    print(f"工作目录: {current_dir}")
    
    # 检查文件权限
    try:
        with open("test_write.txt", "w") as f:
            f.write("test")
        os.remove("test_write.txt")
        print("✅ 文件写入权限: 正常")
    except Exception as e:
        print(f"❌ 文件写入权限: {e}")

def generate_deployment_report():
    """生成部署报告"""
    print("\n📊 生成部署报告...")
    
    report = {
        "系统状态": "准备部署",
        "Python版本": f"{sys.version_info.major}.{sys.version_info.minor}",
        "工作目录": os.getcwd(),
        "文件总数": len(list(Path('.').rglob('*'))),
        "配置检查": {
            "requirements.txt": os.path.exists("requirements.txt"),
            "Procfile": os.path.exists("Procfile"),
            "railway.json": os.path.exists("railway.json"),
            "main.py": os.path.exists("main.py")
        }
    }
    
    # 保存报告
    with open("deployment_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print("✅ 部署报告已生成: deployment_report.json")

def main():
    print("🚀 Railway部署配置检查")
    print("=" * 50)
    
    # 执行检查
    missing_packages = check_requirements()
    missing_files = check_config_files()
    check_environment()
    generate_deployment_report()
    
    print("\n" + "=" * 50)
    print("📋 检查结果汇总:")
    
    if not missing_packages and not missing_files:
        print("🎉 所有配置检查通过！系统已准备好部署到Railway。")
        print("\n📝 下一步操作:")
        print("1. 运行: bash deploy.sh")
        print("2. 按照提示推送到GitHub")
        print("3. 在Railway中部署项目")
    else:
        if missing_packages:
            print(f"⚠️ 缺少依赖包: {', '.join(missing_packages)}")
            print("   请运行: pip install -r requirements.txt")
        
        if missing_files:
            print(f"⚠️ 缺少文件: {', '.join(missing_files)}")
        
        print("\n❌ 请先解决上述问题再部署。")

if __name__ == "__main__":
    main()