# detectors/liquidity_purge.py
import pandas as pd
import numpy as np
from typing import Dict, Optional
from dataclasses import dataclass

@dataclass
class PurgeResult:
    type: str  # 'buy' or 'sell' or None
    level: float
    strength: float  # 0-1 confidence
    candles_since: int
    high_low_range: float

class LiquidityPurgeDetector:
    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self.min_range_pips = 10  # Minimum range to consider significant
        self.require_confirmation = True
        
    def detect(self, data: pd.DataFrame) -> Optional[Dict]:
        """
        Detect liquidity purges with multiple confirmation criteria
        """
        if len(data) < self.lookback + 5:
            return None
            
        # Get recent price action
        high = data['high'].values
        low = data['low'].values
        close = data['close'].values
        
        # Calculate swing points
        swing_highs = self._find_swing_highs(high)
        swing_lows = self._find_swing_lows(low)
        
        # Look for purge candidates
        recent_swing_high = max(high[-self.lookback:-1])
        recent_swing_low = min(low[-self.lookback:-1])
        
        current_high = high[-1]
        current_low = low[-1]
        current_close = close[-1]
        
        # Calculate pip size based on price level
        pip_size = self._get_pip_size(data['close'].iloc[-1])
        
        # Detect buy setup (sweep below recent low)
        if current_low < recent_swing_low - (pip_size * 0.5):
            # Check for reversal confirmation
            if current_close > recent_swing_low:
                strength = self._calculate_purge_strength(data, 'buy')
                
                return {
                    'type': 'buy',
                    'level': recent_swing_low,
                    'strength': strength,
                    'candles_since': self._candles_since_high(high, recent_swing_low),
                    'high_low_range': (current_high - current_low) / pip_size
                }
        
        # Detect sell setup (sweep above recent high)
        if current_high > recent_swing_high + (pip_size * 0.5):
            if current_close < recent_swing_high:
                strength = self._calculate_purge_strength(data, 'sell')
                
                return {
                    'type': 'sell',
                    'level': recent_swing_high,
                    'strength': strength,
                    'candles_since': self._candles_since_low(low, recent_swing_high),
                    'high_low_range': (current_high - current_low) / pip_size
                }
        
        return None
    
    def _find_swing_highs(self, high: np.ndarray) -> list:
        """Find significant swing highs"""
        swings = []
        for i in range(2, len(high) - 2):
            if high[i] > high[i-1] and high[i] > high[i-2] and \
               high[i] > high[i+1] and high[i] > high[i+2]:
                swings.append((i, high[i]))
        return swings
    
    def _find_swing_lows(self, low: np.ndarray) -> list:
        """Find significant swing lows"""
        swings = []
        for i in range(2, len(low) - 2):
            if low[i] < low[i-1] and low[i] < low[i-2] and \
               low[i] < low[i+1] and low[i] < low[i+2]:
                swings.append((i, low[i]))
        return swings
    
    def _calculate_purge_strength(self, data: pd.DataFrame, purge_type: str) -> float:
        """Calculate strength of purge (0-1)"""
        strength = 0.5  # Base strength
        
        # Check volume (if available)
        if 'volume' in data.columns:
            current_volume = data['volume'].iloc[-1]
            avg_volume = data['volume'].iloc[-20:].mean()
            if current_volume > avg_volume * 1.5:
                strength += 0.3
            elif current_volume > avg_volume:
                strength += 0.15
        
        # Check momentum
        close = data['close'].values
        if purge_type == 'buy':
            # Bullish momentum
            if close[-1] > close[-2] > close[-3]:
                strength += 0.2
        else:
            # Bearish momentum
            if close[-1] < close[-2] < close[-3]:
                strength += 0.2
        
        return min(strength, 1.0)
    
    def _get_pip_size(self, price: float) -> float:
        """Get pip size based on price level"""
        if price >= 1000:  # Indices, crypto
            return 0.1
        elif price >= 100:  # Crypto
            return 0.01
        elif price >= 10:  # Some crypto
            return 0.001
        else:
            return 0.0001  # Forex
    
    def _candles_since_high(self, high: np.ndarray, level: float) -> int:
        """Count candles since price was at this level"""
        for i in range(len(high)-1, -1, -1):
            if high[i] >= level:
                return len(high) - 1 - i
        return len(high)
    
    def _candles_since_low(self, low: np.ndarray, level: float) -> int:
        """Count candles since price was at this level"""
        for i in range(len(low)-1, -1, -1):
            if low[i] <= level:
                return len(low) - 1 - i
        return len(low)