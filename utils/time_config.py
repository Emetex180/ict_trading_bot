# utils/time_config.py
import pytz
from datetime import datetime, timedelta
from typing import Optional, Tuple

class DSTAwareTime:
    """Handles DST-aware time conversions for ICT sessions"""
    
    def __init__(self):
        self.ny_tz = pytz.timezone('America/New_York')
        self.utc_tz = pytz.UTC
        
    def get_ny_time(self) -> datetime:
        """Get current New York time with proper DST"""
        return datetime.now(self.ny_tz)
    
    def get_utc_time(self) -> datetime:
        """Get current UTC time"""
        return datetime.now(self.utc_tz)
    
    def ny_to_utc(self, ny_datetime: datetime) -> datetime:
        """Convert New York time to UTC"""
        if ny_datetime.tzinfo is None:
            ny_datetime = self.ny_tz.localize(ny_datetime)
        return ny_datetime.astimezone(self.utc_tz)
    
    def utc_to_ny(self, utc_datetime: datetime) -> datetime:
        """Convert UTC to New York time"""
        if utc_datetime.tzinfo is None:
            utc_datetime = self.utc_tz.localize(utc_datetime)
        return utc_datetime.astimezone(self.ny_tz)
    
    def get_session_times_et(self, session_name: str, date: Optional[datetime] = None) -> Tuple[datetime, datetime]:
        """Get session start and end times in ET with DST handling"""
        if date is None:
            date = self.get_ny_time().date()
        
        # Session definitions (ET)
        sessions = {
            'asian': (19, 0, 23, 0),      # 7PM - 11PM
            'london': (1, 0, 5, 0),       # 1AM - 5AM
            'new_york': (7, 0, 10, 0),    # 7AM - 10AM
            'sweet_spot': (9, 30, 11, 0), # 9:30AM - 11AM
            'afternoon': (13, 0, 16, 0),  # 1PM - 4PM
            'power_hour': (15, 0, 16, 0)  # 3PM - 4PM
        }
        
        if session_name not in sessions:
            raise ValueError(f"Unknown session: {session_name}")
        
        start_h, start_m, end_h, end_m = sessions[session_name]
        
        # Create datetime objects
        start = datetime(date.year, date.month, date.day, start_h, start_m)
        end = datetime(date.year, date.month, date.day, end_h, end_m)
        
        # Localize to ET
        start = self.ny_tz.localize(start)
        end = self.ny_tz.localize(end)
        
        # Handle sessions that cross midnight
        if end < start:
            end += timedelta(days=1)
        
        return start, end
    
    def get_session_utc(self, session_name: str, date: Optional[datetime] = None) -> Tuple[datetime, datetime]:
        """Get session times in UTC"""
        start_et, end_et = self.get_session_times_et(session_name, date)
        return start_et.astimezone(self.utc_tz), end_et.astimezone(self.utc_tz)
    
    def get_session_status_et(self, session_name: str) -> Dict:
        """Get detailed session status with DST info"""
        ny_time = self.get_ny_time()
        start_et, end_et = self.get_session_times_et(session_name, ny_time.date())
        
        # Check if currently in session
        is_active = start_et <= ny_time <= end_et
        
        # Calculate macro window (10min before/after)
        macro_start = start_et - timedelta(minutes=10)
        macro_end = end_et + timedelta(minutes=10)
        
        return {
            'session_name': session_name,
            'start_et': start_et.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'end_et': end_et.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'start_utc': start_et.astimezone(self.utc_tz).strftime('%Y-%m-%d %H:%M:%S %Z'),
            'end_utc': end_et.astimezone(self.utc_tz).strftime('%Y-%m-%d %H:%M:%S %Z'),
            'is_active': is_active,
            'in_macro': macro_start <= ny_time <= macro_end,
            'minutes_until_start': max(0, (start_et - ny_time).seconds // 60) if not is_active else 0,
            'minutes_remaining': max(0, (end_et - ny_time).seconds // 60) if is_active else 0,
            'dst_active': bool(ny_time.dst()),
            'utc_offset': int(ny_time.utcoffset().total_seconds() / 3600)
        }