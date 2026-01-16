"""
AWS S3 storage operations for audio files.
"""
import os
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

# S3 configuration from environment variables
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Initialize S3 client
_s3_client = None

def get_s3_client():
    """Get or create S3 client."""
    global _s3_client
    
    if _s3_client is None:
        try:
            if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
                _s3_client = boto3.client(
                    's3',
                    aws_access_key_id=AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                    region_name=AWS_REGION
                )
            else:
                # Try to use default credentials (from AWS credentials file or IAM role)
                _s3_client = boto3.client('s3', region_name=AWS_REGION)
        except Exception as e:
            print(f"⚠️  Error initializing S3 client: {e}")
            return None
    
    return _s3_client

def upload_to_s3(file_path: Path, bucket: Optional[str] = None, key: Optional[str] = None) -> Optional[str]:
    """
    Upload a file to S3.
    
    Args:
        file_path: Local file path to upload
        bucket: S3 bucket name (defaults to AWS_S3_BUCKET env var)
        key: S3 object key/path (defaults to filename)
    
    Returns:
        S3 URL if successful, None otherwise
    """
    client = get_s3_client()
    if not client:
        print("⚠️  S3 client not available. Check AWS credentials.")
        return None
    
    if not bucket:
        bucket = AWS_S3_BUCKET
    
    if not bucket:
        print("⚠️  S3 bucket not specified. Set AWS_S3_BUCKET environment variable.")
        return None
    
    if not key:
        # Use filename as key, optionally with a folder prefix
        key = f"audio/{file_path.name}"
    
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        print(f"⚠️  File not found: {file_path}")
        return None
    
    try:
        # Upload file
        client.upload_file(
            str(file_path_obj),
            bucket,
            key,
            ExtraArgs={'ContentType': _get_content_type(file_path_obj)}
        )
        
        # Generate URL (use public URL if bucket is public, otherwise use presigned URL)
        # For simplicity, we'll generate a public URL (assuming bucket has public read access)
        # In production, you might want to use presigned URLs for security
        url = f"https://{bucket}.s3.{AWS_REGION}.amazonaws.com/{key}"
        
        print(f"✅ File uploaded to S3: {key}")
        return url
        
    except NoCredentialsError:
        print("⚠️  AWS credentials not found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.")
        return None
    except ClientError as e:
        print(f"⚠️  S3 upload error: {e}")
        return None
    except Exception as e:
        print(f"⚠️  Unexpected error uploading to S3: {e}")
        return None

def get_s3_url(bucket: Optional[str] = None, key: str = "") -> str:
    """
    Generate S3 URL for a given bucket and key.
    
    Args:
        bucket: S3 bucket name (defaults to AWS_S3_BUCKET env var)
        key: S3 object key/path
    
    Returns:
        S3 URL string
    """
    if not bucket:
        bucket = AWS_S3_BUCKET or "your-bucket"
    
    return f"https://{bucket}.s3.{AWS_REGION}.amazonaws.com/{key}"

def download_from_s3(key: str, local_path: Path, bucket: Optional[str] = None) -> bool:
    """
    Download a file from S3.
    
    Args:
        key: S3 object key/path
        local_path: Local file path to save the file
        bucket: S3 bucket name (defaults to AWS_S3_BUCKET env var)
    
    Returns:
        True if successful, False otherwise
    """
    client = get_s3_client()
    if not client:
        return False
    
    if not bucket:
        bucket = AWS_S3_BUCKET
    
    if not bucket:
        print("⚠️  S3 bucket not specified.")
        return False
    
    try:
        local_path_obj = Path(local_path)
        local_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        client.download_file(bucket, key, str(local_path_obj))
        return True
        
    except ClientError as e:
        print(f"⚠️  S3 download error: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Unexpected error downloading from S3: {e}")
        return False

def delete_from_s3(key: str, bucket: Optional[str] = None) -> bool:
    """
    Delete a file from S3 (optional cleanup function).
    
    Args:
        key: S3 object key/path
        bucket: S3 bucket name (defaults to AWS_S3_BUCKET env var)
    
    Returns:
        True if successful, False otherwise
    """
    client = get_s3_client()
    if not client:
        return False
    
    if not bucket:
        bucket = AWS_S3_BUCKET
    
    if not bucket:
        return False
    
    try:
        client.delete_object(Bucket=bucket, Key=key)
        return True
        
    except ClientError as e:
        print(f"⚠️  S3 delete error: {e}")
        return False

def _get_content_type(file_path: Path) -> str:
    """Get content type based on file extension."""
    extension = file_path.suffix.lower()
    content_types = {
        '.webm': 'audio/webm',
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.m4a': 'audio/mp4',
        '.ogg': 'audio/ogg'
    }
    return content_types.get(extension, 'application/octet-stream')

def is_s3_configured() -> bool:
    """Check if S3 is properly configured."""
    return bool(AWS_S3_BUCKET and (AWS_ACCESS_KEY_ID or os.path.exists(os.path.expanduser("~/.aws/credentials"))))
