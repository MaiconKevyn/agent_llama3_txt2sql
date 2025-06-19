import pandas as pd
import sqlite3
from pathlib import Path

def create_database_from_csv():
    """Create SQLite database from CSV file"""
    
    # Read CSV file
    csv_path = Path("data/dados_sus3.csv")
    df = pd.read_csv(csv_path)
    
    # Connect to SQLite database
    db_path = "sus_database.db"
    conn = sqlite3.connect(db_path)
    
    # Create table from DataFrame
    df.to_sql('sus_data', conn, if_exists='replace', index=False)
    
    # Get table info
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(sus_data)")
    columns = cursor.fetchall()
    
    print(f"Database created successfully at {db_path}")
    print(f"Table 'sus_data' has {len(df)} records")
    print("Columns:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
    
    conn.close()
    return db_path

if __name__ == "__main__":
    create_database_from_csv()