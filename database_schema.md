# ApesTogether Stock Portfolio App - Database Schema

This document describes the database schema for the ApesTogether stock portfolio application. It serves as a reference for developers working on the application.

## Tables

### User

Stores user account information.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | Primary Key | Unique identifier for the user |
| username | String(80) | Unique, Not Null | User's chosen username |
| email | String(120) | Unique, Not Null | User's email address |
| password_hash | String(200) | Not Null | Hashed password |
| created_at | DateTime | Default: UTC now | When the user account was created |
| stripe_customer_id | String(120) | Nullable | Stripe customer ID for payments |

### Stock

Stores information about stocks in user portfolios.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | Primary Key | Unique identifier for the stock entry |
| user_id | Integer | Foreign Key (user.id) | Reference to the user who owns this stock |
| ticker | String(10) | Not Null | Stock ticker symbol |

### Transaction

Stores user transaction history.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | Primary Key | Unique identifier for the transaction |
| user_id | Integer | Foreign Key (user.id) | Reference to the user who made this transaction |

### Subscription

Stores user subscription information.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | Integer | Primary Key | Unique identifier for the subscription |
| user_id | Integer | Foreign Key (user.id) | Reference to the subscribed user |

## Relationships

- A User has many Stocks (one-to-many)
- A User has many Transactions (one-to-many)
- A User has many Subscriptions (one-to-many)

## Migration History

### July 2025 - Added created_at column

- Added `created_at` column to User table
- Set default value to current timestamp
- Applied via custom migration script
