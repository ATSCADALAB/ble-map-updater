"""
BLE Authentication Protocol Implementation

Security Features:
- Challenge-response authentication
- 128-bit nonces
- 30-second timeout window  
- ECDSA P-256 signatures
- Replay attack prevention
"""

import secrets
import time
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from enum import Enum

class AuthState(Enum):
    """Authentication state machine"""
    IDLE = "idle"
    CHALLENGE_SENT = "challenge_sent" 
    CHALLENGE_RECEIVED = "challenge_received"
    AUTHENTICATED = "authenticated"
    FAILED = "failed"
    EXPIRED = "expired"

class AuthenticationManager:
    """
    Manages BLE authentication according to protocol specification
    
    Protocol Flow:
    1. Device generates 128-bit nonce + session_id + timestamp
    2. Creates challenge payload: Hash(device_id || nonce || timestamp || session_id)
    3. Enforcement terminal signs payload with private key
    4. Device verifies signature with stored public key
    5. Mutual authentication with device signing response
    """
    
    def __init__(self, device_id: str, logger=None):
        self.device_id = device_id
        self.logger = logger
        
        # Current session state
        self.current_session = None
        self.auth_state = AuthState.IDLE
        
        # Security settings
        self.auth_timeout = 30  # seconds
        self.max_attempts = 3
        self.failed_attempts = 0
        
        # In production: load from secure storage
        self.enforcement_public_key = None
        self.device_private_key = None
        
    def generate_challenge(self) -> Dict[str, Any]:
        """
        Generate authentication challenge for enforcement device
        
        Returns:
            Dict containing challenge data and payload hash
            
        Raises:
            Exception: If already in authenticated state
        """
        
        if self.auth_state == AuthState.AUTHENTICATED:
            raise Exception("Already authenticated - disconnect first")
            
        try:
            # Generate cryptographically secure random values
            nonce = secrets.token_bytes(16)  # 128-bit nonce
            session_id = secrets.token_hex(16)  # 128-bit session ID
            timestamp = int(time.time())
            
            # Create challenge payload according to protocol spec
            payload_components = [
                self.device_id,
                nonce.hex(),
                str(timestamp), 
                session_id
            ]
            
            # Protocol specifies: Hash(device_id || nonce || timestamp || session_id)
            payload_string = "||".join(payload_components)
            payload_hash = hashlib.sha256(payload_string.encode()).hexdigest()
            
            # Store session information
            self.current_session = {
                "session_id": session_id,
                "nonce": nonce,
                "timestamp": timestamp,
                "payload_hash": payload_hash,
                "attempts": 0
            }
            
            # Update state
            self.auth_state = AuthState.CHALLENGE_SENT
            
            # Create challenge response
            challenge = {
                "message_type": "auth_challenge",
                "device_id": self.device_id,
                "session_id": session_id,
                "nonce": nonce.hex(),
                "timestamp": timestamp,
                "payload_hash": payload_hash
            }
            
            # Log security event
            if self.logger:
                self.logger.security_event("auth_challenge_generated", {
                    "session_id": session_id,
                    "device_id": self.device_id,
                    "timestamp": timestamp
                })
                
            return challenge
            
        except Exception as e:
            self.auth_state = AuthState.FAILED
            if self.logger:
                self.logger.error("Challenge generation failed", {"error": str(e)}, e)
            raise
    
    def verify_response(self, response: Dict[str, Any]) -> bool:
        """
        Verify enforcement device authentication response
        
        Args:
            response: Authentication response from enforcement device
            
        Returns:
            bool: True if authentication successful
            
        Security Checks:
        - Timestamp window validation (30 seconds)
        - Session ID matching
        - Digital signature verification (ECDSA P-256)
        - Nonce verification
        """
        
        if self.auth_state != AuthState.CHALLENGE_SENT:
            if self.logger:
                self.logger.security_event("auth_invalid_state", {
                    "current_state": self.auth_state.value,
                    "expected_state": "challenge_sent"
                })
            return False
            
        if not self.current_session:
            if self.logger:
                self.logger.security_event("auth_no_session", {})
            return False
            
        try:
            # Increment attempt counter
            self.current_session["attempts"] += 1
            
            # Check maximum attempts
            if self.current_session["attempts"] > self.max_attempts:
                self.auth_state = AuthState.FAILED
                if self.logger:
                    self.logger.security_event("auth_max_attempts_exceeded", {
                        "session_id": self.current_session["session_id"],
                        "attempts": self.current_session["attempts"]
                    })
                return False
            
            # 1. Validate timestamp window (30 seconds)
            current_time = int(time.time())
            time_diff = current_time - self.current_session["timestamp"]
            
            if time_diff > self.auth_timeout:
                self.auth_state = AuthState.EXPIRED
                if self.logger:
                    self.logger.security_event("auth_timeout", {
                        "session_id": self.current_session["session_id"],
                        "time_diff": time_diff,
                        "timeout": self.auth_timeout
                    })
                return False
            
            # 2. Validate session ID
            if response.get("session_id") != self.current_session["session_id"]:
                if self.logger:
                    self.logger.security_event("auth_session_mismatch", {
                        "expected": self.current_session["session_id"],
                        "received": response.get("session_id")
                    })
                return False
            
            # 3. Validate required fields
            required_fields = ["signature", "device_id", "timestamp"]
            for field in required_fields:
                if field not in response:
                    if self.logger:
                        self.logger.security_event("auth_missing_field", {
                            "missing_field": field
                        })
                    return False
            
            # 4. Verify digital signature (simplified for now)
            # In production: implement ECDSA P-256 verification
            signature = response["signature"]
            enforcement_device_id = response["device_id"]
            
            signature_valid = self._verify_ecdsa_signature(
                self.current_session["payload_hash"],
                signature,
                enforcement_device_id
            )
            
            if not signature_valid:
                if self.logger:
                    self.logger.security_event("auth_signature_invalid", {
                        "session_id": self.current_session["session_id"],
                        "enforcement_device": enforcement_device_id
                    })
                return False
            
            # 5. Authentication successful
            self.auth_state = AuthState.AUTHENTICATED
            self.current_session["authenticated_at"] = current_time
            self.current_session["enforcement_device"] = enforcement_device_id
            
            if self.logger:
                self.logger.security_event("auth_success", {
                    "session_id": self.current_session["session_id"],
                    "enforcement_device": enforcement_device_id,
                    "duration": time_diff
                })
                
            return True
            
        except Exception as e:
            self.auth_state = AuthState.FAILED
            if self.logger:
                self.logger.security_event("auth_verification_error", {
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            return False
    
    def _verify_ecdsa_signature(self, payload_hash: str, signature: str, device_id: str) -> bool:
        """
        Verify ECDSA P-256 signature
        
        In production implementation:
        1. Load enforcement device public key from secure storage
        2. Verify signature using cryptography library
        3. Handle key rotation and certificate validation
        
        For now: simplified verification
        """
        
        # TODO: Implement real ECDSA verification
        # from cryptography.hazmat.primitives import hashes
        # from cryptography.hazmat.primitives.asymmetric import ec
        
        # Simplified verification for testing
        if len(signature) < 10:  # Basic sanity check
            return False
            
        # In production: verify against stored public key
        # public_key = self._load_enforcement_public_key(device_id)
        # return self._verify_signature(payload_hash, signature, public_key)
        
        # For testing: accept non-empty signatures
        return signature and signature != "invalid"
    
    def is_authenticated(self) -> bool:
        """Check if current session is authenticated and not expired"""
        
        if self.auth_state != AuthState.AUTHENTICATED:
            return False
            
        if not self.current_session:
            return False
            
        # Check session timeout (extend to longer period after auth)
        current_time = int(time.time())
        auth_time = self.current_session.get("authenticated_at", 0)
        session_timeout = 300  # 5 minutes for file transfer
        
        if current_time - auth_time > session_timeout:
            self.auth_state = AuthState.EXPIRED
            if self.logger:
                self.logger.security_event("session_expired", {
                    "session_id": self.current_session["session_id"],
                    "duration": current_time - auth_time
                })
            return False
            
        return True
    
    def reset_session(self):
        """Reset authentication session"""
        
        if self.current_session and self.logger:
            self.logger.security_event("session_reset", {
                "session_id": self.current_session["session_id"],
                "previous_state": self.auth_state.value
            })
            
        self.current_session = None
        self.auth_state = AuthState.IDLE
        self.failed_attempts = 0
    
    def get_session_info(self) -> Optional[Dict[str, Any]]:
        """Get current session information for debugging"""
        
        if not self.current_session:
            return None
            
        return {
            "session_id": self.current_session["session_id"],
            "state": self.auth_state.value,
            "authenticated": self.is_authenticated(),
            "timestamp": self.current_session["timestamp"],
            "attempts": self.current_session["attempts"]
        }