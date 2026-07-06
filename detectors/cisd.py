# detectors/cisd.py
import pandas as pd
import numpy as np
from typing import Dict, Optional

class CISDDetector:
    """
    Change in State of Delivery (CISD)
    Detects structural breaks in price delivery
    """
    
    def __init__(self, lookback: int = 5, min_strength: float = 0.4):  # Reduced min_strength
        self.lookback = lookback
        self.min_strength = min_strength
        
    def detect(self, data: pd.DataFrame, purge_type: str) -> bool:
        """
        Detect CISD with confirmation criteria
        
        Args:
            data: OHLCV data
            purge_type: 'buy' or 'sell'
        
        Returns:
            bool: True if CISD confirmed
        """
        if len(data) < self.lookback + 3:
            return False
        
        # Extract data
        high = data['high'].values[-self.lookback-2:]
        low = data['low'].values[-self.lookback-2:]
        close = data['close'].values[-self.lookback-2:]
        
        # Calculate swing points
        swing_highs = self._find_swing_highs(high)
        swing_lows = self._find_swing_lows(low)
        
        if purge_type == 'buy':
            return self._detect_bullish_cisd(high, low, close, swing_highs, swing_lows)
        else:
            return self._detect_bearish_cisd(high, low, close, swing_highs, swing_lows)
    
    def _detect_bullish_cisd(self, high, low, close, swing_highs, swing_lows) -> bool:
        """
        Bullish CISD: Price creates a new lower low, then breaks above previous swing high
        """
        # Need at least 1 swing point for basic detection
        if len(swing_lows) < 1:
            return False
        
        # Get recent swing low
        recent_swing_low = swing_lows[-1][1] if swing_lows else None
        
        if not recent_swing_low:
            return False
        
        # Check conditions (relaxed)
        conditions_met = 0
        total_conditions = 3
        
        # 1. Lower low created (relaxed - allow small wicks)
        if low[-1] < recent_swing_low * 0.999:  # 0.1% below
            conditions_met += 1
        
        # 2. Close above recent swing low (reversal)
        if close[-1] > recent_swing_low:
            conditions_met += 1
        
        # 3. Momentum shift (closing price rises)
        if len(close) >= 3:
            if close[-1] > close[-2]:  # Just one candle of momentum
                conditions_met += 1
        
        # Need at least 2 of 3 conditions
        return conditions_met >= 2
    
    def _detect_bearish_cisd(self, high, low, close, swing_highs, swing_lows) -> bool:
        """
        Bearish CISD: Price creates a new higher high, then breaks below previous swing low
        """
        if len(swing_highs) < 1:
            return False
        
        recent_swing_high = swing_highs[-1][1] if swing_highs else None
        
        if not recent_swing_high:
            return False
        
        conditions_met = 0
        total_conditions = 3
        
        # 1. Higher high created (relaxed)
        if high[-1] > recent_swing_high * 1.001:  # 0.1% above
            conditions_met += 1
        
        # 2. Close below recent swing high (reversal)
        if close[-1] < recent_swing_high:
            conditions_met += 1
        
        # 3. Momentum shift (closing price falls)
        if len(close) >= 3:
            if close[-1] < close[-2]:  # Just one candle of momentum
                conditions_met += 1
        
        return conditions_met >= 2
    
    def _find_swing_highs(self, data: np.ndarray) -> list:
        """Find swing highs with min distance"""
        swings = []
        min_distance = 1  # Reduced from 2 to be more sensitive
        
        for i in range(min_distance, len(data) - min_distance):
            is_swing = True
            for j in range(1, min_distance + 1):
                if data[i] <= data[i-j] or data[i] <= data[i+j]:
                    is_swing = False
                    break
            if is_swing:
                swings.append((i, data[i]))
        
        # Filter to recent swings
        return swings[-5:] if len(swings) > 5 else swings
    
    def _find_swing_lows(self, data: np.ndarray) -> list:
        """Find swing lows with min distance"""
        swings = []
        min_distance = 1  # Reduced from 2 to be more sensitive
        
        for i in range(min_distance, len(data) - min_distance):
            is_swing = True
            for j in range(1, min_distance + 1):
                if data[i] >= data[i-j] or data[i] >= data[i+j]:
                    is_swing = False
                    break
            if is_swing:
                swings.append((i, data[i]))
        
        return swings[-5:] if len(swings) > 5 else swings
    
    def detect_advanced(self, data: pd.DataFrame, purge_type: str) -> Dict:
        """
        Advanced CISD detection with detailed analysis
        """
        result = {
            'is_valid': False,
            'strength': 0.0,
            'swing_points': {},
            'details': {}
        }
        
        if len(data) < self.lookback + 3:
            return result
        
        # Detect basic CISD
        is_valid = self.detect(data, purge_type)
        
        if not is_valid:
            return result
        
        # Calculate strength
        strength = 0.5
        
        # Additional confirmation criteria
        close = data['close'].values[-10:]
        
        # Momentum (simplified)
        if purge_type == 'buy':
            # Check if price is moving up
            if len(close) >= 2 and close[-1] > close[-2]:
                strength += 0.2
        else:
            # Check if price is moving down
            if len(close) >= 2 and close[-1] < close[-2]:
                strength += 0.2
        
        # Volume confirmation (if available)
        if 'volume' in data.columns:
            try:
                avg_volume = data['volume'].iloc[-20:].mean()
                if avg_volume > 0 and data['volume'].iloc[-1] > avg_volume * 1.1:
                    strength += 0.2
            except:
                pass
        
        result['is_valid'] = True
        result['strength'] = min(strength, 1.0)
        result['details']['purge_type'] = purge_type
        result['details']['candles_analyzed'] = len(data)
        
        return result