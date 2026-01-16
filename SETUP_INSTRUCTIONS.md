# S3 and PostgreSQL Setup Instructions

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- `boto3` - AWS SDK for Python
- `psycopg2-binary` - PostgreSQL adapter

## Step 2: PostgreSQL Setup

### Create Database

1. Open PostgreSQL command line or pgAdmin
2. Create a new database:
```sql
CREATE DATABASE voicechatbot;
```

3. Note your PostgreSQL connection details:
   - Host: `localhost` (or your DB host)
   - Port: `5432` (default)
   - Database: `voicechatbot`
   - Username: `postgres` (or your username)
   - Password: Your PostgreSQL password

## Step 3: AWS S3 Setup

### Create S3 Bucket

1. Go to [AWS Console](https://console.aws.amazon.com/)
2. Navigate to S3 service
3. Click "Create bucket"
4. Choose a unique bucket name (e.g., `voice-chatbot-audio-2024`)
5. Select a region (e.g., `us-east-1`)
6. Keep default settings (or configure as needed)
7. Click "Create bucket"

### Create IAM User

1. Go to IAM service in AWS Console
2. Click "Users" → "Create user"
3. Username: `voice-chatbot-s3-user`
4. Select "Programmatic access"
5. Click "Next: Permissions"
6. Click "Attach existing policies directly"
7. Search and select: `AmazonS3FullAccess` (or create a custom policy with only PutObject, GetObject, DeleteObject)
8. Complete user creation
9. **IMPORTANT**: Save the Access Key ID and Secret Access Key (you won't see them again!)

## Step 4: Configure Environment Variables

Create a `.env` file in the project root with the following content:

```env
# Google Gemini API (already configured)
GEMINI_API_KEY=your_gemini_api_key_here

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=your_access_key_id_from_iam
AWS_SECRET_ACCESS_KEY=your_secret_access_key_from_iam
AWS_S3_BUCKET=your-bucket-name
AWS_REGION=us-east-1

# PostgreSQL Configuration
# Option 1: Use DATABASE_URL (recommended)
DATABASE_URL=postgresql://username:password@localhost:5432/voicechatbot

# Option 2: Use separate variables (if not using DATABASE_URL)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=voicechatbot
DB_USER=postgres
DB_PASSWORD=your_db_password
```

**Replace all placeholder values with your actual credentials!**

## Step 5: Test the Setup

1. Run the application:
```bash
python app.py
```

2. Check the console output:
   - ✅ Database connection successful
   - ✅ S3 configuration detected

If you see warnings (⚠️), the app will still work but will use local storage and in-memory conversations as fallback.

## How It Works

### Phase 1: Dual Write (Current Implementation)

- **Voice files**: Saved to both local `audio/` folder AND uploaded to S3
- **Messages**: Saved to both in-memory dict AND PostgreSQL database
- **Serving**: Tries S3/PostgreSQL first, falls back to local storage if unavailable

This ensures:
- ✅ Safe migration - existing functionality still works
- ✅ No data loss if S3/PostgreSQL fails
- ✅ Easy rollback if needed

### Phase 2: Full Migration (Optional)

Once you're confident everything works, you can:
- Remove local file writes after S3 upload
- Remove in-memory conversation storage
- Serve exclusively from S3 and PostgreSQL

## Troubleshooting

### Database Connection Failed
- Check PostgreSQL is running: `pg_isready` or check service status
- Verify credentials in `.env`
- Check database exists: `psql -l | grep voicechatbot`

### S3 Upload Failed
- Verify AWS credentials in `.env`
- Check bucket name is correct
- Verify IAM user has S3 permissions
- Check bucket region matches `AWS_REGION`

### App Still Uses Local Storage
- Check console output for warnings
- Verify `.env` file is in project root
- Restart the application after updating `.env`

## Production Considerations

1. **Security**:
   - Never commit `.env` file to git
   - Use environment variables or secrets manager in production
   - Use IAM roles instead of access keys on AWS (EC2/ECS)

2. **S3 Bucket Configuration**:
   - Enable versioning (optional)
   - Set up lifecycle policies for old files
   - Configure bucket policies for security

3. **Database**:
   - Use connection pooling in production
   - Set up regular backups
   - Monitor query performance

4. **Cost Optimization**:
   - S3 storage is cheap (~$0.023/GB/month)
   - Consider S3 Glacier for old files
   - Monitor AWS costs via CloudWatch
