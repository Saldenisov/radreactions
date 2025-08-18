# Authentication Setup for Railway Deployment

## Default Users

When the application first runs on Railway, it will automatically create these default users in `users.json`:

### User Accounts:
1. **Username:** `saldenisov`
   - **Password:** `Elys3!icp123`
   - **Status:** Administrator

2. **Username:** `zhiwenjiang`
   - **Password:** `Elys3!icp321`
   - **Status:** User

3. **Username:** `jplarbre`
   - **Password:** `Elys3!icp132`
   - **Status:** User

## Security Notes:

- The `users.json` file is automatically created by the application on first run
- Users should change their default passwords immediately after first login
- The authentication system uses bcrypt for secure password hashing
- User data is stored locally in the Railway container's file system
- Registration requests are saved to `registration_requests.json`

## For Railway Deployment:

1. The `users.json` file is excluded from Git (in .gitignore) for security
2. On first startup, the application will create default users automatically
3. All passwords are securely hashed using bcrypt
4. Users can change passwords and update contact info through the profile page

## Admin Access:

To add new users manually, contact the admin user `saldenisov` or add them through the user management system.
