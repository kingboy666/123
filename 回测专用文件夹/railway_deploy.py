#!/usr/bin/env python3
"""
Railway部署脚本
用于在Railway平台上部署交易策略回测系统
"""

import os
import sys
from datetime import datetime

def check_environment():
    """检查环境配置"""
    print("🔍 检查环境配置...")
    
    # 检查必要的环境变量
    required_env_vars = ['OKX_API_KEY', 'OKX_API_SECRET', 'OKX_API_PASSPHRASE']
    missing_vars = []
    
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ 缺少环境变量: {', '.join(missing_vars)}")
        print("请在Railway环境变量中设置以下变量:")
        print("OKX_API_KEY - OKX API密钥")
        print("OKX_API_SECRET - OKX API秘钥") 
        print("OKX_API_PASSPHRASE - OKX API密码短语")
        return False
    
    print("✅ 环境变量检查通过")
    return True

def install_dependencies():
    """安装依赖"""
    print("📦 安装依赖包...")
    
    try:
        import pandas
        import ccxt
        import talib
        import flask
        print("✅ 所有依赖包已安装")
        return True
    except ImportError as e:
        print(f"❌ 依赖包缺失: {e}")
        print("请确保requirements.txt中的包已正确安装")
        return False

def test_data_connection():
    """测试数据连接"""
    print("🌐 测试OKX数据连接...")
    
    try:
        from data_fetcher import OKXDataFetcher
        fetcher = OKXDataFetcher()
        
        # 测试获取市场数据
        market_data = fetcher.get_market_data(['BTC/USDT'])
        if market_data:
            print("✅ OKX数据连接测试通过")
            print(f"📊 当前BTC价格: ${market_data['BTC/USDT']['price']}")
            return True
        else:
            print("❌ 无法获取市场数据")
            return False
            
    except Exception as e:
        print(f"❌ 数据连接测试失败: {e}")
        return False

def test_backtest_engine():
    """测试回测引擎"""
    print("🧪 测试回测引擎...")
    
    try:
        from real_backtest import RealBacktestEngine
        engine = RealBacktestEngine()
        
        # 快速测试一个策略
        results = engine.run_backtest('BTC/USDT', engine.strategy_macd_rsi_bollinger, days=1)
        
        if 'error' not in results:
            print("✅ 回测引擎测试通过")
            print(f"📈 测试结果: {results['total_return']:.2%} 收益")
            return True
        else:
            print(f"❌ 回测测试失败: {results['error']}")
            return False
            
    except Exception as e:
        print(f"❌ 回测引擎测试失败: {e}")
        return False

def main():
    """主部署流程"""
    print("🚀 开始Railway部署检查...")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # 执行检查步骤
    checks = [
        ("环境配置", check_environment),
        ("依赖安装", install_dependencies),
        ("数据连接", test_data_connection),
        ("回测引擎", test_backtest_engine)
    ]
    
    all_passed = True
    
    for check_name, check_func in checks:
        print(f"\n📋 执行检查: {check_name}")
        if not check_func():
            all_passed = False
            break
        print("-" * 30)
    
    print("=" * 50)
    
    if all_passed:
        print("🎉 所有检查通过！系统已准备就绪")
        print("\n📊 可用功能:")
        print("• 实时市场数据获取")
        print("• 多策略回测分析") 
        print("• Web界面可视化")
        print("• OKX交易所真实数据")
        
        print("\n🌐 启动Web服务...")
        # 启动Web服务
        from web_backtest import app
        app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
        
    else:
        print("❌ 部署检查失败，请检查上述错误信息")
        sys.exit(1)

if __name__ == "__main__":
    main()