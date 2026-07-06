# utils/sessions.py
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pytz

# Import from config
from config import ICT_SESSIONS, ASSET_SESSIONS, ASSET_CATEGORIES, MACRO_CONFIG

class SessionManager:
    def __init__(self):
        """Initialize session manager with all required attributes"""
        self.ny_tz = pytz.timezone('America/New_York')
        self.sessions = ICT_SESSIONS  # <-- THIS IS WHAT main.py NEEDS
        self.asset_sessions = ASSET_SESSIONS
        self.asset_categories = ASSET_CATEGORIES
        self.current_session = None
        
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
    
    def _get_time_remaining(self, session) -> Optional[int]:
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
    
    # ============================================================
    # Legacy methods (kept for compatibility)
    # ============================================================
    
    def get_current_session(self) -> str:
        """Get current ICT session name"""
        ny_time = self.get_current_ny_time()
        current_hour = ny_time.hour
        current_minute = ny_time.minute
        current_time = current_hour + current_minute / 60
        
        for session_name, session in self.sessions.items():
            start_hour = session.start_hour
            start_minute = session.start_minute
            end_hour = session.end_hour
            end_minute = session.end_minute
            
            start = start_hour + start_minute / 60
            end = end_hour + end_minute / 60
            
            if start <= end:
                if start <= current_time < end:
                    self.current_session = session_name
                    return session_name
            else:
                if current_time >= start or current_time < end:
                    self.current_session = session_name
                    return session_name
        
        self.current_session = None
        return "off_session"
    
    def is_killzone(self) -> bool:
        """Check if current time is in Killzone"""
        return len(self.get_active_sessions()) > 0
    
    def get_session_time_remaining(self) -> Optional[float]:
        """Get minutes remaining in current session"""
        if not self.current_session:
            return None
        
        session = self.sessions.get(self.current_session)
        if not session:
            return None
        
        ny_time = self.get_current_ny_time()
        current_minutes = ny_time.hour * 60 + ny_time.minute
        end_minutes = session.end_hour * 60 + session.end_minute
        
        if end_minutes > current_minutes:
            return end_minutes - current_minutes
        else:
            return (1440 - current_minutes) + end_minutes
    
    def get_next_session(self) -> Optional[Dict]:
        """Get next trading session details"""
        result = self.get_next_session_start()
        if result:
            return {
                'name': result['name'],
                'starts_in': result['wait_minutes'],
                'start_time': result['start_time']
            }
        return None
    
    def get_session_summary(self) -> Dict:
        """Get summary of all sessions"""
        summary = {}
        ny_time = self.get_current_ny_time()
        current_time = ny_time.hour + ny_time.minute / 60
        
        for session_name, session in self.sessions.items():
            start = session.start_hour + session.start_minute / 60
            end = session.end_hour + session.end_minute / 60
            
            status = "active" if start <= current_time < end else "inactive"
            macro_window = session.get_macro_window()
            
            summary[session_name] = {
                'start': start,
                'end': end,
                'status': status,
                'killzone': {
                    'start': session.start_hour - 0.167,
                    'end': session.end_hour + 0.167
                },
                'macro_window': macro_window
            }
        
        return summary