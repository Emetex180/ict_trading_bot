# detectors/fvg.py
import pandas as pd
import numpy as np
from typing import Dict, Optional, List

class FVGDetector:
    """
    Fair Value Gap (FVG) Detector
    Detects unfulfilled price gaps
    """
    
    def __init__(self, min_gap: float = 5, max_gap: float = 50):
        self.min_gap_pips = min_gap
        self.max_gap_pips = max_gap
        
    def detect(self, data: pd.DataFrame, purge_type: str) -> Optional[Dict]:
        """
        Detect valid FVG with confirmation
        
        Args:
            data: OHLCV data (1M or smaller timeframe)
            purge_type: 'buy' or 'sell'
        
        Returns:
            Dict with FVG details or None
        """
        if len(data) < 5:
            return None
        
        # Get pip size
        pip_size = self._get_pip_size(data['close'].iloc[-1])
        
        # Scan for FVGs
        fvgs = []
        for i in range(1, len(data) - 1):
            prev = data.iloc[i-1]
            curr = data.iloc[i]
            next_ = data.iloc[i+1]
            
            # Bullish FVG: Gap up
            if purge_type == 'buy':
                if prev['high'] < curr['low']:
                    gap_pips = (curr['low'] - prev['high']) / pip_size
                    if self.min_gap_pips <= gap_pips <= self.max_gap_pips:
                        fvgs.append({
                            'type': 'bullish',
                            'fvg_low': prev['high'],
                            'fvg_high': curr['low'],
                            'gap_pips': gap_pips,
                            'strength': self._calculate_fvg_strength(data, i, 'bullish'),
                            'index': i
                        })
            
            # Bearish FVG: Gap down
            elif purge_type == 'sell':
                if prev['low'] > curr['high']:
                    gap_pips = (prev['low'] - curr['high']) / pip_size
                    if self.min_gap_pips <= gap_pips <= self.max_gap_pips:
                        fvgs.append({
                            'type': 'bearish',
                            'fvg_low': curr['high'],
                            'fvg_high': prev['low'],
                            'gap_pips': gap_pips,
                            'strength': self._calculate_fvg_strength(data, i, 'bearish'),
                            'index': i
                        })
        
        # Filter and return strongest FVG
        if not fvgs:
            return None
        
        # Sort by strength
        fvgs.sort(key=lambda x: x['strength'], reverse=True)
        
        # Check if FVG is still unfulfilled
        best_fvg = fvgs[0]
        if self._is_fvg_fulfilled(data, best_fvg):
            return None
        
        return best_fvg
    
    def _calculate_fvg_strength(self, data: pd.DataFrame, index: int, fvg_type: str) -> float:
        """Calculate FVG strength (0-1)"""
        strength = 0.5  # Base
        
        # Check gap size (larger gaps are stronger)
        pip_size = self._get_pip_size(data['close'].iloc[index])
        gap_size = abs(data['high'].iloc[index] - data['low'].iloc[index-1]) / pip_size
        if gap_size > 15:
            strength += 0.2
        elif gap_size > 10:
            strength += 0.1
        
        # Check surrounding price action
        if fvg_type == 'bullish':
            # Bullish momentum before gap
            if index >= 3:
                prev_high = data['high'].iloc[index-3:index].max()
                if prev_high < data['low'].iloc[index]:
                    strength += 0.2
        else:
            # Bearish momentum before gap
            if index >= 3:
                prev_low = data['low'].iloc[index-3:index].min()
                if prev_low > data['high'].iloc[index]:
                    strength += 0.2
        
        # Check for continuation candles after gap
        if index < len(data) - 3:
            after_high = data['high'].iloc[index+1:index+4].max()
            after_low = data['low'].iloc[index+1:index+4].min()
            
            if fvg_type == 'bullish':
                if after_low > data['high'].iloc[index]:
                    strength += 0.1
            else:
                if after_high < data['low'].iloc[index]:
                    strength += 0.1
        
        return min(strength, 1.0)
    
    def _is_fvg_fulfilled(self, data: pd.DataFrame, fvg: Dict) -> bool:
        """Check if FVG has been filled"""
        # Check subsequent candles
        for i in range(fvg['index'] + 1, len(data)):
            candle_low = data['low'].iloc[i]
            candle_high = data['high'].iloc[i]
            
            if fvg['type'] == 'bullish':
                # Bullish FVG is filled when price trades back into the gap
                if candle_low <= fvg['fvg_high'] and candle_high >= fvg['fvg_low']:
                    return True
            else:
                # Bearish FVG is filled when price trades back into the gap
                if candle_low <= fvg['fvg_high'] and candle_high >= fvg['fvg_low']:
                    return True
        
        return False
    
    def _get_pip_size(self, price: float) -> float:
        """Get pip size based on price level"""
        if price >= 1000:
            return 0.1
        elif price >= 100:
            return 0.01
        elif price >= 10:
            return 0.001
        else:
            return 0.0001
    
    def detect_multiple_fvgs(self, data: pd.DataFrame, purge_type: str, max_fvgs: int = 5) -> List[Dict]:
        """Detect multiple FVGs"""
        fvgs = []
        for i in range(1, len(data) - 1):
            fvg = self.detect(data.iloc[max(0, i-5):i+5], purge_type)
            if fvg:
                fvgs.append(fvg)
            if len(fvgs) >= max_fvgs:
                break
        return fvgs