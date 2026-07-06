# detectors/fvg.py
import pandas as pd
import numpy as np
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)

class FVGDetector:
    """
    Fair Value Gap (FVG) Detector
    Detects unfulfilled price gaps
    """
    
    def __init__(self, min_gap: float = 2, max_gap: float = 50):  # Made min_gap smaller (2 pips)
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
        
        # Scan for FVGs - look at more candles
        fvgs = []
        
        # Check multiple candles for FVGs (not just adjacent)
        for i in range(1, min(len(data) - 1, 20)):  # Check up to 20 candles back
            try:
                prev = data.iloc[-i-2]  # 2 candles ago
                curr = data.iloc[-i-1]   # 1 candle ago
                
                # Bullish FVG: Gap up (previous high < current low)
                if purge_type == 'buy':
                    if prev['high'] < curr['low']:
                        gap_pips = (curr['low'] - prev['high']) / pip_size
                        if self.min_gap_pips <= gap_pips <= self.max_gap_pips:
                            fvgs.append({
                                'type': 'bullish',
                                'fvg_low': prev['high'],
                                'fvg_high': curr['low'],
                                'gap_pips': gap_pips,
                                'strength': self._calculate_fvg_strength(data, -i-1, 'bullish'),
                                'index': -i-1
                            })
                
                # Bearish FVG: Gap down (previous low > current high)
                elif purge_type == 'sell':
                    if prev['low'] > curr['high']:
                        gap_pips = (prev['low'] - curr['high']) / pip_size
                        if self.min_gap_pips <= gap_pips <= self.max_gap_pips:
                            fvgs.append({
                                'type': 'bearish',
                                'fvg_low': curr['high'],
                                'fvg_high': prev['low'],
                                'gap_pips': gap_pips,
                                'strength': self._calculate_fvg_strength(data, -i-1, 'bearish'),
                                'index': -i-1
                            })
            except Exception as e:
                continue
        
        # If no FVGs found, try a more relaxed approach
        if not fvgs:
            # Try looking at every candle in the last 10
            for i in range(len(data) - 2, max(0, len(data) - 20), -1):
                try:
                    prev = data.iloc[i]
                    curr = data.iloc[i+1]
                    
                    if purge_type == 'buy' and prev['high'] < curr['low']:
                        gap_pips = (curr['low'] - prev['high']) / pip_size
                        if self.min_gap_pips <= gap_pips <= self.max_gap_pips:
                            fvgs.append({
                                'type': 'bullish',
                                'fvg_low': prev['high'],
                                'fvg_high': curr['low'],
                                'gap_pips': gap_pips,
                                'strength': 0.5,
                                'index': i
                            })
                    
                    elif purge_type == 'sell' and prev['low'] > curr['high']:
                        gap_pips = (prev['low'] - curr['high']) / pip_size
                        if self.min_gap_pips <= gap_pips <= self.max_gap_pips:
                            fvgs.append({
                                'type': 'bearish',
                                'fvg_low': curr['high'],
                                'fvg_high': prev['low'],
                                'gap_pips': gap_pips,
                                'strength': 0.5,
                                'index': i
                            })
                except:
                    continue
        
        # Filter and return strongest FVG
        if not fvgs:
            return None
        
        # Sort by strength
        fvgs.sort(key=lambda x: x['strength'], reverse=True)
        
        # Return the strongest FVG (even if partially filled)
        best_fvg = fvgs[0]
        
        # Check if FVG is completely filled (relaxed check)
        if self._is_fvg_completely_fulfilled(data, best_fvg):
            return None
        
        return best_fvg
    
    def _calculate_fvg_strength(self, data: pd.DataFrame, index: int, fvg_type: str) -> float:
        """Calculate FVG strength (0-1)"""
        strength = 0.5  # Base
        
        try:
            # Check gap size (larger gaps are stronger)
            pip_size = self._get_pip_size(data['close'].iloc[index])
            
            # Safely get gap size
            if index < 0:
                idx = len(data) + index
            else:
                idx = index
            
            if idx > 0 and idx < len(data) - 1:
                gap_size = abs(data['high'].iloc[idx] - data['low'].iloc[idx-1]) / pip_size
                if gap_size > 15:
                    strength += 0.2
                elif gap_size > 10:
                    strength += 0.1
            
            # Check surrounding price action
            if fvg_type == 'bullish':
                if idx >= 3:
                    prev_high = data['high'].iloc[max(0, idx-3):idx].max()
                    if prev_high < data['low'].iloc[idx]:
                        strength += 0.2
            else:
                if idx >= 3:
                    prev_low = data['low'].iloc[max(0, idx-3):idx].min()
                    if prev_low > data['high'].iloc[idx]:
                        strength += 0.2
            
            # Check for continuation candles
            if idx < len(data) - 3:
                after_high = data['high'].iloc[idx+1:min(len(data), idx+4)].max()
                after_low = data['low'].iloc[idx+1:min(len(data), idx+4)].min()
                
                if fvg_type == 'bullish':
                    if after_low > data['high'].iloc[idx]:
                        strength += 0.1
                else:
                    if after_high < data['low'].iloc[idx]:
                        strength += 0.1
        except:
            pass
        
        return min(strength, 1.0)
    
    def _is_fvg_completely_fulfilled(self, data: pd.DataFrame, fvg: Dict) -> bool:
        """Check if FVG has been completely filled"""
        # Get the index
        idx = fvg['index']
        if idx < 0:
            idx = len(data) + idx
        
        # Check subsequent candles
        for i in range(idx + 1, len(data)):
            try:
                candle_low = data['low'].iloc[i]
                candle_high = data['high'].iloc[i]
                
                # Check if price completely filled the gap
                if fvg['type'] == 'bullish':
                    # Bullish FVG is completely filled when price trades through the entire gap
                    if candle_low <= fvg['fvg_low'] and candle_high >= fvg['fvg_high']:
                        return True
                else:
                    # Bearish FVG is completely filled when price trades through the entire gap
                    if candle_low <= fvg['fvg_low'] and candle_high >= fvg['fvg_high']:
                        return True
            except:
                continue
        
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
        for i in range(1, min(len(data) - 1, 30)):
            fvg = self.detect(data.iloc[max(0, i-5):i+5], purge_type)
            if fvg:
                fvgs.append(fvg)
            if len(fvgs) >= max_fvgs:
                break
        return fvgs