# backtester/engine.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

from detectors.liquidity_purge import LiquidityPurgeDetector
from detectors.cisd import CISDDetector
from detectors.fvg import FVGDetector

logger = logging.getLogger(__name__)

class Backtester:
    def __init__(self):
        self.liquidity_detector = LiquidityPurgeDetector(lookback=20)
        self.cisd_detector = CISDDetector(lookback=5)
        self.fvg_detector = FVGDetector(min_gap=3, max_gap=100)  # Made more sensitive
        self.results = []
        self.trades = []
        self.setups = []
        self.debug_info = []
    
    def run_backtest(self, symbol: str, data_1h: pd.DataFrame, 
                     data_5m: pd.DataFrame, data_1m: pd.DataFrame,
                     initial_balance: float = 10000) -> Dict:
        """
        Run backtest on historical data
        """
        logger.info(f"Running backtest on {symbol}")
        
        self.trades = []
        self.setups = []
        self.debug_info = []
        balance = initial_balance
        
        # Print data info for debugging
        logger.info(f"Data shapes - 1H: {len(data_1h)}, 5M: {len(data_5m)}, 1M: {len(data_1m)}")
        
        # Iterate through each 1H candle (with lookback)
        for i in range(20, len(data_1h)):
            try:
                current_1h = data_1h.iloc[:i+1]
                current_time = data_1h.index[i]
                
                # Get corresponding 5M and 1M data
                current_5m = data_5m[data_5m.index <= current_time]
                current_1m = data_1m[data_1m.index <= current_time]
                
                if len(current_5m) < 5 or len(current_1m) < 3:
                    continue
                
                # Detect setup
                setup = self._detect_setup(current_1h, current_5m, current_1m, current_time)
                
                if setup:
                    self.setups.append(setup)
                    
                    # Simulate trade
                    trade = self._simulate_trade(
                        setup, 
                        data_1m, 
                        i,
                        current_time
                    )
                    
                    if trade:
                        self.trades.append(trade)
                        balance += trade['pnl']
                        
                        # Log each trade for debugging
                        logger.info(f"📊 Trade {len(self.trades)}: {setup['type']} at {trade['entry_price']:.5f} -> {trade['exit_price']:.5f} | PnL: ${trade['pnl']:.2f}")
                        
            except Exception as e:
                logger.error(f"Error in backtest iteration {i}: {e}")
                continue
        
        # Calculate metrics
        results = self._calculate_metrics(self.trades, initial_balance, symbol)
        results['setups'] = len(self.setups)
        results['total_candles'] = len(data_1h)
        
        # Log summary
        logger.info(f"✅ Backtest complete: {len(self.setups)} setups, {len(self.trades)} trades")
        
        # Generate visualizations
        self._generate_visualizations(symbol, data_1h, data_1m)
        
        return results
    
    def _detect_setup(self, data_1h, data_5m, data_1m, current_time) -> Optional[Dict]:
        """Detect a setup in the current data slice with debugging"""
        try:
            # Step 1: Detect Liquidity Purge
            purge = self.liquidity_detector.detect(data_1h)
            if not purge or not purge.get('type'):
                return None
            
            purge_type = purge['type']
            
            # Step 2: Check CISD
            if not self.cisd_detector.detect(data_5m, purge_type):
                return None
            
            # Step 3: Check FVG
            fvg = self.fvg_detector.detect(data_1m, purge_type)
            if not fvg:
                return None
            
            # Calculate entry and risk levels
            entry = (fvg['fvg_low'] + fvg['fvg_high']) / 2
            
            if purge_type == 'buy':
                stop_loss = fvg['fvg_low'] - (fvg['fvg_high'] - fvg['fvg_low']) * 0.5
                take_profit = entry + (entry - stop_loss) * 2
            else:
                stop_loss = fvg['fvg_high'] + (fvg['fvg_high'] - fvg['fvg_low']) * 0.5
                take_profit = entry - (stop_loss - entry) * 2
            
            return {
                'type': 'BUY' if purge_type == 'buy' else 'SELL',
                'entry': entry,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'fvg': fvg,
                'purge': purge,
                'timestamp': current_time,
                'gap_pips': fvg.get('gap_pips', 0)
            }
            
        except Exception as e:
            logger.error(f"Error detecting setup: {e}")
            return None
    
    def _simulate_trade(self, setup: Dict, full_data: pd.DataFrame, 
                        idx: int, entry_time: datetime) -> Optional[Dict]:
        """Simulate a trade from setup"""
        try:
            is_long = setup['type'] == 'BUY'
            entry_price = setup['entry']
            stop_loss = setup['stop_loss']
            take_profit = setup['take_profit']
            
            risk = abs(entry_price - stop_loss)
            position_size = 1000  # Fixed position size
            
            # Look for exit in subsequent candles (up to 50 candles)
            future_data = full_data.iloc[idx+1:idx+100]
            
            if len(future_data) == 0:
                return None
            
            exit_price = None
            exit_reason = None
            
            for _, candle in future_data.iterrows():
                high = candle['high']
                low = candle['low']
                close = candle['close']
                
                if is_long:
                    if high >= take_profit:
                        exit_price = take_profit
                        exit_reason = 'take_profit'
                        break
                    elif low <= stop_loss:
                        exit_price = stop_loss
                        exit_reason = 'stop_loss'
                        break
                else:
                    if low <= take_profit:
                        exit_price = take_profit
                        exit_reason = 'take_profit'
                        break
                    elif high >= stop_loss:
                        exit_price = stop_loss
                        exit_reason = 'stop_loss'
                        break
            
            # If no exit found, use the last close
            if exit_price is None:
                exit_price = future_data.iloc[-1]['close']
                exit_reason = 'timeout'
            
            # Calculate PnL
            if is_long:
                pnl = (exit_price - entry_price) / risk * position_size
            else:
                pnl = (entry_price - exit_price) / risk * position_size
            
            # Calculate pips
            pip_size = 0.0001
            pips = abs(exit_price - entry_price) / pip_size
            
            return {
                'entry_time': entry_time,
                'exit_time': future_data.index[-1],
                'entry_price': entry_price,
                'exit_price': exit_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'position_size': position_size,
                'pnl': pnl,
                'result': exit_reason,
                'pips': pips,
                'type': setup['type'],
                'gap_pips': setup.get('gap_pips', 0)
            }
            
        except Exception as e:
            logger.error(f"Error simulating trade: {e}")
            return None
    
    def _calculate_metrics(self, trades: List[Dict], initial_balance: float, symbol: str) -> Dict:
        """Calculate backtest metrics"""
        if not trades:
            return {
                'symbol': symbol,
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_profit': 0,
                'avg_pips': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'final_balance': initial_balance,
                'setups': 0,
                'total_setups': 0,
                'total_candles': 0
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
            drawdown = (peak - running_balance) / peak * 100 if peak > 0 else 0
            drawdowns.append(drawdown)
        
        max_drawdown = max(drawdowns) if drawdowns else 0
        
        # Calculate Sharpe ratio
        returns = [t['pnl'] / initial_balance for t in trades]
        if returns and len(returns) > 1:
            avg_return = np.mean(returns)
            std_return = np.std(returns) if len(returns) > 1 else 0.01
            sharpe_ratio = (avg_return / std_return) * np.sqrt(252) if std_return > 0 else 0
        else:
            sharpe_ratio = 0
        
        avg_pips = np.mean([t['pips'] for t in trades]) if trades else 0
        
        return {
            'symbol': symbol,
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'avg_profit': round(total_pnl / total_trades, 2) if total_trades > 0 else 0,
            'avg_pips': round(avg_pips, 2),
            'max_drawdown': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'final_balance': round(initial_balance + total_pnl, 2),
            'setups': len(self.setups),
            'total_setups': len(self.setups),
            'total_candles': 0
        }
    
    def _generate_visualizations(self, symbol: str, data_1h: pd.DataFrame, data_1m: pd.DataFrame):
        """Generate visual charts for the backtest"""
        try:
            # Create results directory
            os.makedirs('backtest_results', exist_ok=True)
            
            # Only create visualizations if there are trades
            if len(self.trades) > 0:
                # 1. Equity Curve
                self._create_equity_curve(symbol)
                
                # 2. Trade Distribution
                self._create_trade_distribution(symbol)
                
                # 3. Performance Summary Dashboard
                self._create_performance_dashboard(symbol)
                
                # 4. Trade Map
                self._create_trade_map(symbol, data_1h, data_1m)
            else:
                logger.warning(f"No trades to visualize for {symbol}")
                # Create a simple "no trades" report
                self._create_no_trades_report(symbol)
            
            logger.info(f"Visualizations saved to backtest_results/")
            
        except Exception as e:
            logger.error(f"Error generating visualizations: {e}")
    
    def _create_no_trades_report(self, symbol: str):
        """Create a report when no trades are found"""
        try:
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>No Trades Found - {symbol}</title>
                <style>
                    body {{ font-family: Arial; background: #0a0a0f; color: #e0e0e0; padding: 40px; }}
                    .container {{ max-width: 800px; margin: 0 auto; }}
                    .warning {{ background: #1a1a2e; padding: 30px; border-radius: 10px; border-left: 4px solid #ffaa00; }}
                    h1 {{ color: #ffaa00; }}
                    .info {{ background: #14141f; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="warning">
                        <h1>⚠️ No Trades Found</h1>
                        <p>Backtest on {symbol} found 0 trades.</p>
                        <p>This could mean:</p>
                        <ul>
                            <li>The strategy conditions are too strict</li>
                            <li>The data might be mock data (check MT5 connection)</li>
                            <li>Not enough historical data</li>
                            <li>The detectors need adjustment</li>
                        </ul>
                    </div>
                    <div class="info">
                        <h3>📊 Debug Information</h3>
                        <p>Setups found: {len(self.setups)}</p>
                        <p>Trades executed: {len(self.trades)}</p>
                        <p>Data shape: {len(data_1h) if hasattr(self, 'data_1h') else 'N/A'}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            with open(f'backtest_results/{symbol}_no_trades_report.html', 'w') as f:
                f.write(html_content)
                
        except Exception as e:
            logger.error(f"Error creating no trades report: {e}")
    
    def _create_equity_curve(self, symbol: str):
        """Create equity curve chart"""
        try:
            if not self.trades:
                return
            
            # Calculate cumulative PnL
            cumulative = []
            running = 10000
            for trade in self.trades:
                running += trade['pnl']
                cumulative.append(running)
            
            fig = go.Figure()
            
            # Equity curve
            fig.add_trace(go.Scatter(
                x=[t['entry_time'] for t in self.trades],
                y=cumulative,
                mode='lines+markers',
                name='Equity',
                line=dict(color='#00d4ff', width=2),
                marker=dict(size=6, color='#00d4ff')
            ))
            
            # Add horizontal line at initial balance
            fig.add_hline(y=10000, line_dash="dash", line_color="gray", 
                         annotation_text="Initial Balance")
            
            fig.update_layout(
                title=f'{symbol} - Equity Curve ({len(self.trades)} trades)',
                xaxis_title='Date',
                yaxis_title='Balance ($)',
                template='plotly_dark',
                height=400,
                hovermode='x unified'
            )
            
            fig.write_html(f'backtest_results/{symbol}_equity_curve.html')
            
        except Exception as e:
            logger.error(f"Error creating equity curve: {e}")
    
    def _create_trade_distribution(self, symbol: str):
        """Create trade distribution charts"""
        try:
            if not self.trades:
                return
            
            # Prepare data
            pnls = [t['pnl'] for t in self.trades]
            results = [t['result'] for t in self.trades]
            
            fig = make_subplots(rows=1, cols=2, 
                               subplot_titles=('PnL Distribution', 'Trade Results'))
            
            # PnL histogram
            fig.add_trace(
                go.Histogram(x=pnls, nbinsx=20, name='PnL', 
                            marker_color='#00d4ff'),
                row=1, col=1
            )
            
            # Results pie chart
            win_count = sum(1 for r in results if r == 'take_profit')
            loss_count = sum(1 for r in results if r == 'stop_loss')
            
            fig.add_trace(
                go.Pie(labels=['Wins', 'Losses'], 
                       values=[win_count, loss_count],
                       marker_colors=['#00ff88', '#ff4444']),
                row=1, col=2
            )
            
            fig.update_layout(
                title=f'{symbol} - Trade Distribution ({len(self.trades)} trades)',
                template='plotly_dark',
                height=400
            )
            
            fig.write_html(f'backtest_results/{symbol}_trade_distribution.html')
            
        except Exception as e:
            logger.error(f"Error creating trade distribution: {e}")
    
    def _create_performance_dashboard(self, symbol: str):
        """Create performance summary dashboard"""
        try:
            if not self.trades:
                return
            
            # Calculate metrics
            wins = sum(1 for t in self.trades if t['result'] == 'take_profit')
            losses = sum(1 for t in self.trades if t['result'] == 'stop_loss')
            total_pnl = sum(t['pnl'] for t in self.trades)
            
            fig = make_subplots(rows=2, cols=3,
                               subplot_titles=(
                                   'Win Rate', 'Total PnL', 'Avg Trade',
                                   'Wins vs Losses', 'Profit Factor', 'Max Drawdown'
                               ))
            
            # Win rate gauge
            win_rate = (wins / len(self.trades) * 100) if self.trades else 0
            fig.add_trace(
                go.Indicator(
                    mode="gauge+number",
                    value=win_rate,
                    title={'text': "Win Rate %"},
                    gauge={'axis': {'range': [0, 100]},
                          'bar': {'color': "#00d4ff"}},
                    domain={'row': 0, 'column': 0}
                ),
                row=1, col=1
            )
            
            # Total PnL
            fig.add_trace(
                go.Indicator(
                    mode="number",
                    value=total_pnl,
                    title={'text': "Total PnL ($)"},
                    number={'prefix': "$"},
                    domain={'row': 0, 'column': 1}
                ),
                row=1, col=2
            )
            
            # Avg Trade
            avg_trade = total_pnl / len(self.trades) if self.trades else 0
            fig.add_trace(
                go.Indicator(
                    mode="number",
                    value=avg_trade,
                    title={'text': "Avg Trade ($)"},
                    number={'prefix': "$"},
                    domain={'row': 0, 'column': 2}
                ),
                row=1, col=3
            )
            
            # Wins vs Losses bar chart
            fig.add_trace(
                go.Bar(x=['Wins', 'Losses'], y=[wins, losses],
                      marker_color=['#00ff88', '#ff4444']),
                row=2, col=1
            )
            
            # Profit Factor
            total_wins = sum(t['pnl'] for t in self.trades if t['pnl'] > 0)
            total_losses = abs(sum(t['pnl'] for t in self.trades if t['pnl'] < 0))
            profit_factor = total_wins / total_losses if total_losses > 0 else 0
            
            fig.add_trace(
                go.Indicator(
                    mode="number",
                    value=profit_factor,
                    title={'text': "Profit Factor"},
                    number={'valueformat': '.2f'},
                    domain={'row': 1, 'column': 2}
                ),
                row=2, col=2
            )
            
            # Max Drawdown
            running = 10000
            peak = 10000
            max_dd = 0
            for trade in self.trades:
                running += trade['pnl']
                if running > peak:
                    peak = running
                dd = (peak - running) / peak * 100
                if dd > max_dd:
                    max_dd = dd
            
            fig.add_trace(
                go.Indicator(
                    mode="number",
                    value=max_dd,
                    title={'text': "Max Drawdown %"},
                    number={'suffix': "%", 'valueformat': '.1f'},
                    domain={'row': 1, 'column': 3}
                ),
                row=2, col=3
            )
            
            fig.update_layout(
                title=f'{symbol} - Performance Dashboard ({len(self.trades)} trades)',
                template='plotly_dark',
                height=600
            )
            
            fig.write_html(f'backtest_results/{symbol}_performance_dashboard.html')
            
        except Exception as e:
            logger.error(f"Error creating performance dashboard: {e}")
    
    def _create_trade_map(self, symbol: str, data_1h: pd.DataFrame, data_1m: pd.DataFrame):
        """Create a price chart with trade entries and exits"""
        try:
            if not self.trades:
                return
            
            # Use 1H data for the price chart
            price_data = data_1h.tail(200)  # Last 200 candles
            
            fig = go.Figure()
            
            # Candlestick chart
            fig.add_trace(go.Candlestick(
                x=price_data.index,
                open=price_data['open'],
                high=price_data['high'],
                low=price_data['low'],
                close=price_data['close'],
                name='Price',
                increasing_line_color='#00ff88',
                decreasing_line_color='#ff4444'
            ))
            
            # Add trade entries and exits
            for trade in self.trades[:20]:  # Show last 20 trades
                # Entry marker
                entry_color = '#00ff88' if trade['type'] == 'BUY' else '#ff4444'
                entry_symbol = 'triangle-up' if trade['type'] == 'BUY' else 'triangle-down'
                
                fig.add_trace(go.Scatter(
                    x=[trade['entry_time']],
                    y=[trade['entry_price']],
                    mode='markers',
                    marker=dict(
                        symbol=entry_symbol,
                        size=12,
                        color=entry_color,
                        line=dict(width=1, color='white')
                    ),
                    name=f"Entry {trade['type']}",
                    showlegend=False,
                    text=f"Entry: ${trade['entry_price']:.5f}",
                    hoverinfo='text'
                ))
                
                # Exit marker
                exit_color = '#00ff88' if trade['result'] == 'take_profit' else '#ff4444'
                fig.add_trace(go.Scatter(
                    x=[trade['exit_time']],
                    y=[trade['exit_price']],
                    mode='markers',
                    marker=dict(
                        symbol='circle',
                        size=10,
                        color=exit_color,
                        line=dict(width=1, color='white')
                    ),
                    name=f"Exit {trade['result']}",
                    showlegend=False,
                    text=f"Exit: ${trade['exit_price']:.5f}<br>PnL: ${trade['pnl']:.2f}",
                    hoverinfo='text'
                ))
            
            fig.update_layout(
                title=f'{symbol} - Trade Map ({len(self.trades)} trades)',
                xaxis_title='Date',
                yaxis_title='Price',
                template='plotly_dark',
                height=600,
                hovermode='x unified'
            )
            
            fig.write_html(f'backtest_results/{symbol}_trade_map.html')
            
        except Exception as e:
            logger.error(f"Error creating trade map: {e}")