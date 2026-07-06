# main.py (Updated with Macro Sessions)
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time

from config import (
    ALL_SYMBOLS, ASSET_CATEGORIES, MACRO_CONFIG,
    TRADING_CONFIG, TELEGRAM_CONFIG, DISCORD_CONFIG
)
from detectors.liquidity_purge import LiquidityPurgeDetector
from detectors.cisd import CISDDetector
from detectors.fvg import FVGDetector
from data.fetcher import MarketDataFetcher
from notifiers.telegram import TelegramNotifier
from notifiers.discord import DiscordNotifier
from utils.sessions import SessionManager
from utils.database import Database
from utils.logger import setup_logger

logger = setup_logger(__name__)

class ICTStrategyScanner:
    def __init__(self):
        """Initialize all components"""
        self.liquidity_detector = LiquidityPurgeDetector(
            lookback=TRADING_CONFIG['liquidity_lookback']
        )
        self.cisd_detector = CISDDetector(
            lookback=TRADING_CONFIG['cisd_lookback']
        )
        self.fvg_detector = FVGDetector(
            min_gap=TRADING_CONFIG['min_gap_pips'],
            max_gap=TRADING_CONFIG['max_gap_pips']
        )
        
        self.data_fetcher = MarketDataFetcher()
        self.session_manager = SessionManager()
        self.database = Database()
        
        # Initialize notifiers
        self.telegram = TelegramNotifier(
            TELEGRAM_CONFIG['bot_token'],
            TELEGRAM_CONFIG['chat_ids']
        )
        self.discord = DiscordNotifier(
            DISCORD_CONFIG['webhook_url']
        )
        
        # Statistics
        self.scan_count = 0
        self.setups_found = 0
        self.last_scan_time = None
        self.session_stats = {session: 0 for session in self.session_manager.sessions.keys()}
        
        logger.info("🚀 ICT Strategy Scanner initialized")
        logger.info(f"📊 Monitoring {len(ALL_SYMBOLS)} assets")
        logger.info(f"🕐 Macro windows: {MACRO_CONFIG['minutes_before']}min before, {MACRO_CONFIG['minutes_after']}min after")
        logger.info(f"🔄 Macro-only scanning: {MACRO_CONFIG['scan_during_macro_only']}")

    async def scan_asset(self, symbol: str) -> Optional[Dict]:
        """Scan a single asset for setups"""
        try:
            # Check if we should scan this asset based on session
            if not self.session_manager.should_scan(symbol):
                return None
            
            # Get active sessions for this asset
            active_sessions = self.session_manager.get_active_sessions(symbol)
            if not active_sessions:
                return None
            
            # Get the best (highest priority) active session
            best_session = self.session_manager.get_best_active_session(symbol)
            
            # Fetch data for all timeframes
            data_1h = await self.data_fetcher.fetch_data(
                symbol, TRADING_CONFIG['liquidity_timeframe'], lookback=100
            )
            data_5m = await self.data_fetcher.fetch_data(
                symbol, TRADING_CONFIG['cisd_timeframe'], lookback=100
            )
            data_1m = await self.data_fetcher.fetch_data(
                symbol, TRADING_CONFIG['fvg_timeframe'], lookback=100
            )
            
            if not all([data_1h is not None, data_5m is not None, data_1m is not None]):
                logger.warning(f"⚠️ Incomplete data for {symbol}")
                return None
            
            # Step 1: Detect Liquidity Purge on 1H
            purge = self.liquidity_detector.detect(data_1h)
            if not purge or not purge['type']:
                return None
            
            # Step 2: Check CISD on 5M
            if not self.cisd_detector.detect(data_5m, purge['type']):
                return None
            
            # Step 3: Check FVG on 1M
            fvg = self.fvg_detector.detect(data_1m, purge['type'])
            if not fvg:
                return None
            
            # Step 4: Calculate entry and risk levels
            entry_price = self.calculate_entry_price(purge, fvg)
            stop_loss = self.calculate_stop_loss(purge, fvg)
            take_profit = self.calculate_take_profit(entry_price, stop_loss, purge['type'])
            
            # Get macro window status
            macro_status = self.get_macro_status(symbol, best_session)
            
            # Build setup object
            setup = {
                'symbol': symbol,
                'type': 'BUY' if purge['type'] == 'buy' else 'SELL',
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'timeframe': '1H/5M/1M',
                'session': best_session,
                'session_priority': self.session_manager.get_session_priority(best_session),
                'macro_status': macro_status,
                
                # Entry details
                'entry_price': entry_price,
                'entry_low': fvg['fvg_low'],
                'entry_high': fvg['fvg_high'],
                'gap_pips': fvg['gap_pips'],
                
                # Risk Management
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk_reward_ratio': TRADING_CONFIG['risk_reward_ratio'],
                'position_size': self.calculate_position_size(stop_loss, entry_price),
                
                # Detector outputs
                'purge_level': purge['level'],
                'purge_strength': purge.get('strength', 0.5),
                'fvg_details': fvg,
                
                # Market context
                'market_phase': self.get_market_phase(data_1h),
                'daily_range': self.calculate_daily_range(data_1h),
                
                # Confidence score (now includes session priority)
                'confidence': self.calculate_confidence(purge, fvg, best_session)
            }
            
            # Update session stats
            if best_session in self.session_stats:
                self.session_stats[best_session] += 1
            
            return setup
            
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")
            return None

    def get_macro_status(self, symbol: str, session_name: str) -> Dict:
        """Get macro window status for the current time"""
        ny_time = self.session_manager.get_current_ny_time()
        session = self.session_manager.sessions.get(session_name)
        
        if not session:
            return {'status': 'unknown', 'macro_active': False}
        
        current_minutes = ny_time.hour * 60 + ny_time.minute
        start_minutes = session.start_hour * 60 + session.start_minute
        end_minutes = session.end_hour * 60 + session.end_minute
        
        macro_start = start_minutes - MACRO_CONFIG['minutes_before']
        macro_end = end_minutes + MACRO_CONFIG['minutes_after']
        
        # Determine if in macro window
        is_in_macro = False
        status = 'outside'
        
        if macro_start <= current_minutes < start_minutes:
            is_in_macro = True
            status = 'pre_session'
            minutes_until = start_minutes - current_minutes
        elif start_minutes <= current_minutes < end_minutes:
            is_in_macro = True
            status = 'active'
            minutes_until = 0
        elif end_minutes <= current_minutes < macro_end:
            is_in_macro = True
            status = 'post_session'
            minutes_until = 0
        else:
            is_in_macro = False
            status = 'outside'
            # Calculate minutes until next session
            if current_minutes < start_minutes:
                minutes_until = start_minutes - current_minutes
            else:
                minutes_until = (1440 - current_minutes) + start_minutes
        
        return {
            'status': status,
            'macro_active': is_in_macro,
            'minutes_until_start': max(0, start_minutes - current_minutes) if status != 'active' else 0,
            'minutes_remaining': max(0, end_minutes - current_minutes) if status == 'active' else 0,
            'session_start': f"{session.start_hour:02d}:{session.start_minute:02d}",
            'session_end': f"{session.end_hour:02d}:{session.end_minute:02d}",
            'macro_start': f"{macro_start // 60:02d}:{macro_start % 60:02d}",
            'macro_end': f"{macro_end // 60:02d}:{macro_end % 60:02d}"
        }

    def calculate_entry_price(self, purge: Dict, fvg: Dict) -> float:
        """Calculate optimal entry price"""
        if fvg['type'] == 'bullish':
            return (fvg['fvg_low'] + fvg['fvg_high']) / 2
        else:
            return (fvg['fvg_low'] + fvg['fvg_high']) / 2

    def calculate_stop_loss(self, purge: Dict, fvg: Dict) -> float:
        """Calculate stop loss based on setup"""
        if fvg['type'] == 'bullish':
            return fvg['fvg_low'] - (fvg['fvg_high'] - fvg['fvg_low']) * 0.5
        else:
            return fvg['fvg_high'] + (fvg['fvg_high'] - fvg['fvg_low']) * 0.5

    def calculate_take_profit(self, entry: float, stop: float, setup_type: str) -> float:
        """Calculate take profit with risk-reward ratio"""
        risk = abs(entry - stop)
        rr = TRADING_CONFIG['risk_reward_ratio']
        
        if setup_type == 'BUY':
            return entry + (risk * rr)
        else:
            return entry - (risk * rr)

    def calculate_position_size(self, stop_loss: float, entry: float) -> float:
        """Calculate position size based on risk management"""
        account_balance = 10000
        risk_amount = account_balance * TRADING_CONFIG['max_risk_per_trade']
        risk_pips = abs(entry - stop_loss)
        position_size = risk_amount / risk_pips if risk_pips > 0 else 0
        return round(position_size, 2)

    def get_market_phase(self, data) -> str:
        """Determine market phase"""
        # Simplified - would use ATR, ADX, etc.
        return "Trending"

    def calculate_daily_range(self, data) -> float:
        """Calculate daily range in pips"""
        return 50.0

    def calculate_confidence(self, purge: Dict, fvg: Dict, session: str) -> int:
        """Calculate confidence score (1-100) with session weighting"""
        score = 60  # Base score
        
        # Add for purge strength
        if purge.get('strength', 0) > 0.7:
            score += 15
        elif purge.get('strength', 0) > 0.5:
            score += 10
        
        # Add for FVG quality
        if fvg['gap_pips'] > 10 and fvg['gap_pips'] < 30:
            score += 10
        elif fvg['gap_pips'] > 5 and fvg['gap_pips'] < 50:
            score += 5
        
        # Add for session priority
        priority = self.session_manager.get_session_priority(session)
        score += priority * 2
        
        # Macro window bonus
        if fvg.get('macro_status', {}).get('status') == 'active':
            score += 5
        elif fvg.get('macro_status', {}).get('status') in ['pre_session', 'post_session']:
            score += 3
        
        return min(score, 100)

    async def scan_all_assets(self):
        """Scan all assets in watchlist with session filtering"""
        logger.info("🔄 Starting full market scan...")
        self.scan_count += 1
        self.last_scan_time = datetime.utcnow()
        
        # Group assets by category for better session management
        assets_by_category = {}
        for symbol in ALL_SYMBOLS:
            category = ASSET_CATEGORIES.get(symbol, 'forex')
            if category not in assets_by_category:
                assets_by_category[category] = []
            assets_by_category[category].append(symbol)
        
        setups = []
        
        # Scan each category with its specific sessions
        for category, symbols in assets_by_category.items():
            logger.info(f"📂 Scanning {category} assets ({len(symbols)} symbols)")
            
            for symbol in symbols:
                setup = await self.scan_asset(symbol)
                if setup:
                    setups.append(setup)
        
        if setups:
            self.setups_found += len(setups)
            logger.info(f"🎯 Found {len(setups)} setups across {len(setups)} assets!")
            
            # Send notifications with session context
            for setup in setups:
                await self.send_notifications(setup)
                self.database.save_setup(setup)
                
                # Log the session status
                session_name = setup['session']
                macro_status = setup['macro_status']['status']
                logger.info(f"📊 {setup['symbol']} - {setup['type']} setup in {session_name} session ({macro_status})")
        else:
            logger.info("❌ No setups found in this scan")
        
        return setups

    async def send_notifications(self, setup: Dict):
        """Send notifications to all configured channels"""
        # Send to Telegram with macro status
        await self.telegram.send_alert(setup)
        
        # Send to Discord
        await self.discord.send_alert(setup)
        
        # Print to console with session context
        self.print_setup(setup)

    def print_setup(self, setup: Dict):
        """Print setup to console with session and macro status"""
        emoji = "✅" if setup['type'] == 'BUY' else "🔴"
        color = "\033[92m" if setup['type'] == 'BUY' else "\033[91m"
        reset = "\033[0m"
        
        # Session emojis
        session_emojis = {
            'asian': '🌏',
            'london': '🇬🇧',
            'new_york': '🗽',
            'sweet_spot': '🎯',
            'afternoon': '🌆',
            'power_hour': '⚡'
        }
        session_emoji = session_emojis.get(setup['session'], '🕐')
        
        # Macro status indicators
        macro_status = setup['macro_status']
        status_indicators = {
            'active': '🟢 LIVE',
            'pre_session': '🔵 WARMUP',
            'post_session': '🟡 COOLDOWN',
            'outside': '⚪ OFFSESSION'
        }
        status_indicator = status_indicators.get(macro_status['status'], '⚪')
        
        print(f"\n{color}{'='*70}{reset}")
        print(f"{emoji} {color}{setup['type']} SETUP DETECTED{reset}")
        print(f"{'='*70}")
        print(f"Symbol:       {setup['symbol']}")
        print(f"Session:      {session_emoji} {setup['session']} ({status_indicator})")
        print(f"Priority:     {setup['session_priority']}/10")
        print(f"Confidence:   {setup['confidence']}%")
        
        # Macro window details
        print(f"\n📊 Macro Window:")
        print(f"  Status:     {macro_status['status'].upper()}")
        print(f"  Window:     {macro_status['macro_start']} - {macro_status['macro_end']} ET")
        print(f"  Session:    {macro_status['session_start']} - {macro_status['session_end']} ET")
        if macro_status['status'] == 'active':
            print(f"  Remaining:  {macro_status['minutes_remaining']} min")
        elif macro_status['status'] == 'pre_session':
            print(f"  Starts in:  {macro_status['minutes_until_start']} min")
        
        # Entry details
        print(f"\n📈 Entry Zone:   {setup['entry_low']} - {setup['entry_high']}")
        print(f"💹 Entry Price:  {setup['entry_price']}")
        print(f"🛑 Stop Loss:    {setup['stop_loss']}")
        print(f"🎯 Take Profit:  {setup['take_profit']}")
        print(f"📐 Risk/Reward:  1:{setup['risk_reward_ratio']}")
        print(f"💼 Position Size: {setup['position_size']} units")
        print(f"📏 Gap Size:     {setup['gap_pips']:.1f} pips")
        print(f"⏰ Time:         {setup['timestamp']}")
        print(f"{'='*70}\n")

    async def run(self):
        """Main scanner loop with session-aware scheduling"""
        logger.info("🔄 Scanner started. Press Ctrl+C to stop.")
        logger.info(f"🕐 Current New York time: {self.session_manager.get_current_ny_time().strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        # Start dashboard in background
        from dashboard.app import Dashboard
        dashboard = Dashboard(self)
        asyncio.create_task(dashboard.run())
        
        while True:
            try:
                ny_time = self.session_manager.get_current_ny_time()
                
                # Check if we should scan based on active sessions
                active_sessions = self.session_manager.get_active_sessions()
                
                if active_sessions:
                    logger.info(f"🟢 Active sessions: {', '.join(active_sessions)}")
                    await self.scan_all_assets()
                else:
                    # Find next session
                    next_session = self.session_manager.get_next_session_start()
                    if next_session:
                        wait_minutes = next_session['wait_minutes'] - MACRO_CONFIG['minutes_before']
                        if wait_minutes > 0:
                            logger.info(f"⏰ Next session: {next_session['name']} starts at {next_session['start_time']} ET (in {wait_minutes:.0f} min)")
                            
                            # Sleep until macro window starts
                            if wait_minutes > 5:
                                await asyncio.sleep(60)  # Check every minute
                                continue
                
                # Update statistics
                logger.info(f"📊 Stats: {self.scan_count} scans, {self.setups_found} total setups found")
                
                # Wait before next scan
                await asyncio.sleep(60)
                
            except KeyboardInterrupt:
                logger.info("🛑 Scanner stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(60)

# =================================================
# ENTRY POINT
# =================================================

async def main():
    scanner = ICTStrategyScanner()
    await scanner.run()

if __name__ == "__main__":
    asyncio.run(main())