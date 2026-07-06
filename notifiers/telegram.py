# notifiers/telegram.py
import aiohttp
import asyncio
from typing import Dict, List, Optional  # <-- ADD THIS
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_ids: List[str]):
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
    async def send_alert(self, setup: Dict) -> bool:
        """Send setup alert via Telegram"""
        try:
            # Build message
            message = self._build_message(setup)
            
            # Send to all chat IDs
            success = True
            for chat_id in self.chat_ids:
                try:
                    await self._send_message(chat_id, message)
                except Exception as e:
                    logger.error(f"Error sending to chat {chat_id}: {e}")
                    success = False
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
            return False
    
    def _build_message(self, setup: Dict) -> str:
        """Build formatted message with macro session context"""
        emoji = "✅" if setup['type'] == 'BUY' else "🔴"
        
        # Session emojis
        session_emojis = {
            'asian': "🌏",
            'london': "🇬🇧",
            'new_york': "🗽",
            'sweet_spot': "🎯",
            'afternoon': "🌆",
            'power_hour': "⚡"
        }
        session_emoji = session_emojis.get(setup.get('session', ''), "🕐")
        
        # Macro status indicators
        macro = setup.get('macro_status', {})
        status_emojis = {
            'active': '🟢',
            'pre_session': '🔵',
            'post_session': '🟡',
            'outside': '⚪'
        }
        status_emoji = status_emojis.get(macro.get('status', ''), '⚪')
        
        # Build message
        message = f"""
{emoji} <b>{setup['type']} SETUP DETECTED</b>
{'-'*45}

<code>{setup['symbol']}</code>  {session_emoji} {setup.get('session', 'Unknown')}

<b>⏰ Session Status:</b>
• {status_emoji} {macro.get('status', 'unknown').upper()}
• Priority: {setup.get('session_priority', 0)}/10
• Window: {macro.get('macro_start', 'N/A')} - {macro.get('macro_end', 'N/A')} ET

<b>📊 Entry Zone:</b>
<code>{setup['entry_low']:.5f} - {setup['entry_high']:.5f}</code>

<b>💹 Entry Price:</b> {setup['entry_price']:.5f}
<b>🛑 Stop Loss:</b>  {setup['stop_loss']:.5f}
<b>🎯 Take Profit:</b> {setup['take_profit']:.5f}

<b>📐 Risk/Reward:</b> 1:{setup['risk_reward_ratio']}
<b>📏 Gap Size:</b>    {setup['gap_pips']:.1f} pips
<b>🎯 Confidence:</b>   {setup['confidence']}%

<b>⏰ Time:</b> {setup['timestamp'][:19]} UTC
<b>🔄 Timeframe:</b> {setup['timeframe']}

<b>📈 Market Phase:</b> {setup.get('market_phase', 'N/A')}
<b>📊 Daily Range:</b> {setup.get('daily_range', 'N/A')} pips

<b>💼 Position Size:</b> {setup.get('position_size', 0):.2f} units

<b>📊 Confidence Bar:</b>
{self._get_confidence_bar(setup['confidence'])}
"""
        return message
    
    def _get_confidence_bar(self, confidence: int) -> str:
        """Create visual confidence bar"""
        filled = int(confidence / 10)
        return "█" * filled + "░" * (10 - filled)
    
    async def _send_message(self, chat_id: str, message: str) -> bool:
        """Send message to Telegram"""
        url = f"{self.base_url}/sendMessage"
        
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Telegram API error: {error_text}")
                    return False
                return True
    
    async def send_test_message(self, chat_id: str) -> bool:
        """Send a test message"""
        message = """
🚀 <b>Bot is Running!</b>

Scanner is active and monitoring:
• 20+ currency pairs
• Major indices
• Crypto assets

Sessions: Asian, London, New York, NY Afternoon, Power Hour

<i>You will receive alerts for valid setups.</i>
"""
        return await self._send_message(chat_id, message)
    
    async def send_statistics(self, chat_id: str, stats: Dict):
        """Send daily/weekly statistics"""
        message = f"""
📊 <b>Bot Statistics</b>

<b>Total Scans:</b> {stats.get('total_scans', 0)}
<b>Setups Found:</b> {stats.get('setups_found', 0)}
<b>Win Rate:</b> {stats.get('win_rate', 'N/A')}%
<b>Total P/L:</b> {stats.get('total_pl', 'N/A')}

<b>Top Performers:</b>
{self._format_top_performers(stats.get('top_performers', []))}
"""
        await self._send_message(chat_id, message)
    
    def _format_top_performers(self, performers: List) -> str:
        """Format top performers for display"""
        if not performers:
            return "No data yet"
        
        lines = []
        for p in performers[:5]:
            lines.append(f"• {p['symbol']}: {p['wins']} wins / {p['losses']} losses")
        return "\n".join(lines)