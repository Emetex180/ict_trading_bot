# utils/sessions.py
from datetime import datetime
from typing import Optional, Dict
from config import ICT_SESSIONS

class SessionManager:
    def __init__(self):
        self.current_session = None
        
    def get_current_session(self) -> str:
        """Get current ICT session name"""
        current_hour = datetime.utcnow().hour
        current_minute = datetime.utcnow().minute
        
        for session_name, session in ICT_SESSIONS.items():
            start = session['start']
            end = session['end']
            
            # Convert to decimal hours
            current_time = current_hour + current_minute / 60
            
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
        current_time = datetime.utcnow().hour + datetime.utcnow().minute / 60
        
        for session in ICT_SESSIONS.values():
            if 'killzone' in session:
                kz_start = session['killzone']['start']
                kz_end = session['killzone']['end']
                
                if kz_start <= current_time < kz_end:
                    return True
        
        return False
    
    def get_session_time_remaining(self) -> Optional[float]:
        """Get minutes remaining in current session"""
        if not self.current_session:
            return None
            
        session = ICT_SESSIONS[self.current_session]
        end_time = session['end']
        
        current_time = datetime.utcnow().hour + datetime.utcnow().minute / 60
        time_remaining = (end_time - current_time) * 60  # Convert to minutes
        
        return max(0, time_remaining)
    
    def get_next_session(self) -> Dict:
        """Get next trading session details"""
        # Find next session
        current_time = datetime.utcnow().hour + datetime.utcnow().minute / 60
        next_session = None
        min_time_diff = float('inf')
        
        for session_name, session in ICT_SESSIONS.items():
            start = session['start']
            if start > current_time:
                time_diff = start - current_time
                if time_diff < min_time_diff:
                    min_time_diff = time_diff
                    next_session = session_name
                    
        if next_session:
            return {
                'name': next_session,
                'starts_in': min_time_diff * 60,  # Minutes
                'start_time': ICT_SESSIONS[next_session]['start']
            }
        
        return None
    
    def get_session_summary(self) -> Dict:
        """Get summary of all sessions"""
        summary = {}
        current_hour = datetime.utcnow().hour
        current_minute = datetime.utcnow().minute
        current_time = current_hour + current_minute / 60
        
        for session_name, session in ICT_SESSIONS.items():
            start = session['start']
            end = session['end']
            
            status = "active" if start <= current_time < end else "inactive"
            
            summary[session_name] = {
                'start': start,
                'end': end,
                'status': status,
                'killzone': session.get('killzone', None)
            }
            
        return summary