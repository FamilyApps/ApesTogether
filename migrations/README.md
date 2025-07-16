# Database Migrations

This directory contains database migration scripts for the ApesTogether stock portfolio application.

## Migration Process

For any database schema changes, follow this process:

1. **Create a migration script** in this directory with a descriptive name and timestamp
2. **Test the migration** in a development environment
3. **Document the changes** in the database_schema.md file
4. **Deploy the migration** to production

## Using Flask-Migrate

The application now uses Flask-Migrate for database migrations. To create and apply migrations:

### Creating a new migration

```bash
# In your development environment
cd /path/to/stock-portfolio-app
export FLASK_APP=api/index.py
flask db migrate -m "Description of changes"
```

This will create a new migration script in the migrations directory.

### Applying migrations

```bash
# In your development environment
cd /path/to/stock-portfolio-app
export FLASK_APP=api/index.py
flask db upgrade
```

### Production migrations

For production, we use a custom endpoint that runs the migration script. This should only be used after thorough testing in development.

## Migration History

- **July 2025**: Added `created_at` column to User table
