# Railway Deployment with Google Bigtable

## Environment Variables for Railway

Set these environment variables in your Railway project:

### Required for Bigtable:
```
USE_BIGTABLE=true
BIGTABLE_PROJECT_ID=adept-storm-466618-b4
BIGTABLE_INSTANCE_ID=hash-generator-instance
BIGTABLE_TABLE_ID=hashes
```

### Google Cloud Authentication:

**Option 1: Base64 Encoded (Recommended for Railway)**
1. Base64 encode your service account JSON file
2. Set the environment variable:
```
GOOGLE_APPLICATION_CREDENTIALS_BASE64=<base64_encoded_string>
```
The base64 string is in the file `service-account-base64.txt`

**Option 2: Raw JSON (may have issues with quotes)**
```
GOOGLE_APPLICATION_CREDENTIALS_JSON={"type": "service_account", ...}
```

### Optional:
```
SECRET_KEY=your-secret-key-here
RETENTION_DAYS=7
```

## How to Set in Railway:

1. Go to your Railway project dashboard
2. Click on your service
3. Go to "Variables" tab
4. Click "New Variable" for each environment variable
5. For `GOOGLE_APPLICATION_CREDENTIALS_JSON`, paste the entire JSON content from your service account file
6. Save and Railway will automatically redeploy

## Local Development:

For local development, the `.env` file is used with the path to the JSON file:
```
GOOGLE_APPLICATION_CREDENTIALS=adept-storm-466618-b4-7dc417b4e0e6.json
```

## Security Note:

The service account JSON is not committed to the repository for security reasons. It's passed as an environment variable in Railway instead.