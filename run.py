# run.py
#!/usr/bin/env python3
"""
ICT Trading Bot - Main Entry Point
Run with: python run.py
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from main import main

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║   🚀 ICT TRADING BOT - Multi-Asset Scanner              ║
    ║                                                          ║
    ║   Assets: Forex, Indices, Crypto                        ║
    ║   Sessions: Asian, London, NY, NY Afternoon, Power Hour ║
    ║   Notifications: Telegram, Discord                     ║
    ║   Dashboard: http://localhost:5000                     ║
    ║                                                          ║
    ║   Press Ctrl+C to stop                                  ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)