# Authentication Setup for Railway Deployment

## SQLite Database Authentication

The application now uses a **SQLite database** (`users.db`) for secure user authentication instead of JSON files.

## Default Users

When the application first runs on Railway, it will automatically create these default users in the SQLite database:

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

## Security Features:

- **SQLite Database**: User data stored in `users.db` with proper database structure
- **bcrypt Password Hashing**: All passwords are securely hashed with salt
- **Role-Based Access**: Admin and user roles with different permissions
- **Account Management**: Users can be activated/deactivated by admins
- **Registration Workflow**: Registration requests stored in database for admin approval
- **Session Management**: Secure session state management with Streamlit
- **Database Exclusion**: `users.db` excluded from Git for security

## For Railway Deployment:

1. The `users.db` SQLite database is excluded from Git (in .gitignore) for security
2. On first startup, the application will:
   - Create the SQLite database with proper schema
   - Create default users with hashed passwords automatically
   - Set up registration requests table
3. **Admin Features** (for `saldenisov`):
   - View and manage all users
   - Approve/reject registration requests
   - Create new users directly
   - Activate/deactivate user accounts
4. **User Features**:
   - Change passwords securely
   - Update contact information
   - Submit registration requests

## Database Schema:

### Users Table:
- `id` (Primary Key)
- `username` (Unique)
- `password_hash` (bcrypt hashed)
- `email`, `phone`, `department`, `institution` (Contact info)
- `created_at`, `last_login` (Timestamps)
- `password_changed`, `password_change_date` (Password tracking)
- `is_active` (Account status)
- `role` (admin/user)

### Registration Requests Table:
- `id` (Primary Key)
- `requested_username`, `email`, `justification`
- `request_date`, `status`, `processed_by`, `processed_date`

## Admin Access:

The admin user `saldenisov` can:
- Access the full admin panel through their profile page
- Manage users and registration requests
- Create new users with custom roles
- Monitor system usage and user activity
