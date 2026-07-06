# dashboard/app.py
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
import json
import threading
import webbrowser
import logging
from ..utils.database import Database

logger = logging.getLogger(__name__)

class Dashboard:
    def __init__(self, scanner=None):
        self.app = Flask(__name__)
        CORS(self.app)
        self.scanner = scanner
        self.db = Database()
        
        # Setup routes
        self._setup_routes()
        
    def _setup_routes(self):
        @self.app.route('/')
        def index():
            return render_template('dashboard.html')
        
        @self.app.route('/api/status')
        def status():
            return jsonify({
                'status': 'online',
                'scanning': self.scanner.scan_count if self.scanner else 0,
                'setups_found': self.scanner.setups_found if self.scanner else 0,
                'last_scan': self.scanner.last_scan_time.isoformat() if self.scanner and self.scanner.last_scan_time else None,
                'active_assets': len(self.scanner.ALL_SYMBOLS) if self.scanner else 0
            })
        
        @self.app.route('/api/setups')
        def get_setups():
            symbol = request.args.get('symbol')
            limit = int(request.args.get('limit', 50))
            setups = self.db.get_setups(symbol, limit)
            return jsonify(setups)
        
        @self.app.route('/api/statistics')
        def get_statistics():
            days = int(request.args.get('days', 7))
            stats = self.db.get_statistics(days)
            return jsonify(stats)
        
        @self.app.route('/api/symbols')
        def get_symbols():
            if self.scanner:
                return jsonify(self.scanner.ALL_SYMBOLS)
            return jsonify([])
        
        @self.app.route('/api/session')
        def get_session():
            if self.scanner:
                session = self.scanner.session_manager.get_current_session()
                killzone = self.scanner.session_manager.is_killzone()
                return jsonify({
                    'current_session': session,
                    'is_killzone': killzone,
                    'active_sessions': self.scanner.ALLOWED_SESSIONS
                })
            return jsonify({})
    
    def run(self, host='0.0.0.0', port=5000):
        """Run the dashboard server"""
        # Open browser
        webbrowser.open(f'http://localhost:{port}')
        
        # Run Flask app
        self.app.run(host=host, port=port, debug=False, use_reloader=False)