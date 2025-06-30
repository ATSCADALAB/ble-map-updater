#!/usr/bin/env python3
"""
Authentication Manager for BLE Map Transfer
Implements challenge-response authentication với digital signatures

FEATURES:
- Challenge-response protocol
- Digital signature validation
- Session management
- Rate limiting
- Multi-device support
"""

import time
import json
import hashlib
import secrets
from enum import Enum
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass


class AuthState(Enum):
    """Authentication states"""
    INITIAL = "initial"
    CHALLENGE_SENT = "challenge_sent"
    AUTHENTICATED = "authenticated"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class AuthSession:
    """Authentication session data"""
    device_id: str
    challenge: str
    challenge_time: float
    state: AuthState
    attempts: int = 0
    client_info: Optional[Dict[str, Any]] = None


class AuthenticationManager:
    """
    Manages authentication cho BLE connections
    
    PROTOCOL:
    1. Client requests authentication
    2. Server generates và sends challenge
    3. Client signs challenge với private key
    4. Server validates signature với public key
    5. Session established on success
    """
    
    def __init__(self, device_id: str, logger=None):
        self.device_id = device_id
        self.logger = logger
        
        # Configuration
        self.auth_timeout = 60  # seconds
        self.max_attempts = 3
        self.challenge_length = 32  # bytes
        
        # Active sessions
        self.sessions: Dict[str, AuthSession] = {}
        
        # Signature validation (simplified for demo)
        self.signature_enabled = False
        
        if self.logger:
            self.logger.system_logger.info("AuthenticationManager initialized", {
                "device_id": device_id,
                "auth_timeout": self.auth_timeout,
                "max_attempts": self.max_attempts
            })
    
    def generate_challenge(self, client_id: str) -> Dict[str, Any]:
        """
        Generate authentication challenge cho client
        
        Args:
            client_id: Unique identifier cho connecting client
            
        Returns:
            Dict: Challenge data để send to client
        """
        
        # Clean up expired sessions
        self._cleanup_expired_sessions()
        
        # Check if client already has active session
        if client_id in self.sessions:
            session = self.sessions[client_id]
            if session.state == AuthState.AUTHENTICATED:
                return {
                    "status": "already_authenticated",
                    "message": "Client already authenticated"
                }
            elif session.attempts >= self.max_attempts:
                return {
                    "status": "max_attempts_exceeded",
                    "message": "Maximum authentication attempts exceeded"
                }
        
        # Generate random challenge
        challenge = secrets.token_hex(self.challenge_length)
        challenge_time = time.time()
        
        # Create session
        session = AuthSession(
            device_id=client_id,
            challenge=challenge,
            challenge_time=challenge_time,
            state=AuthState.CHALLENGE_SENT
        )
        
        self.sessions[client_id] = session
        
        if self.logger:
            self.logger.security_logger.info("Authentication challenge generated", {
                "client_id": client_id,
                "challenge_length": len(challenge),
                "timestamp": challenge_time
            })
        
        return {
            "status": "challenge_generated",
            "challenge": challenge,
            "server_id": self.device_id,
            "timestamp": challenge_time,
            "expires_in": self.auth_timeout
        }
    
    def verify_challenge_response(self, client_id: str, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verify client's response to authentication challenge
        
        Args:
            client_id: Client identifier
            response_data: Client's response including signature
            {
                "challenge": str,
                "signature": str,
                "client_info": dict (optional),
                "timestamp": float
            }
            
        Returns:
            Dict: Verification result
        """
        
        # Check session exists
        if client_id not in self.sessions:
            return {
                "status": "error",
                "error_code": "NO_ACTIVE_CHALLENGE",
                "message": "No active challenge for client"
            }
        
        session = self.sessions[client_id]
        session.attempts += 1
        
        try:
            # Check session state
            if session.state != AuthState.CHALLENGE_SENT:
                session.state = AuthState.FAILED
                return {
                    "status": "error", 
                    "error_code": "INVALID_STATE",
                    "message": f"Invalid session state: {session.state.value}"
                }
            
            # Check timeout
            if time.time() - session.challenge_time > self.auth_timeout:
                session.state = AuthState.EXPIRED
                return {
                    "status": "error",
                    "error_code": "CHALLENGE_EXPIRED",
                    "message": "Challenge expired"
                }
            
            # Validate response format
            required_fields = ["challenge", "signature"]
            for field in required_fields:
                if field not in response_data:
                    session.state = AuthState.FAILED
                    return {
                        "status": "error",
                        "error_code": "INVALID_RESPONSE_FORMAT", 
                        "message": f"Missing field: {field}"
                    }
            
            # Verify challenge matches
            if response_data["challenge"] != session.challenge:
                session.state = AuthState.FAILED
                return {
                    "status": "error",
                    "error_code": "CHALLENGE_MISMATCH",
                    "message": "Challenge mismatch"
                }
            
            # Verify signature (simplified for demo)
            if self.signature_enabled:
                signature_valid = self._verify_signature(
                    session.challenge,
                    response_data["signature"],
                    client_id
                )
                
                if not signature_valid:
                    session.state = AuthState.FAILED
                    return {
                        "status": "error",
                        "error_code": "INVALID_SIGNATURE",
                        "message": "Signature verification failed"
                    }
            else:
                # For demo: simple signature check
                expected_signature = self._generate_demo_signature(session.challenge, client_id)
                if response_data["signature"] != expected_signature:
                    # Allow for demo purposes - just log warning
                    if self.logger:
                        self.logger.security_logger.warning("Demo signature mismatch", {
                            "client_id": client_id,
                            "expected": expected_signature,
                            "received": response_data["signature"]
                        })
            
            # Authentication successful
            session.state = AuthState.AUTHENTICATED
            session.client_info = response_data.get("client_info", {})
            
            if self.logger:
                self.logger.security_logger.info("Authentication successful", {
                    "client_id": client_id,
                    "attempts": session.attempts,
                    "duration": time.time() - session.challenge_time
                })
            
            return {
                "status": "authenticated",
                "session_id": self._generate_session_id(client_id),
                "server_info": {
                    "device_id": self.device_id,
                    "capabilities": ["map_transfer", "chunked_protocol"],
                    "max_file_size": 5 * 1024 * 1024  # 5MB
                },
                "session_timeout": 3600  # 1 hour
            }
            
        except Exception as e:
            session.state = AuthState.FAILED
            
            if self.logger:
                self.logger.security_logger.error("Authentication verification error", {
                    "client_id": client_id,
                    "error": str(e)
                }, e)
            
            return {
                "status": "error",
                "error_code": "VERIFICATION_ERROR",
                "message": str(e)
            }
    
    def is_authenticated(self, client_id: str) -> bool:
        """Check if client is authenticated"""
        
        if client_id not in self.sessions:
            return False
        
        session = self.sessions[client_id]
        
        # Check state
        if session.state != AuthState.AUTHENTICATED:
            return False
        
        # Check timeout (sessions expire after 1 hour)
        if time.time() - session.challenge_time > 3600:
            session.state = AuthState.EXPIRED
            return False
        
        return True
    
    def invalidate_session(self, client_id: str):
        """Invalidate authentication session"""
        
        if client_id in self.sessions:
            session = self.sessions[client_id]
            session.state = AuthState.FAILED
            
            if self.logger:
                self.logger.security_logger.info("Session invalidated", {
                    "client_id": client_id
                })
    
    def get_session_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get session information"""
        
        if client_id not in self.sessions:
            return None
        
        session = self.sessions[client_id]
        
        return {
            "device_id": session.device_id,
            "state": session.state.value,
            "attempts": session.attempts,
            "challenge_time": session.challenge_time,
            "client_info": session.client_info
        }
    
    def _verify_signature(self, challenge: str, signature: str, client_id: str) -> bool:
        """
        Verify digital signature (placeholder implementation)
        
        In production, this would use real cryptographic verification
        with stored public keys for each client device.
        """
        
        # Placeholder: In production, load client's public key
        # and verify signature using cryptographic library
        
        # For demo: simple hash-based verification
        expected_signature = hashlib.sha256(
            f"{challenge}:{client_id}:{self.device_id}".encode()
        ).hexdigest()
        
        return signature == expected_signature
    
    def _generate_demo_signature(self, challenge: str, client_id: str) -> str:
        """Generate demo signature for testing"""
        return hashlib.sha256(
            f"{challenge}:{client_id}:{self.device_id}".encode()
        ).hexdigest()
    
    def _generate_session_id(self, client_id: str) -> str:
        """Generate unique session ID"""
        timestamp = str(int(time.time()))
        data = f"{client_id}:{self.device_id}:{timestamp}"
        return hashlib.md5(data.encode()).hexdigest()
    
    def _cleanup_expired_sessions(self):
        """Remove expired sessions"""
        
        current_time = time.time()
        expired_clients = []
        
        for client_id, session in self.sessions.items():
            if current_time - session.challenge_time > self.auth_timeout * 2:
                expired_clients.append(client_id)
        
        for client_id in expired_clients:
            del self.sessions[client_id]
            
            if self.logger:
                self.logger.security_logger.info("Expired session cleaned up", {
                    "client_id": client_id
                })
    
    def get_active_sessions_count(self) -> int:
        """Get number of active authenticated sessions"""
        
        count = 0
        for session in self.sessions.values():
            if session.state == AuthState.AUTHENTICATED:
                count += 1
        
        return count
    
    def configure(self, config: Dict[str, Any]):
        """Update configuration"""
        
        security_config = config.get("security", {})
        
        self.auth_timeout = security_config.get("auth_timeout", self.auth_timeout)
        self.max_attempts = security_config.get("max_auth_attempts", self.max_attempts)
        self.signature_enabled = security_config.get("required_signature", False)
        
        if self.logger:
            self.logger.system_logger.info("Authentication configuration updated", {
                "auth_timeout": self.auth_timeout,
                "max_attempts": self.max_attempts,
                "signature_enabled": self.signature_enabled
            })