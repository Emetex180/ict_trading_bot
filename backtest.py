# backtest.py
import asyncio
import pandas as pd
from datetime import datetime, timedelta
import sys
import os
import webbrowser

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.fetcher import MarketDataFetcher
from backtester.engine import Backtester
from utils.logger import setup_logger

logger = setup_logger(__name__)

async def run_backtest():
    """Run a backtest on historical data with visual output"""
    
    print("\n" + "="*60)
    print("📊 ICT STRATEGY BACKTEST - VISUAL OUTPUT")
    print("="*60 + "\n")
    
    # Initialize components
    fetcher = MarketDataFetcher()
    backtester = Backtester()
    
    # Choose symbol to backtest
    symbol = input("Enter symbol to backtest (default: EURUSD): ").strip() or "EURUSD"
    
    # Choose date range
    days = input("Enter number of days to backtest (default: 30): ").strip()
    days = int(days) if days else 30
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    print(f"\n📊 Backtesting: {symbol}")
    print(f"📅 Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print("⏳ Fetching historical data...\n")
    
    try:
        # Fetch historical data
        data_1h = await fetcher.fetch_data(symbol, '1h', lookback=days * 24)
        data_5m = await fetcher.fetch_data(symbol, '5m', lookback=days * 24 * 12)
        data_1m = await fetcher.fetch_data(symbol, '1m', lookback=days * 24 * 60)
        
        if data_1h is None or data_5m is None or data_1m is None:
            print("❌ Failed to fetch data for all timeframes")
            return
        
        print(f"✅ Data fetched:")
        print(f"   - 1H: {len(data_1h)} candles")
        print(f"   - 5M: {len(data_5m)} candles")
        print(f"   - 1M: {len(data_1m)} candles")
        
        # Run backtest
        print("\n🔄 Running backtest...")
        results = backtester.run_backtest(
            symbol=symbol,
            data_1h=data_1h,
            data_5m=data_5m,
            data_1m=data_1m,
            initial_balance=10000
        )
        
        # Print results
        print("\n" + "="*60)
        print("📊 BACKTEST RESULTS")
        print("="*60)
        print(f"Symbol:        {results['symbol']}")
        print(f"Total Setups:  {results.get('setups', 0)}")
        print(f"Total Trades:  {results['total_trades']}")
        print(f"Wins:          {results['wins']}")
        print(f"Losses:        {results['losses']}")
        print(f"Win Rate:      {results['win_rate']}%")
        print(f"Total P/L:     ${results['total_pnl']:.2f}")
        print(f"Avg Profit:    ${results['avg_profit']:.2f}")
        print(f"Avg Pips:      {results['avg_pips']:.2f}")
        print(f"Max Drawdown:  {results['max_drawdown']}%")
        print(f"Sharpe Ratio:  {results['sharpe_ratio']}")
        print(f"Final Balance: ${results['final_balance']:.2f}")
        print("="*60)
        
        # Save results
        save_results(results)
        
        # Open visualizations
        print("\n📊 Visualizations created:")
        print(f"   - Equity Curve: backtest_results/{symbol}_equity_curve.html")
        print(f"   - Trade Distribution: backtest_results/{symbol}_trade_distribution.html")
        print(f"   - Performance Dashboard: backtest_results/{symbol}_performance_dashboard.html")
        print(f"   - Trade Map: backtest_results/{symbol}_trade_map.html")
        
        # Ask to open in browser
        open_browser = input("\n🌐 Open visualizations in browser? (y/n): ").strip().lower()
        if open_browser == 'y':
            open_visualizations(symbol)
        
    except Exception as e:
        print(f"❌ Error during backtest: {e}")
        logger.error(f"Backtest error: {e}")

def save_results(results: dict):
    """Save backtest results to CSV and JSON"""
    try:
        os.makedirs('backtest_results', exist_ok=True)
        
        # Save CSV
        filename = f"backtest_results/backtest_{results['symbol']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        pd.DataFrame([results]).to_csv(f"{filename}.csv", index=False)
        
        # Save summary text
        with open(f"{filename}.txt", 'w') as f:
            for key, value in results.items():
                f.write(f"{key}: {value}\n")
        
        print(f"\n📁 Results saved to: {filename}.csv and {filename}.txt")
        
    except Exception as e:
        print(f"Error saving results: {e}")

def open_visualizations(symbol: str):
    """Open visualizations in browser"""
    try:
        files = [
            f'backtest_results/{symbol}_equity_curve.html',
            f'backtest_results/{symbol}_trade_distribution.html',
            f'backtest_results/{symbol}_performance_dashboard.html',
            f'backtest_results/{symbol}_trade_map.html'
        ]
        
        for file in files:
            if os.path.exists(file):
                webbrowser.open(file)
                print(f"📂 Opened: {file}")
        
    except Exception as e:
        print(f"Error opening visualizations: {e}")

if __name__ == "__main__":
    asyncio.run(run_backtest())