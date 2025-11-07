
import pandas as pd
import os

def load_csv_data(file_path):
    """
    Loads historical data from a specified CSV file path.

    Args:
        file_path (str): The full, absolute path to the CSV file.

    Returns:
        pd.DataFrame: A pandas DataFrame with the loaded and parsed data,
                      or None if the file is not found or an error occurs.
    """
    data_path = file_path # Use the provided full path directly

    try:
        if not os.path.exists(file_path):
            print(f"Error: Data file not found at {file_path}")
            return None

        df = pd.read_csv(file_path, sep='\t', engine='python')

        # Clean column names by removing '<' and '>'
        df.columns = [col.replace('<', '').replace('>', '') for col in df.columns]

        # Handle files with and without a TIME column (like Daily data)
        if 'TIME' in df.columns:
            # Combine DATE and TIME for intraday data
            df['DATETIME'] = pd.to_datetime(df['DATE'] + ' ' + df['TIME'])
        else:
            # Use only DATE for daily data
            df['DATETIME'] = pd.to_datetime(df['DATE'])
        df = df.set_index('DATETIME')

        # Keep only the necessary OHLC and Volume columns
        df = df[['OPEN', 'HIGH', 'LOW', 'CLOSE', 'TICKVOL']]
        df.rename(columns={'TICKVOL': 'VOLUME'}, inplace=True)

        # Ensure all data is numeric, coercing errors
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df.dropna(inplace=True)
        
        print(f"Successfully loaded and parsed {os.path.basename(file_path)}")
        return df

    except Exception as e:
        print(f"An error occurred while processing {file_path}: {e}")
        return None

if __name__ == '__main__':
    # This is a simple test to demonstrate how the function works
    # We will use the M1 data file as requested by the user for testing
    m1_file = 'XAUUSD_M1_202101040105_202510201416.csv'
    
    print(f"Attempting to load data from {m1_file}...")
    data_df = load_csv_data(m1_file)
    
    if data_df is not None:
        print("\nData loaded successfully!")
        print("Data shape:", data_df.shape)
        print("First 5 rows:")
        print(data_df.head())
        print("\nLast 5 rows:")
        print(data_df.tail())
