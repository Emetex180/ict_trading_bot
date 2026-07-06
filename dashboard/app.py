# dashboard/app.py
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
import json
import threading
import webbrowser
import logging
import sys
import os

# Fix the import - add the project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import Database
try:
    from utils.database import Database
except ImportError:
    try:
        from ..utils.database import Database
    except ImportError:
        # Create a dummy Database class if import fails
        class Database:
            def __init__(self):
                pass
            def get_setups(self, symbol=None, limit=50):
                return []
            def get_statistics(self, days=7):
                return {'total_setups': 0, 'win_rate': 0, 'total_pl': 0}

logger = logging.getLogger(__name__)

class Dashboard:
    def __init__(self, scanner=None):
        self.app = Flask(__name__)
        CORS(self.app)
        self.scanner = scanner
        
        # Initialize database (with fallback)
        try:
            self.db = Database()
        except Exception as e:
            logger.error(f"Database error: {e}")
            self.db = Database()  # Use dummy
        
        # Setup routes
        self._setup_routes()
        
    def _setup_routes(self):
        @self.app.route('/')
        def index():
            try:
                return render_template('dashboard.html')
            except Exception as e:
                logger.error(f"Template error: {e}")
                return f"""
                <h1>Dashboard Template Error</h1>
                <p>Make sure dashboard.html exists in templates folder.</p>
                <p>Error: {str(e)}</p>
                """
        
        @self.app.route('/api/status')
        def status():
            try:
                session = "Off Session"
                if self.scanner and hasattr(self.scanner, 'session_manager'):
                    try:
                        session = self.scanner.session_manager.get_current_session()
                    except:
                        pass
                
                return jsonify({
                    'status': 'online',
                    'session': session,
                    'scanning': self.scanner.scan_count if self.scanner else 0,
                    'setups_found': self.scanner.setups_found if self.scanner else 0,
                    'last_scan': self.scanner.last_scan_time.isoformat() if self.scanner and self.scanner.last_scan_time else None,
                    'active_assets': len(self.scanner.ALL_SYMBOLS) if self.scanner and hasattr(self.scanner, 'ALL_SYMBOLS') else 0
                })
            except Exception as e:
                logger.error(f"Status error: {e}")
                return jsonify({'status': 'error', 'error': str(e)})
        
        @self.app.route('/api/setups')
        def get_setups():
            try:
                symbol = request.args.get('symbol')
                limit = int(request.args.get('limit', 50))
                setups = self.db.get_setups(symbol, limit)
                return jsonify(setups)
            except Exception as e:
                logger.error(f"Setups error: {e}")
                return jsonify([])
        
        @self.app.route('/api/statistics')
        def get_statistics():
            try:
                days = int(request.args.get('days', 7))
                stats = self.db.get_statistics(days)
                return jsonify(stats)
            except Exception as e:
                logger.error(f"Statistics error: {e}")
                return jsonify({'total_setups': 0, 'win_rate': 0, 'total_pl': 0})
        
        @self.app.route('/api/symbols')
        def get_symbols():
            try:
                if self.scanner and hasattr(self.scanner, 'ALL_SYMBOLS'):
                    return jsonify(self.scanner.ALL_SYMBOLS)
                # Fallback: try to import from config
                try:
                    from config import ALL_SYMBOLS
                    return jsonify(ALL_SYMBOLS)
                except:
                    return jsonify([])
            except Exception as e:
                logger.error(f"Symbols error: {e}")
                return jsonify([])
        
        @self.app.route('/api/session')
        def get_session():
            try:
                if self.scanner and hasattr(self.scanner, 'session_manager'):
                    session = self.scanner.session_manager.get_current_session()
                    killzone = self.scanner.session_manager.is_killzone()
                    return jsonify({
                        'current_session': session,
                        'is_killzone': killzone,
                        'active_sessions': ['asian', 'london', 'new_york', 'sweet_spot', 'afternoon', 'power_hour']
                    })
                return jsonify({
                    'current_session': 'Off Session',
                    'is_killzone': False,
                    'active_sessions': []
                })
            except Exception as e:
                logger.error(f"Session error: {e}")
                return jsonify({
                    'current_session': 'Error',
                    'is_killzone': False,
                    'active_sessions': []
                })
    
    def run(self, host='127.0.0.1', port=5000):
        """Run the dashboard server"""
        try:
            # Try to open browser
            webbrowser.open(f'http://localhost:{port}')
        except:
            pass
        
        logger.info(f"Dashboard starting on http://{host}:{port}")
        
        # Run Flask app
        try:
            self.app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
        except OSError as e:
            if "Address already in use" in str(e):
                logger.error(f"Port {port} is already in use!")
                logger.info(f"Try using a different port, e.g., dashboard.run(port=5001)")
            raise
        except Exception as e:
            logger.error(f"Dashboard error: {e}")
            raise