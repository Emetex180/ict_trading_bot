# config.py
import pytz
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os

# =================================================
# TIMEZONE CONFIGURATION (DST-Aware)
# =================================================

class TimezoneConfig:
    """Handles DST-aware timezone conversions"""
    def __init__(self):
        self.ny_tz = pytz.timezone('America/New_York')
        self.utc_tz = pytz.UTC
    
    def get_ny_time(self) -> datetime:
        """Get current New York time with DST awareness"""
        return datetime.now(self.ny_tz)
    
    def get_utc_offset(self) -> int:
        """Get current UTC offset (hours) for New York"""
        ny_time = self.get_ny_time()
        return int(ny_time.utcoffset().total_seconds() / 3600)
    
    def is_dst(self) -> bool:
        """Check if currently in Daylight Saving Time"""
        ny_time = self.get_ny_time()
        return ny_time.dst() != timedelta(0)

timezone = TimezoneConfig()

# =================================================
# ICT SESSIONS (New York Time with Macro Windows)
# =================================================

class ICTSession:
    def __init__(self, name: str, start_hour: int, start_minute: int, 
                 end_hour: int, end_minute: int, macro_minutes: int = 10):
        self.name = name
        self.start_hour = start_hour
        self.start_minute = start_minute
        self.end_hour = end_hour
        self.end_minute = end_minute
        self.macro_minutes = macro_minutes
        
        # Calculate macro window (10 min before and after)
        self.macro_start = self._add_minutes(start_hour, start_minute, -macro_minutes)
        self.macro_end = self._add_minutes(end_hour, end_minute, macro_minutes)
    
    def _add_minutes(self, hour: int, minute: int, minutes: int) -> tuple:
        """Add minutes to time, handling hour wraparound"""
        total_minutes = hour * 60 + minute + minutes
        if total_minutes < 0:
            total_minutes += 1440
        elif total_minutes >= 1440:
            total_minutes -= 1440
        return (total_minutes // 60, total_minutes % 60)
    
    def time_to_minutes(self, hour: int, minute: int) -> int:
        """Convert time to minutes from midnight"""
        return hour * 60 + minute
    
    def is_in_session(self, current_hour: int, current_minute: int, use_macro: bool = True) -> bool:
        """Check if current time is in session (with optional macro window)"""
        current_minutes = self.time_to_minutes(current_hour, current_minute)
        
        if use_macro:
            start_h, start_m = self.macro_start
            end_h, end_m = self.macro_end
        else:
            start_h, start_m = self.start_hour, self.start_minute
            end_h, end_m = self.end_hour, self.end_minute
        
        start_minutes = self.time_to_minutes(start_h, start_m)
        end_minutes = self.time_to_minutes(end_h, end_m)
        
        # Handle sessions that cross midnight
        if start_minutes <= end_minutes:
            return start_minutes <= current_minutes < end_minutes
        else:
            return current_minutes >= start_minutes or current_minutes < end_minutes
    
    def get_macro_window(self) -> Dict:
        """Get macro window details"""
        return {
            'start': f"{self.macro_start[0]:02d}:{self.macro_start[1]:02d}",
            'end': f"{self.macro_end[0]:02d}:{self.macro_end[1]:02d}",
            'start_minutes': self.time_to_minutes(*self.macro_start),
            'end_minutes': self.time_to_minutes(*self.macro_end)
        }

# =================================================
# ASSET WATCHLIST
# =================================================

WATCHLIST = {
    'forex': [
        'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 
        'USDCAD', 'NZDUSD', 'EURGBP', 'EURJPY',
        'GBPJPY', 'AUDJPY', 'CHFJPY'
    ],
    'indices': ['NAS100', 'US30', 'SPX500', 'UK100', 'GER40'],
    'crypto': ['BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD']
}

# Flatten for scanning
ALL_SYMBOLS = [s for category in WATCHLIST.values() for s in category]

# =================================================
# ASSET CATEGORIES
# =================================================

ASSET_CATEGORIES = {
    # Forex
    'EURUSD': 'forex', 'GBPUSD': 'forex', 'USDJPY': 'forex',
    'AUDUSD': 'forex', 'USDCAD': 'forex', 'NZDUSD': 'forex',
    'EURGBP': 'forex', 'EURJPY': 'forex', 'GBPJPY': 'forex',
    'AUDJPY': 'forex', 'CHFJPY': 'forex',
    # Indices
    'NAS100': 'indices', 'US30': 'indices', 'SPX500': 'indices',
    'UK100': 'indices', 'GER40': 'indices',
    # Crypto
    'BTCUSD': 'crypto', 'ETHUSD': 'crypto', 
    'SOLUSD': 'crypto', 'XRPUSD': 'crypto'
}

# =================================================
# ASSET-SPECIFIC SESSION CONFIGURATION
# =================================================

# All sessions defined in New York Time (ET)
SESSIONS = {
    'asian': ICTSession(
        name='Asian',
        start_hour=19, start_minute=0,  # 7:00 PM
        end_hour=23, end_minute=0,      # 11:00 PM
        macro_minutes=10
    ),
    'london': ICTSession(
        name='London',
        start_hour=1, start_minute=0,   # 1:00 AM
        end_hour=5, end_minute=0,       # 5:00 AM
        macro_minutes=10
    ),
    'new_york': ICTSession(
        name='New York',
        start_hour=7, start_minute=0,   # 7:00 AM
        end_hour=10, end_minute=0,      # 10:00 AM
        macro_minutes=10
    ),
    'sweet_spot': ICTSession(
        name='Sweet Spot',
        start_hour=9, start_minute=30,  # 9:30 AM
        end_hour=11, end_minute=0,      # 11:00 AM
        macro_minutes=10
    ),
    'afternoon': ICTSession(
        name='Afternoon',
        start_hour=13, start_minute=0,  # 1:00 PM
        end_hour=16, end_minute=0,      # 4:00 PM
        macro_minutes=10
    ),
    'power_hour': ICTSession(
        name='Power Hour',
        start_hour=15, start_minute=0,  # 3:00 PM
        end_hour=16, end_minute=0,      # 4:00 PM
        macro_minutes=10
    )
}

# Asset categories with their allowed sessions
ASSET_SESSIONS = {
    'forex': ['asian', 'london', 'new_york'],
    'crypto': ['asian', 'london', 'new_york'],
    'indices': ['london', 'sweet_spot', 'afternoon', 'power_hour']
}

# =================================================
# MACRO WINDOW CONFIGURATION
# =================================================

MACRO_CONFIG = {
    'enabled': True,
    'minutes_before': 10,
    'minutes_after': 10,
    'scan_during_macro_only': True,
    'macro_priority': {
        'power_hour': 10,
        'sweet_spot': 9,
        'new_york': 8,
        'london': 7,
        'afternoon': 6,
        'asian': 5
    }
}

# =================================================
# TRADING CONFIGURATION
# =================================================

TRADING_CONFIG = {
    'liquidity_lookback': 20,
    'liquidity_timeframe': '1h',
    'cisd_lookback': 5,
    'cisd_timeframe': '5m',
    'fvg_timeframe': '1m',
    'min_gap_pips': 5,
    'max_gap_pips': 50,
    'max_risk_per_trade': 0.02,
    'risk_reward_ratio': 2.0,
    'max_daily_trades': 5
}

# =================================================
# ALLOWED SESSIONS
# =================================================

ALLOWED_SESSIONS = ['asian', 'london', 'new_york', 'sweet_spot', 'afternoon', 'power_hour']

# =================================================
# OANDA API CONFIGURATION
# =================================================

OANDA_CONFIG = {
    'api_key': 'YOUR_OANDA_API_KEY',  # Replace with your API key
    'account_id': 'YOUR_OANDA_ACCOUNT_ID',  # Replace with your account ID
    'environment': 'practice',  # 'practice' or 'live'
    'base_url': 'https://api-fxpractice.oanda.com/v3'  # Use 'https://api-fxtrade.oanda.com/v3' for live
}

# =================================================
# TELEGRAM CONFIGURATION
# =================================================

TELEGRAM_CONFIG = {
    'bot_token': 'YOUR_BOT_TOKEN',  # Replace with your bot token
    'chat_ids': ['YOUR_CHAT_ID']     # Replace with your chat ID
}

# =================================================
# DISCORD CONFIGURATION
# =================================================

DISCORD_CONFIG = {
    'webhook_url': 'YOUR_WEBHOOK_URL'  # Replace with your webhook URL
}

# =================================================
# DATABASE CONFIGURATION
# =================================================

DATABASE_PATH = 'data/trading_bot.db'

# =================================================
# LOGGING CONFIGURATION
# =================================================

LOG_LEVEL = 'INFO'
LOG_FILE = 'logs/trading_bot.log'

# =================================================
# SESSION MANAGER WITH MACRO SUPPORT
# =================================================

class SessionManager:
    def __init__(self):
        self.ny_tz = pytz.timezone('America/New_York')
        self.sessions = SESSIONS
        self.asset_sessions = ASSET_SESSIONS
        self.asset_categories = ASSET_CATEGORIES
        
    def get_current_ny_time(self) -> datetime:
        """Get current New York time with DST awareness"""
        return datetime.now(self.ny_tz)
    
    def get_session_for_asset(self, symbol: str) -> List[str]:
        """Get allowed session names for an asset"""
        category = self.asset_categories.get(symbol, 'forex')
        return self.asset_sessions.get(category, ['london', 'new_york'])
    
    def is_session_active(self, session_name: str, use_macro: bool = True) -> bool:
        """Check if a specific session is active"""
        session = self.sessions.get(session_name)
        if not session:
            return False
        
        ny_time = self.get_current_ny_time()
        current_hour = ny_time.hour
        current_minute = ny_time.minute
        
        return session.is_in_session(current_hour, current_minute, use_macro)
    
    def get_active_sessions(self, symbol: str = None, use_macro: bool = True) -> List[str]:
        """Get all active sessions for an asset"""
        active = []
        
        if symbol:
            allowed = self.get_session_for_asset(symbol)
            for session_name in allowed:
                if self.is_session_active(session_name, use_macro):
                    active.append(session_name)
        else:
            for session_name in self.sessions.keys():
                if self.is_session_active(session_name, use_macro):
                    active.append(session_name)
        
        return active
    
    def get_macro_window_details(self, session_name: str) -> Dict:
        """Get macro window details for a session"""
        session = self.sessions.get(session_name)
        if session:
            return session.get_macro_window()
        return {}
    
    def get_session_priority(self, session_name: str) -> int:
        """Get priority score for a session (higher = more important)"""
        return MACRO_CONFIG['macro_priority'].get(session_name, 5)
    
    def get_best_active_session(self, symbol: str) -> Optional[str]:
        """Get the highest priority active session for an asset"""
        active = self.get_active_sessions(symbol)
        if not active:
            return None
        
        # Sort by priority
        active.sort(key=lambda s: self.get_session_priority(s), reverse=True)
        return active[0]
    
    def get_session_status(self, symbol: str = None) -> Dict:
        """Get detailed session status for display"""
        ny_time = self.get_current_ny_time()
        
        status = {
            'timestamp': ny_time.isoformat(),
            'timezone': 'America/New_York',
            'dst_active': ny_time.dst() != timedelta(0),
            'utc_offset': int(ny_time.utcoffset().total_seconds() / 3600),
            'sessions': {}
        }
        
        sessions_to_check = self.sessions.keys()
        if symbol:
            sessions_to_check = self.get_session_for_asset(symbol)
        
        for session_name in sessions_to_check:
            session = self.sessions[session_name]
            is_active = session.is_in_session(ny_time.hour, ny_time.minute, False)
            is_macro = session.is_in_session(ny_time.hour, ny_time.minute, True)
            macro_window = session.get_macro_window()
            
            status['sessions'][session_name] = {
                'name': session.name,
                'active': is_active,
                'macro_active': is_macro and not is_active,
                'in_session': is_macro,
                'start': f"{session.start_hour:02d}:{session.start_minute:02d}",
                'end': f"{session.end_hour:02d}:{session.end_minute:02d}",
                'macro_start': macro_window['start'],
                'macro_end': macro_window['end'],
                'priority': self.get_session_priority(session_name),
                'time_remaining': self._get_time_remaining(session)
            }
        
        return status
    
    def _get_time_remaining(self, session: ICTSession) -> Optional[int]:
        """Get minutes remaining in session"""
        ny_time = self.get_current_ny_time()
        current_minutes = ny_time.hour * 60 + ny_time.minute
        end_minutes = session.end_hour * 60 + session.end_minute
        
        if session.is_in_session(ny_time.hour, ny_time.minute, False):
            if end_minutes > current_minutes:
                return end_minutes - current_minutes
            else:
                return (1440 - current_minutes) + end_minutes
        return None
    
    def should_scan(self, symbol: str) -> bool:
        """Determine if we should scan an asset based on session"""
        active = self.get_active_sessions(symbol)
        
        if not active:
            return False
        
        if MACRO_CONFIG['scan_during_macro_only']:
            ny_time = self.get_current_ny_time()
            for session_name in active:
                session = self.sessions[session_name]
                if session.is_in_session(ny_time.hour, ny_time.minute, True):
                    return True
            return False
        
        return True
    
    def get_next_session_start(self, symbol: str = None) -> Optional[Dict]:
        """Get the next session start time for an asset"""
        ny_time = self.get_current_ny_time()
        current_minutes = ny_time.hour * 60 + ny_time.minute
        
        sessions_to_check = self.sessions.keys()
        if symbol:
            sessions_to_check = self.get_session_for_asset(symbol)
        
        next_session = None
        min_wait = float('inf')
        
        for session_name in sessions_to_check:
            session = self.sessions[session_name]
            start_minutes = session.start_hour * 60 + session.start_minute
            
            if start_minutes > current_minutes:
                wait = start_minutes - current_minutes
            else:
                wait = (1440 - current_minutes) + start_minutes
            
            if wait < min_wait:
                min_wait = wait
                next_session = {
                    'name': session_name,
                    'start_time': f"{session.start_hour:02d}:{session.start_minute:02d}",
                    'wait_minutes': wait,
                    'macro_start': f"{session.macro_start[0]:02d}:{session.macro_start[1]:02d}",
                    'macro_wait_minutes': wait - MACRO_CONFIG['minutes_before']
                }
        
        return next_session