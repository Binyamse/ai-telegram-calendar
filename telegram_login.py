import os
import hashlib
import hmac
import time
from typing import Dict, Optional, Union, Tuple


class TelegramLoginVerifier:
    """Helper class for verifying Telegram Login Widget data"""
    
    def __init__(self, bot_token: str):
        """Initialize with bot token"""
        self.bot_token = bot_token
        # Create secret key from bot token
        self.secret_key = hashlib.sha256(bot_token.encode()).digest()
        
    def verify_telegram_auth(self, auth_data: Dict[str, str]) -> Tuple[bool, Optional[str]]:
        """
        Verify Telegram authentication data.
        
        Args:
            auth_data: Dictionary with auth data from Telegram
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if hash is present
        if 'hash' not in auth_data:
            return False, "No hash provided"
            
        # Check required fields
        required_fields = ['id', 'auth_date', 'first_name']
        if not all(field in auth_data for field in required_fields):
            return False, "Missing required fields"
            
        # Check auth_date is not too old (1 day)
        auth_date = int(auth_data['auth_date'])
        now = time.time()
        if now - auth_date > 86400:
            return False, "Authentication too old"
            
        # Check hash
        received_hash = auth_data['hash']
        auth_data_without_hash = {k: v for k, v in auth_data.items() if k != 'hash'}
        calculated_hash = self._calculate_hash(auth_data_without_hash)
        
        if calculated_hash != received_hash:
            return False, "Invalid hash"
            
        return True, None
        
    def _calculate_hash(self, auth_data: Dict[str, str]) -> str:
        """
        Calculate hash for Telegram auth data.
        
        Args:
            auth_data: Dictionary with auth data from Telegram (without hash field)
            
        Returns:
            Calculated hash string
        """
        # Create data check string
        data_check_arr = []
        for key in sorted(auth_data.keys()):
            data_check_arr.append(f"{key}={auth_data[key]}")
        data_check_string = '\n'.join(data_check_arr)
        
        # Calculate HMAC-SHA-256 hash
        computed_hash = hmac.new(
            self.secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return computed_hash


def extract_user_data(auth_data: Dict[str, str]) -> Dict[str, str]:
    """
    Extract relevant user data from Telegram auth data.
    
    Args:
        auth_data: Dictionary with auth data from Telegram
        
    Returns:
        Dictionary with user data
    """
    user_data = {
        'id': auth_data['id'],
        'first_name': auth_data['first_name'],
        'auth_date': auth_data['auth_date']
    }
    
    # Optional fields
    if 'last_name' in auth_data:
        user_data['last_name'] = auth_data['last_name']
    if 'username' in auth_data:
        user_data['username'] = auth_data['username'].lower()
    if 'photo_url' in auth_data:
        user_data['photo_url'] = auth_data['photo_url']
        
    return user_data
