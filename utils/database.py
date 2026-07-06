# utils/database.py
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
import json
import logging
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._initialize_db()
    
    def _initialize_db(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Setups table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS setups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                setup_type TEXT NOT NULL,
                entry_price REAL,
                entry_low REAL,
                entry_high REAL,
                stop_loss REAL,
                take_profit REAL,
                gap_pips REAL,
                confidence INTEGER,
                session TEXT,
                timestamp DATETIME,
                status TEXT DEFAULT 'pending',
                trade_result TEXT,
                profit_loss REAL,
                notes TEXT,
                raw_data TEXT
            )
        ''')
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setup_id INTEGER,
                entry_time DATETIME,
                exit_time DATETIME,
                entry_price REAL,
                exit_price REAL,
                position_size REAL,
                profit_loss REAL,
                pips REAL,
                result TEXT,
                notes TEXT,
                FOREIGN KEY (setup_id) REFERENCES setups(id)
            )
        ''')
        
        # Statistics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATETIME,
                total_scans INTEGER DEFAULT 0,
                setups_found INTEGER DEFAULT 0,
                trades_taken INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_pl REAL DEFAULT 0,
                win_rate REAL DEFAULT 0,
                avg_risk_reward REAL DEFAULT 0,
                best_setup TEXT,
                worst_setup TEXT
            )
        ''')
        
        # Performance by symbol
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS symbol_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE,
                total_trades INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_pl REAL DEFAULT 0,
                win_rate REAL DEFAULT 0,
                avg_pips REAL DEFAULT 0,
                last_trade DATETIME
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("📊 Database initialized")
    
    def save_setup(self, setup: Dict) -> int:
        """Save a detected setup to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO setups (
                symbol, setup_type, entry_price, entry_low, entry_high,
                stop_loss, take_profit, gap_pips, confidence, session,
                timestamp, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            setup['symbol'],
            setup['type'],
            setup['entry_price'],
            setup['entry_low'],
            setup['entry_high'],
            setup['stop_loss'],
            setup['take_profit'],
            setup['gap_pips'],
            setup['confidence'],
            setup.get('session', 'unknown'),
            setup['timestamp'],
            json.dumps(setup)
        ))
        
        setup_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"💾 Setup saved to database (ID: {setup_id})")
        return setup_id
    
    def update_setup_result(self, setup_id: int, result: str, pl: float):
        """Update setup with trade result"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE setups 
            SET status = ?, profit_loss = ?, trade_result = ?
            WHERE id = ?
        ''', (result, pl, result, setup_id))
        
        conn.commit()
        conn.close()
    
    def get_setups(self, symbol: str = None, limit: int = 100) -> List[Dict]:
        """Get recent setups"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM setups ORDER BY timestamp DESC LIMIT ?"
        params = [limit]
        
        if symbol:
            query = "SELECT * FROM setups WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?"
            params = [symbol, limit]
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_statistics(self, days: int = 7) -> Dict:
        """Get trading statistics for recent period"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get statistics for last N days
        cursor.execute('''
            SELECT 
                COUNT(*) as total_setups,
                SUM(CASE WHEN status = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN status = 'loss' THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN status = 'win' THEN profit_loss ELSE NULL END) as avg_win,
                AVG(CASE WHEN status = 'loss' THEN profit_loss ELSE NULL END) as avg_loss,
                SUM(profit_loss) as total_pl
            FROM setups
            WHERE timestamp >= datetime('now', ?)
        ''', (f'-{days} days',))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            total = row[0] or 0
            wins = row[1] or 0
            losses = row[2] or 0
            win_rate = (wins / total * 100) if total > 0 else 0
            
            return {
                'total_setups': total,
                'wins': wins,
                'losses': losses,
                'win_rate': round(win_rate, 2),
                'avg_win': round(row[3] or 0, 2),
                'avg_loss': round(row[4] or 0, 2),
                'total_pl': round(row[5] or 0, 2)
            }
        
        return {
            'total_setups': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'total_pl': 0
        }
    
    def update_symbol_performance(self, symbol: str, result: str, pips: float, pl: float):
        """Update performance metrics for a symbol"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get existing
        cursor.execute('''
            SELECT total_trades, wins, losses, total_pl FROM symbol_performance
            WHERE symbol = ?
        ''', (symbol,))
        
        row = cursor.fetchone()
        
        if row:
            total_trades, wins, losses, total_pl = row
            total_trades += 1
            wins += 1 if result == 'win' else 0
            losses += 1 if result == 'loss' else 0
            total_pl += pl
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            
            cursor.execute('''
                UPDATE symbol_performance
                SET total_trades = ?, wins = ?, losses = ?, total_pl = ?, win_rate = ?, last_trade = ?
                WHERE symbol = ?
            ''', (total_trades, wins, losses, total_pl, win_rate, datetime.now(), symbol))
        else:
            cursor.execute('''
                INSERT INTO symbol_performance (symbol, total_trades, wins, losses, total_pl, win_rate, last_trade)
                VALUES (?, 1, ?, ?, ?, ?, ?)
            ''', (symbol, 1 if result == 'win' else 0, 0 if result == 'win' else 1, pl, 100 if result == 'win' else 0, datetime.now()))
        
        conn.commit()
        conn.close()