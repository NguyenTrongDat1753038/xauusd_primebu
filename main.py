import sys
import os

# Add the project root to the Python path to allow imports from 'src'
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

from src.live_trader import main_trader_loop

def main():
    """
    Main entry point for the application.
    This function starts the live trading bot.
    """
    print("--- Starting Live Trading Bot ---")
    main_trader_loop()

if __name__ == "__main__":
    main()
