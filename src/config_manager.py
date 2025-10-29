
import json
import os
import re

def get_config():
    """
    Reads the configuration file and returns it as a dictionary.

    The path is constructed relative to this file's location to ensure
    it works regardless of where the script is run from.
    """
    # Construct the absolute path to the config file
    # config.json is in ../configs/ from the src/ directory
    config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'config.json')
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            # Read the file and remove comments before parsing
            content = f.read()
            # Remove all C-style comments (// and /* */)
            content = re.sub(r'//.*?\n|/\*.*?\*/', '', content, flags=re.S)
            config = json.loads(content)
        return config
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {config_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from the configuration file at {config_path}")
        return None

if __name__ == '__main__':
    # This is a simple test to show how the function works
    config = get_config()
    if config:
        print("Configuration loaded successfully!")
        print("Trading Symbol:", config.get('trading', {}).get('symbol'))
        print("EMA Periods:", config.get('strategy', {}).get('ema_periods'))
