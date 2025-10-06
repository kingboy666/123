from flask import Flask, render_template, request, jsonify
import pandas as pd
from datetime import datetime
from real_backtest import RealBacktestEngine
from data_fetcher import OKXDataFetcher
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# 全局变量存储回测结果
backtest_results = {}
market_data = {}

def update_market_data():
    """定时更新市场数据"""
    global market_data
    fetcher = OKXDataFetcher()
    
    while True:
        try:
            market_data = fetcher.get_market_data()
            time.sleep(60)  # 每分钟更新一次
        except Exception as e:
            print(f"更新市场数据失败: {e}")
            time.sleep(30)

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html', market_data=market_data)

@app.route('/api/backtest', methods=['POST'])
def run_backtest():
    """运行回测API"""
    try:
        data = request.json
        symbols = data.get('symbols', ['BTC/USDT', 'ETH/USDT', 'AVAX/USDT'])
        days = data.get('days', 30)
        timeframe = data.get('timeframe', '1h')
        
        engine = RealBacktestEngine()
        results = engine.run_all_strategies(symbols)
        
        # 存储结果
        backtest_results['last_run'] = {
            'timestamp': datetime.now().isoformat(),
            'results': results
        }
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/market/data')
def get_market_data():
    """获取市场数据API"""
    return jsonify(market_data)

@app.route('/api/available/symbols')
def get_available_symbols():
    """获取可交易品种"""
    fetcher = OKXDataFetcher()
    symbols = fetcher.get_available_symbols()
    return jsonify(symbols)

@app.route('/api/historical/data')
def get_historical_data():
    """获取历史数据API"""
    try:
        symbol = request.args.get('symbol', 'BTC/USDT')
        days = int(request.args.get('days', 30))
        timeframe = request.args.get('timeframe', '1h')
        
        fetcher = OKXDataFetcher()
        data = fetcher.get_historical_data(symbol, timeframe, days)
        
        if data is not None:
            return jsonify({
                'success': True,
                'data': data.reset_index().to_dict('records')
            })
        else:
            return jsonify({
                'success': False,
                'error': '无法获取数据'
            })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

if __name__ == '__main__':
    # 启动市场数据更新线程
    market_thread = threading.Thread(target=update_market_data, daemon=True)
    market_thread.start()
    
    print("Web回测系统启动中...")
    print("访问 http://localhost:5000 查看回测界面")
    
    app.run(host='0.0.0.0', port=5000, debug=True)