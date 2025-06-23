import os
import sys
from sqlalchemy import create_engine, text
from datetime import datetime

# Connect to the database
db_path = os.path.join(os.path.dirname(__file__), 'instance', 'portfolio.db')
engine = create_engine(f'sqlite:///{db_path}')
conn = engine.connect()

print("Connected to database:", db_path)

try:
    # Get all users
    users = conn.execute(text("SELECT id, email FROM user")).fetchall()
    print(f"Found {len(users)} users")
    
    for user in users:
        user_id = user[0]
        email = user[1]
        print(f"\nProcessing user: {email} (ID: {user_id})")
        
        # Get all stocks for this user
        stocks = conn.execute(
            text("SELECT id, ticker, quantity, purchase_date FROM stock WHERE user_id = :user_id ORDER BY id"),
            {"user_id": user_id}
        ).fetchall()
        
        print(f"  Found {len(stocks)} stocks")
        
        # Track unique tickers
        seen_tickers = {}
        duplicates = []
        
        for stock in stocks:
            stock_id = stock[0]
            ticker = stock[1]
            quantity = stock[2]
            date_added = stock[3]
            
            if ticker in seen_tickers:
                # This is a duplicate
                duplicates.append(stock_id)
                print(f"  Duplicate found: {ticker} (ID: {stock_id}, Quantity: {quantity})")
            else:
                # First time seeing this ticker
                seen_tickers[ticker] = stock_id
                print(f"  Keeping: {ticker} (ID: {stock_id}, Quantity: {quantity})")
        
        # Delete duplicates if any found
        if duplicates:
            print(f"  Removing {len(duplicates)} duplicate stocks...")
            for dup_id in duplicates:
                conn.execute(
                    text("DELETE FROM stock WHERE id = :id"),
                    {"id": dup_id}
                )
            conn.commit()
            print("  Duplicates removed successfully!")
        else:
            print("  No duplicates found for this user.")
    
    print("\nCleanup completed successfully!")
    
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()
    sys.exit(1)
    
finally:
    conn.close()
