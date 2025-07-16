# Migration Cleanup Plan

After the migration has been successfully applied to the production database, follow these steps to clean up:

## 1. Verify Migration Success

1. Visit `https://apestogether.ai/api/run-migration` to run the migration
2. Check `https://apestogether.ai/api/debug` to confirm the database connection is successful
3. Verify that the application is functioning correctly

## 2. Remove Temporary Migration Endpoint

Once verified, remove the temporary migration endpoint by:

1. Removing the `/api/run-migration` route from `api/index.py`
2. Keeping the Flask-Migrate setup for future migrations
3. Committing and pushing the changes to deploy the update

## 3. Keep Migration Scripts

Keep the migration scripts (`migrations.py` and `apply_migration.py`) in your codebase as they may be useful for:
- Reference for future migrations
- Documenting the database schema history
- Potential reuse in development/staging environments

## 4. Future Database Changes

For any future database schema changes:
1. Use Flask-Migrate to generate and manage migrations
2. Test migrations in development before applying to production
3. Document all schema changes in a dedicated file
