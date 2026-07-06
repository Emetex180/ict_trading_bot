# data/fetcher.py - MT5 Version (FIXED)
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import logging
import asyncio
import time

logger = logging.getLogger(__name__)

class MarketDataFetcher:
    def __init__(self):
        """Initialize MT5 connection"""
        self.connected = False
        self.symbols = {}
        self.cache = {}
        self.last_request_time = {}
        self.login = 5052695458
        self.password = "LiK-B1Og"
        self.server = "MetaQuotes-Demo"
        
        # Try to connect to MT5
        self._connect()
        
    def _connect(self) -> bool:
        """Connect to MetaTrader 5 terminal"""
        try:
            # Initialize MT5
            if not mt5.initialize():
                logger.error("MT5 initialization failed")
                logger.error(f"Error: {mt5.last_error()}")
                return False
            
            # Attempt login
            if not mt5.login(login=self.login, password=self.password, server=self.server):
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                # Try without login (might still work for some data)
                logger.warning("Continuing with MT5 without login...")
            
            # Check connection
            if mt5.terminal_info():
                self.connected = True
                logger.info("✅ Connected to MetaTrader 5")
                logger.info(f"Terminal: {mt5.terminal_info().name}")
                logger.info(f"Connected: {mt5.terminal_info().connected}")
                
                # Get available symbols
                symbols = mt5.symbols_get()
                if symbols:
                    logger.info(f"Available symbols: {len(symbols)}")
                    # Show first 10 symbols
                    for symbol in symbols[:10]:
                        logger.info(f"  {symbol.name}")
                return True
            else:
                logger.warning("MT5 connection established but terminal info not available")
                return True
                
        except Exception as e:
            logger.error(f"MT5 connection error: {e}")
            return False
    
    def _ensure_connection(self) -> bool:
        """Ensure MT5 is connected"""
        if not self.connected:
            return self._connect()
        return True
    
    def _get_symbol_name(self, symbol: str) -> str:
        """Convert symbol to MT5 format"""
        # Convert to uppercase first
        symbol = symbol.upper()
        
        # Common mappings
        symbol_map = {
            'EURUSD': 'EURUSD',
            'GBPUSD': 'GBPUSD', 
            'USDJPY': 'USDJPY',
            'AUDUSD': 'AUDUSD',
            'USDCAD': 'USDCAD',
            'NZDUSD': 'NZDUSD',
            'EURGBP': 'EURGBP',
            'EURJPY': 'EURJPY',
            'GBPJPY': 'GBPJPY',
            'AUDJPY': 'AUDJPY',
            'CHFJPY': 'CHFJPY',
            'NAS100': 'NAS100',
            'USTEC': 'USTEC',
            'US30': 'US30',
            'SPX500': 'US500',
            'UK100': 'UK100',
            'GER40': 'GER40',
            'DAX': 'GER40',
            'BTCUSD': 'BTCUSD',
            'ETHUSD': 'ETHUSD',
            'SOLUSD': 'SOLUSD',
            'XRPUSD': 'XRPUSD'
        }
        return symbol_map.get(symbol, symbol)
    
    def _get_timeframe(self, timeframe: str) -> int:
        """Convert timeframe to MT5 constant"""
        timeframe_map = {
            '1m': mt5.TIMEFRAME_M1,
            '2m': mt5.TIMEFRAME_M2,
            '3m': mt5.TIMEFRAME_M3,
            '4m': mt5.TIMEFRAME_M4,
            '5m': mt5.TIMEFRAME_M5,
            '6m': mt5.TIMEFRAME_M6,
            '10m': mt5.TIMEFRAME_M10,
            '12m': mt5.TIMEFRAME_M12,
            '15m': mt5.TIMEFRAME_M15,
            '20m': mt5.TIMEFRAME_M20,
            '30m': mt5.TIMEFRAME_M30,
            '1h': mt5.TIMEFRAME_H1,
            '2h': mt5.TIMEFRAME_H2,
            '3h': mt5.TIMEFRAME_H3,
            '4h': mt5.TIMEFRAME_H4,
            '6h': mt5.TIMEFRAME_H6,
            '8h': mt5.TIMEFRAME_H8,
            '12h': mt5.TIMEFRAME_H12,
            '1d': mt5.TIMEFRAME_D1,
            '1w': mt5.TIMEFRAME_W1,
            '1mn': mt5.TIMEFRAME_MN1
        }
        return timeframe_map.get(timeframe, mt5.TIMEFRAME_M1)
    
    async def fetch_data(
        self, 
        symbol: str, 
        timeframe: str, 
        lookback: int = 100,
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data from MT5"""
        try:
            # Check cache
            cache_key = f"{symbol}_{timeframe}_{lookback}"
            if use_cache and cache_key in self.cache:
                cache_age = (datetime.now() - self.cache[cache_key]['timestamp']).seconds
                if cache_age < 60:  # Cache for 60 seconds
                    return self.cache[cache_key]['data']
            
            if not self._ensure_connection():
                logger.warning(f"No MT5 connection, using mock data for {symbol}")
                return self.generate_mock_data(symbol, timeframe, lookback)
            
            # Get symbol in MT5 format
            mt5_symbol = self._get_symbol_name(symbol)
            mt5_timeframe = self._get_timeframe(timeframe)
            
            # Check if symbol is available
            symbol_info = mt5.symbol_info(mt5_symbol)
            if not symbol_info:
                logger.warning(f"Symbol {mt5_symbol} not found in MT5, using mock data")
                return self.generate_mock_data(symbol, timeframe, lookback)
            
            # Rate limiting
            await self._rate_limit(mt5_symbol)
            
            # Fetch data
            rates = mt5.copy_rates_from_pos(mt5_symbol, mt5_timeframe, 0, lookback)
            
            if rates is None or len(rates) == 0:
                logger.warning(f"No data for {mt5_symbol}, using mock data")
                return self.generate_mock_data(symbol, timeframe, lookback)
            
            # Convert to DataFrame
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            
            # Rename columns to match expected format
            df = df[['open', 'high', 'low', 'close', 'tick_volume']]
            df.rename(columns={'tick_volume': 'volume'}, inplace=True)
            
            # Cache the result
            self.cache[cache_key] = {
                'data': df,
                'timestamp': datetime.now()
            }
            
            logger.debug(f"Fetched {len(df)} candles for {symbol} from MT5")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return self.generate_mock_data(symbol, timeframe, lookback)
    
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
        timeframes: List[str] = None
    ) -> Dict:
        """Fetch multiple timeframes for a symbol"""
        if timeframes is None:
            timeframes = ['1m', '5m', '1h']
        
        result = {}
        for tf in timeframes:
            data = await self.fetch_data(symbol, tf)
            if data is not None:
                result[tf] = data
        return result
    
    def fetch_historical_data(self, symbol: str, timeframe: str, 
                              start_date: datetime, end_date: datetime) -> Optional[pd.DataFrame]:
        """Fetch historical data between two dates for backtesting"""
        try:
            if not self._ensure_connection():
                return self.generate_mock_data(symbol, timeframe, 1000)
            
            mt5_symbol = self._get_symbol_name(symbol)
            mt5_timeframe = self._get_timeframe(timeframe)
            
            # Convert to MT5 datetime format (seconds since 1970)
            start = int(start_date.timestamp())
            end = int(end_date.timestamp())
            
            rates = mt5.copy_rates_range(mt5_symbol, mt5_timeframe, start, end)
            
            if rates is None or len(rates) == 0:
                logger.warning(f"No historical data for {mt5_symbol}, using mock data")
                return self.generate_mock_data(symbol, timeframe, 1000)
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            df = df[['open', 'high', 'low', 'close', 'tick_volume']]
            df.rename(columns={'tick_volume': 'volume'}, inplace=True)
            
            logger.info(f"Fetched {len(df)} historical candles for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return None
    
    def generate_mock_data(self, symbol: str, timeframe: str, lookback: int = 100) -> pd.DataFrame:
        """Generate mock data for testing"""
        np.random.seed(42 + hash(symbol) % 1000)
        
        # Base prices
        base_prices = {
            'EURUSD': 1.10, 'GBPUSD': 1.30, 'USDJPY': 150.0,
            'AUDUSD': 0.65, 'USDCAD': 1.35, 'NZDUSD': 0.60,
            'EURGBP': 0.85, 'EURJPY': 165.0, 'GBPJPY': 195.0,
            'AUDJPY': 97.0, 'CHFJPY': 170.0,
            'NAS100': 18000, 'US30': 40000, 'SPX500': 5000,
            'UK100': 8000, 'GER40': 17000,
            'BTCUSD': 60000, 'ETHUSD': 3000, 'SOLUSD': 150, 'XRPUSD': 0.50
        }
        
        base_price = base_prices.get(symbol.upper(), 100.0)
        
        # Generate price data with trend
        trend = np.random.normal(0, 0.0005, lookback)
        returns = np.random.normal(0, 0.001, lookback) + trend
        prices = base_price * np.exp(np.cumsum(returns))
        
        # Create OHLC
        df = pd.DataFrame({
            'open': prices * (1 + np.random.normal(0, 0.0005, lookback)),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.001, lookback))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.001, lookback))),
            'close': prices,
            'volume': np.random.randint(100, 1000, lookback)
        })
        
        # Ensure high >= low
        df['high'] = df[['open', 'high', 'close']].max(axis=1)
        df['low'] = df[['open', 'low', 'close']].min(axis=1)
        
        # Generate timestamps
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
        return df
    
    def __del__(self):
        """Cleanup MT5 connection"""
        try:
            mt5.shutdown()
        except:
            pass