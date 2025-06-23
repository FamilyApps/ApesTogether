# Admin Interface Documentation

## Overview

The admin interface provides administrative capabilities for managing users, stocks, transactions, and subscriptions. It's designed to be secure, accessible only to authorized administrators, and provides full CRUD operations for managing stock transactions.

## Access Control

- **Production**: Only users with the admin email (`fordutilityapps@gmail.com`) can access the admin interface
- **Development**: Any authenticated user can access the admin interface when `FLASK_DEBUG=development`

## Features

### Dashboard

The dashboard provides an overview of key metrics:
- Total number of users
- Total number of stocks
- Total number of transactions
- Total number of subscriptions

### User Management

- View a list of all users
- View detailed information about each user
- See user's subscription status
- Access user's transaction history

### Transaction Management

- View all transactions for a specific user
- Add new transactions manually
- Edit existing transactions
- Delete transactions
- Filter and sort transactions

## Database Structure

The admin interface interacts with the following database tables:
- `user`: User account information
- `stock`: Stock holdings
- `stock_transaction`: Transaction history (renamed from `transaction` to avoid SQLite reserved keyword issues)
- `subscription`: Subscription relationships between users

## Implementation Details

### Models

All database models are defined in `models.py`:
- `User`: User account information and authentication
- `Stock`: Stock holdings information
- `Transaction`: Stock transaction history
- `Subscription`: Subscription relationships

### Routes

Admin routes are defined in `admin_interface.py` and registered as a Flask blueprint:
- `/admin/`: Dashboard
- `/admin/users`: User list
- `/admin/users/<user_id>`: User details
- `/admin/users/<user_id>/transactions`: User transactions
- `/admin/users/<user_id>/transactions/add`: Add transaction
- `/admin/users/<user_id>/transactions/<transaction_id>/edit`: Edit transaction
- `/admin/users/<user_id>/transactions/<transaction_id>/delete`: Delete transaction

### Templates

Admin templates are stored in the `templates/admin/` directory:
- `dashboard.html`: Admin dashboard
- `user_list.html`: List of all users
- `user_detail.html`: User details and transactions

## Security Considerations

1. **Authentication**: All admin routes require authentication
2. **Authorization**: Only users with the admin email can access admin routes in production
3. **CSRF Protection**: All forms include CSRF protection
4. **Input Validation**: All user inputs are validated before processing

## Maintenance

### Adding New Admin Features

1. Add new routes to `admin_interface.py`
2. Create or update templates in `templates/admin/`
3. Update models in `models.py` if necessary
4. Create migration scripts for any database changes

### Troubleshooting

- **Database Issues**: Check that all required tables exist and have the correct structure
- **Access Issues**: Verify that the user has the correct admin email
- **Template Issues**: Check for template rendering errors in the application logs
