# data/fetcher.py
import aiohttp
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict
import logging
from config import OANDA_CONFIG

logger = logging.getLogger(__name__)

class MarketDataFetcher:
    def __init__(self):
        self.api_key = OANDA_CONFIG['api_key']
        self.account_id = OANDA_CONFIG['account_id']
        self.base_url = OANDA_CONFIG['base_url']
        self.environment = OANDA_CONFIG['environment']
        
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        # Cache for rate limits
        self.cache = {}
        self.last_request_time = {}
        
    def get_instrument_id(self, symbol: str) -> str:
        """Convert symbol to OANDA format"""
        # Forex pairs: EURUSD -> EUR_USD
        if symbol in ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 
                     'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY', 'AUDJPY', 
                     'CHFJPY']:
            return f"{symbol[:3]}_{symbol[3:]}"
        
        # Indices
        if symbol == 'NAS100':
            return 'NAS100_USD'
        elif symbol == 'US30':
            return 'US30_USD'
        elif symbol == 'SPX500':
            return 'SPX500_USD'
        elif symbol == 'UK100':
            return 'UK100_GBP'
        elif symbol == 'GER40':
            return 'GER40_EUR'
        
        # Crypto
        if symbol in ['BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD']:
            return symbol
        
        return symbol

    def get_timeframe_granularity(self, timeframe: str) -> str:
        """Convert timeframe to OANDA granularity"""
        mapping = {
            '1m': 'M1',
            '5m': 'M5',
            '15m': 'M15',
            '30m': 'M30',
            '1h': 'H1',
            '4h': 'H4',
            '1d': 'D',
            '1w': 'W'
        }
        return mapping.get(timeframe, 'M1')

    async def fetch_data(
        self, 
        symbol: str, 
        timeframe: str, 
        lookback: int = 100,
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data from OANDA"""
        try:
            # Check cache
            cache_key = f"{symbol}_{timeframe}_{lookback}"
            if use_cache and cache_key in self.cache:
                cache_age = (datetime.now() - self.cache[cache_key]['timestamp']).seconds
                if cache_age < 60:  # Cache for 60 seconds
                    return self.cache[cache_key]['data']
            
            # Get data from API
            instrument = self.get_instrument_id(symbol)
            granularity = self.get_timeframe_granularity(timeframe)
            
            # Calculate date range
            end = datetime.utcnow()
            # Estimate how many candles needed (add buffer)
            if 'm' in timeframe:
                minutes = int(timeframe.replace('m', ''))
                start = end - timedelta(minutes=minutes * lookback * 2)
            elif 'h' in timeframe:
                hours = int(timeframe.replace('h', ''))
                start = end - timedelta(hours=hours * lookback * 2)
            else:
                start = end - timedelta(days=lookback * 2)
            
            # Format for OANDA
            start_str = start.strftime('%Y-%m-%dT%H:%M:%SZ')
            end_str = end.strftime('%Y-%m-%dT%H:%M:%SZ')
            
            # Build URL
            url = f"{self.base_url}/accounts/{self.account_id}/candles"
            params = {
                'instrument': instrument,
                'granularity': granularity,
                'from': start_str,
                'to': end_str,
                'price': 'M'  # Midpoint prices
            }
            
            # Rate limiting
            await self._rate_limit(instrument)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"OANDA API error for {symbol}: {error_text}")
                        return None
                    
                    data = await response.json()
                    
                    # Parse candles
                    candles = []
                    for candle in data['candles']:
                        if candle['complete']:  # Only use completed candles
                            mid = candle['mid']
                            candles.append({
                                'timestamp': pd.to_datetime(candle['time']),
                                'open': float(mid['o']),
                                'high': float(mid['h']),
                                'low': float(mid['l']),
                                'close': float(mid['c']),
                                'volume': candle.get('volume', 0)
                            })
                    
                    if not candles:
                        return None
                    
                    df = pd.DataFrame(candles)
                    df.set_index('timestamp', inplace=True)
                    df = df.tail(lookback)  # Keep only last N candles
                    
                    # Cache the result
                    self.cache[cache_key] = {
                        'data': df,
                        'timestamp': datetime.now()
                    }
                    
                    return df
                    
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None

    async def _rate_limit(self, instrument: str):
        """Implement rate limiting for API calls"""
        now = datetime.now()
        if instrument in self.last_request_time:
            elapsed = (now - self.last_request_time[instrument]).total_seconds()
            if elapsed < 0.5:  # 500ms minimum between requests
                await asyncio.sleep(0.5 - elapsed)
        
        self.last_request_time[instrument] = now

    async def fetch_multi_timeframe(
        self, 
        symbol: str, 
        timeframes: list = ['1m', '5m', '1h']
    ) -> Dict:
        """Fetch multiple timeframes for a symbol"""
        result = {}
        for tf in timeframes:
            data = await self.fetch_data(symbol, tf)
            if data is not None:
                result[tf] = data
        return result

    def generate_mock_data(self, symbol: str, timeframe: str, lookback: int = 100) -> pd.DataFrame:
        """Generate mock data for testing"""
        np.random.seed(42)
        
        # Generate price data with trend
        base_price = 100 if 'USD' in symbol else 1.0
        if symbol == 'BTCUSD':
            base_price = 50000
        elif symbol == 'ETHUSD':
            base_price = 3000
        elif symbol == 'SOLUSD':
            base_price = 150
            
        # Create random walk
        returns = np.random.normal(0, 0.001, lookback)
        prices = base_price * np.exp(np.cumsum(returns))
        
        # Add some volatility clusters
        volatility = np.random.gamma(1, 1, lookback) * 0.002
        returns = returns * (1 + volatility)
        prices = base_price * np.exp(np.cumsum(returns))
        
        # Create OHLC data
        df = pd.DataFrame({
            'open': prices * (1 + np.random.normal(0, 0.0005, lookback)),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.001, lookback))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.001, lookback))),
            'close': prices,
            'volume': np.random.randint(100, 1000, lookback)
        })
        
        # Create timestamps
        if 'm' in timeframe:
            minutes = int(timeframe.replace('m', ''))
            timestamps = pd.date_range(
                start=datetime.now() - timedelta(minutes=minutes*lookback),
                periods=lookback,
                freq=f'{minutes}min'
            )
        elif 'h' in timeframe:
            hours = int(timeframe.replace('h', ''))
            timestamps = pd.date_range(
                start=datetime.now() - timedelta(hours=hours*lookback),
                periods=lookback,
                freq=f'{hours}h'
            )
        else:
            timestamps = pd.date_range(
                start=datetime.now() - timedelta(days=lookback),
                periods=lookback,
                freq='D'
            )
        
        df.index = timestamps
        
        # Clean up: ensure high >= low
        df['high'] = df[['open', 'high', 'close']].max(axis=1)
        df['low'] = df[['open', 'low', 'close']].min(axis=1)
        
        return df