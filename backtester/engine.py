# backtester/engine.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio
import logging
from ..detectors.liquidity_purge import LiquidityPurgeDetector
from ..detectors.cisd import CISDDetector
from ..detectors.fvg import FVGDetector
from ..data.fetcher import MarketDataFetcher

logger = logging.getLogger(__name__)

class Backtester:
    def __init__(self):
        self.detectors = {
            'liquidity': LiquidityPurgeDetector(lookback=20),
            'cisd': CISDDetector(lookback=5),
            'fvg': FVGDetector(min_gap=5, max_gap=50)
        }
        self.data_fetcher = MarketDataFetcher()
        self.results = []
    
    async def run_backtest(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        initial_balance: float = 10000
    ) -> Dict:
        """
        Run backtest on historical data
        """
        logger.info(f"Running backtest on {symbol} from {start_date} to {end_date}")
        
        # Fetch historical data
        # Need to fetch multiple timeframes
        timeframes = ['1m', '5m', '1h']
        data = {}
        
        for tf in timeframes:
            # For backtest, we need to fetch data in chunks
            df = await self._fetch_historical_data(symbol, tf, start_date, end_date)
            if df is not None:
                data[tf] = df
        
        if not data:
            logger.error("No data available for backtest")
            return {}
        
        # Run simulation
        trades = []
        balance = initial_balance
        positions = []
        
        # Iterate through each 1H candle
        for i in range(1, len(data['1h'])):
            # Get current slice
            current_data = {
                '1h': data['1h'].iloc[:i+1],
                '5m': data['5m'][data['5m'].index <= data['1h'].index[i]],
                '1m': data['1m'][data['1m'].index <= data['1h'].index[i]]
            }
            
            # Skip if not enough data
            if len(current_data['1h']) < 20 or len(current_data['5m']) < 5 or len(current_data['1m']) < 3:
                continue
            
            # Detect setup
            setup = await self._detect_setup(current_data)
            
            if setup:
                # Simulate trade
                trade = self._simulate_trade(
                    setup,
                    current_data,
                    data['1m'],
                    i
                )
                
                if trade:
                    trades.append(trade)
                    balance += trade['pnl']
        
        # Calculate metrics
        results = self._calculate_metrics(trades, initial_balance)
        
        logger.info(f"Backtest complete: {len(trades)} trades, ${balance:.2f} final balance")
        
        return results
    
    async def _fetch_historical_data(self, symbol: str, timeframe: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """Fetch historical data for backtest"""
        # Convert dates to datetime
        start_date = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(end.replace('Z', '+00:00'))
        
        # Calculate number of candles needed
        if 'm' in timeframe:
            minutes = int(timeframe.replace('m', ''))
            lookback = int((end_date - start_date).total_seconds() / (minutes * 60)) + 100
        else:
            hours = int(timeframe.replace('h', ''))
            lookback = int((end_date - start_date).total_seconds() / (hours * 3600)) + 100
        
        # For backtest, we need to fetch from start date
        # This would use the OANDA API with historical data support
        # For now, generate mock data
        return self.data_fetcher.generate_mock_data(symbol, timeframe, lookback)
    
    async def _detect_setup(self, data: Dict) -> Optional[Dict]:
        """Detect setup in current data slice"""
        # Check liquidity purge
        purge = self.detectors['liquidity'].detect(data['1h'])
        if not purge:
            return None
        
        # Check CISD
        if not self.detectors['cisd'].detect(data['5m'], purge['type']):
            return None
        
        # Check FVG
        fvg = self.detectors['fvg'].detect(data['1m'], purge['type'])
        if not fvg:
            return None
        
        return {
            'type': 'BUY' if purge['type'] == 'buy' else 'SELL',
            'entry': (fvg['fvg_low'] + fvg['fvg_high']) / 2,
            'stop_loss': self._calculate_stop(purge, fvg),
            'take_profit': self._calculate_target(purge, fvg),
            'fvg': fvg,
            'purge': purge
        }
    
    def _simulate_trade(self, setup: Dict, current_data: Dict, full_data: pd.DataFrame, idx: int) -> Optional[Dict]:
        """Simulate a trade from setup"""
        # Determine trade direction
        is_long = setup['type'] == 'BUY'
        
        # Simulate entry
        entry_price = setup['entry']
        stop_loss = setup['stop_loss']
        take_profit = setup['take_profit']
        
        # Risk per trade
        risk = abs(entry_price - stop_loss)
        position_size = 1000  # Simplified
        
        # Check if trade would be triggered
        if is_long:
            # Entry price must be above current price?
            # For simplicity, assume market order at next candle open
            next_candle = full_data.iloc[idx + 1] if idx + 1 < len(full_data) else None
            if next_candle is None:
                return None
            
            # Check if trade hits stop or target
            exit_price = None
            exit_reason = None
            high = next_candle['high']
            low = next_candle['low']
            close = next_candle['close']
            
            # Check if take profit or stop loss hit
            if is_long:
                if high >= take_profit:
                    exit_price = take_profit
                    exit_reason = 'take_profit'
                elif low <= stop_loss:
                    exit_price = stop_loss
                    exit_reason = 'stop_loss'
                else:
                    exit_price = close
                    exit_reason = 'close'
            else:
                if low <= take_profit:
                    exit_price = take_profit
                    exit_reason = 'take_profit'
                elif high >= stop_loss:
                    exit_price = stop_loss
                    exit_reason = 'stop_loss'
                else:
                    exit_price = close
                    exit_reason = 'close'
            
            # Calculate PnL
            if is_long:
                pnl = (exit_price - entry_price) / abs(entry_price - stop_loss) * risk * position_size
            else:
                pnl = (entry_price - exit_price) / abs(entry_price - stop_loss) * risk * position_size
            
            return {
                'entry_time': current_data['1h'].index[-1],
                'exit_time': next_candle.name,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'position_size': position_size,
                'pnl': pnl,
                'result': exit_reason,
                'pips': abs(exit_price - entry_price) / 0.0001
            }
        
        return None
    
    def _calculate_stop(self, purge: Dict, fvg: Dict) -> float:
        """Calculate stop loss"""
        if purge['type'] == 'buy':
            return fvg['fvg_low'] - (fvg['fvg_high'] - fvg['fvg_low']) * 0.5
        else:
            return fvg['fvg_high'] + (fvg['fvg_high'] - fvg['fvg_low']) * 0.5
    
    def _calculate_target(self, purge: Dict, fvg: Dict) -> float:
        """Calculate take profit"""
        entry = (fvg['fvg_low'] + fvg['fvg_high']) / 2
        stop = self._calculate_stop(purge, fvg)
        risk = abs(entry - stop)
        
        if purge['type'] == 'buy':
            return entry + risk * 2
        else:
            return entry - risk * 2
    
    def _calculate_metrics(self, trades: List[Dict], initial_balance: float) -> Dict:
        """Calculate backtest metrics"""
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0
            }
        
        total_trades = len(trades)
        wins = sum(1 for t in trades if t['result'] == 'take_profit')
        losses = sum(1 for t in trades if t['result'] == 'stop_loss')
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        
        total_pnl = sum(t['pnl'] for t in trades)
        
        # Calculate drawdown
        running_balance = initial_balance
        peak = initial_balance
        drawdowns = []
        
        for trade in trades:
            running_balance += trade['pnl']
            if running_balance > peak:
                peak = running_balance
            drawdown = (peak - running_balance) / peak * 100
            drawdowns.append(drawdown)
        
        max_drawdown = max(drawdowns) if drawdowns else 0
        
        # Calculate Sharpe ratio (simplified)
        returns = [t['pnl'] / initial_balance for t in trades]
        if returns:
            avg_return = np.mean(returns)
            std_return = np.std(returns) if len(returns) > 1 else 0.01
            sharpe_ratio = (avg_return / std_return) * np.sqrt(252) if std_return > 0 else 0
        else:
            sharpe_ratio = 0
        
        return {
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'avg_profit': round(total_pnl / total_trades, 2) if total_trades > 0 else 0,
            'max_drawdown': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'final_balance': round(initial_balance + total_pnl, 2)
        }