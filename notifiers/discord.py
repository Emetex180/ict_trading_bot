# notifiers/discord.py
import aiohttp
from typing import Dict, Optional  # <-- ADD THIS
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class DiscordNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        
    async def send_alert(self, setup: Dict) -> bool:
        """Send setup alert via Discord webhook"""
        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured")
            return False
        
        try:
            embed = self._build_embed(setup)
            payload = {'embeds': [embed]}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status != 204:
                        error_text = await response.text()
                        logger.error(f"Discord webhook error: {error_text}")
                        return False
                    return True
                    
        except Exception as e:
            logger.error(f"Error sending Discord alert: {e}")
            return False
    
    def _build_embed(self, setup: Dict) -> Dict:
        """Build Discord embed"""
        # Color based on type
        color = 0x00ff00 if setup['type'] == 'BUY' else 0xff0000
        
        # Emoji
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
        
        # Macro status
        macro = setup.get('macro_status', {})
        status_emojis = {
            'active': '🟢',
            'pre_session': '🔵',
            'post_session': '🟡',
            'outside': '⚪'
        }
        status_emoji = status_emojis.get(macro.get('status', ''), '⚪')
        
        # Build embed
        embed = {
            'title': f"{emoji} {setup['type']} SETUP - {setup['symbol']}",
            'color': color,
            'timestamp': setup['timestamp'],
            'fields': [
                {
                    'name': '⏰ Session Status',
                    'value': f"{status_emoji} {macro.get('status', 'unknown').upper()}\nPriority: {setup.get('session_priority', 0)}/10",
                    'inline': False
                },
                {
                    'name': '📊 Entry Zone',
                    'value': f"`{setup['entry_low']:.5f} - {setup['entry_high']:.5f}`",
                    'inline': False
                },
                {
                    'name': '💹 Entry Price',
                    'value': f"`{setup['entry_price']:.5f}`",
                    'inline': True
                },
                {
                    'name': '🛑 Stop Loss',
                    'value': f"`{setup['stop_loss']:.5f}`",
                    'inline': True
                },
                {
                    'name': '🎯 Take Profit',
                    'value': f"`{setup['take_profit']:.5f}`",
                    'inline': True
                },
                {
                    'name': '📐 Risk/Reward',
                    'value': f"1:{setup['risk_reward_ratio']}",
                    'inline': True
                },
                {
                    'name': '📏 Gap Size',
                    'value': f"{setup['gap_pips']:.1f} pips",
                    'inline': True
                },
                {
                    'name': '🎯 Confidence',
                    'value': f"{setup['confidence']}%",
                    'inline': True
                },
                {
                    'name': f'{session_emoji} Session',
                    'value': setup.get('session', 'Unknown'),
                    'inline': True
                },
                {
                    'name': '📈 Market Phase',
                    'value': setup.get('market_phase', 'N/A'),
                    'inline': True
                },
                {
                    'name': '💼 Position Size',
                    'value': f"{setup.get('position_size', 0):.2f} units",
                    'inline': True
                }
            ],
            'footer': {
                'text': f"ICT Strategy Scanner • {setup['timeframe']}"
            }
        }
        
        return embed