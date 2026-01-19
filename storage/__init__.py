"""Storage package for Redis and S3 operations."""
from storage.redis_client import (
    is_redis_available,
    get_redis_client,
    clear_session,
    set_streaming_state,
    get_streaming_state
)
from storage.s3 import (
    upload_to_s3,
    upload_to_s3_async,
    is_s3_configured,
    get_s3_client,
    get_s3_url,
    download_from_s3,
    delete_from_s3
)

__all__ = [
    # Redis
    'is_redis_available',
    'get_redis_client',
    'clear_session',
    'set_streaming_state',
    'get_streaming_state',
    # S3
    'upload_to_s3',
    'upload_to_s3_async',
    'is_s3_configured',
    'get_s3_client',
    'get_s3_url',
    'download_from_s3',
    'delete_from_s3'
]
