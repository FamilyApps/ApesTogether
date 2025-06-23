# Admin Transaction Management

This document explains how to use the new transaction management functionality in the admin interface.

## Overview

The enhanced admin interface now allows you to:

1. **Add manual transactions** with custom dates and prices
2. **Edit existing transactions** including changing share quantities, prices, and dates
3. **Delete transactions** while automatically updating stock positions
4. **View transaction history** in a sortable, searchable table

## How It Works

### Adding Manual Transactions

1. Navigate to a user's detail page in the admin interface
2. Click "Add Manual Transaction" button
3. Enter the transaction details:
   - Stock symbol
   - Transaction type (buy/sell)
   - Number of shares
   - Price per share
   - Transaction date
   - Optional notes

When you add a transaction, the system will automatically:
- Update the user's stock position
- Create a record of the transaction with the custom price
- Use your manually entered price instead of pulling from Alpha Vantage

### Editing Transactions

1. Find the transaction in the user's transaction history
2. Click the "Edit" button
3. Modify any of the following:
   - Number of shares
   - Price per share
   - Transaction date
   - Notes

When you save changes, the system will:
- Recalculate the user's stock position based on your changes
- Update the transaction record

### Deleting Transactions

1. Edit a transaction
2. Click the "Delete Transaction" button
3. Confirm the deletion

The system will:
- Remove the transaction from the database
- Update the user's stock position to reflect the removal

## Database Changes

A new `Transaction` model has been added with the following fields:
- `id`: Primary key
- `user_id`: Foreign key to User
- `symbol`: Stock symbol
- `shares`: Number of shares
- `price`: Price per share
- `transaction_type`: 'buy' or 'sell'
- `date`: Transaction date
- `notes`: Optional notes

## Technical Implementation

When the application starts, it will automatically check if the Transaction table exists and create it if needed. You can also manually run the migration script:

```
python migrations/add_transactions_table.py
```

## Best Practices

1. **Use notes field** to document why you're making manual adjustments
2. **Be careful with dates** - entering historical dates will affect portfolio performance calculations
3. **Check stock positions** after making changes to ensure they're accurate
