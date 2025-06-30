#!/usr/bin/env python3
"""
BLE Protocol Definitions for Map Transfer System
Defines constants, message types, và protocol structures

PROTOCOL OVERVIEW:
- Authentication: Challenge-response với digital signatures
- Transfer: Chunked file transfer với metadata validation
- Control: Transfer control commands (pause/resume/cancel)
- Status: Real-time status và progress reporting
"""

from enum import Enum
from typing import Dict, Any, List
from dataclasses import dataclass


# =============================================================================
# BLE Service và Characteristic UUIDs
# =============================================================================

class ServiceUUIDs:
    """BLE Service UUIDs"""
    MAP_TRANSFER_SERVICE = "12345678-1234-1234-1234-123456789abc"


class CharacteristicUUIDs:
    """BLE Characteristic UUIDs"""
    # Authentication channel
    AUTH_CHALLENGE = "12345678-1234-1234-1234-123456789abd"
    
    # Map data transfer channel
    MAP_DATA = "12345678-1234-1234-1234-123456789abe"
    
    # Status và control channel
    STATUS_CONTROL = "12345678-1234-1234-1234-123456789abf"


# =============================================================================
# Message Types
# =============================================================================

class MessageType:
    """Protocol message types"""
    
    # Authentication messages
    AUTH_REQUEST = "auth_request"
    AUTH_CHALLENGE = "auth_challenge" 
    AUTH_RESPONSE = "auth_response"
    AUTH_SUCCESS = "auth_success"
    AUTH_ERROR = "auth_error"
    
    # Transfer messages
    TRANSFER_INIT = "transfer_init"
    TRANSFER_READY = "transfer_ready"
    CHUNK_DATA = "chunk_data"
    CHUNK_ACK = "chunk_ack"
    TRANSFER_COMPLETE = "transfer_complete"
    TRANSFER_ERROR = "transfer_error"
    
    # Control messages
    TRANSFER_PAUSE = "transfer_pause"
    TRANSFER_RESUME = "transfer_resume"
    TRANSFER_CANCEL = "transfer_cancel"
    
    # Status messages
    STATUS_REQUEST = "status_request"
    STATUS_RESPONSE = "status_response"
    PROGRESS_UPDATE = "progress_update"


# =============================================================================
# Transfer States
# =============================================================================

class TransferState(Enum):
    """Transfer session states"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    METADATA_RECEIVED = "metadata_received"
    RECEIVING_CHUNKS = "receiving_chunks"
    VALIDATING = "validating"
    COMPLETING = "completing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


# =============================================================================
# Error Codes
# =============================================================================

class ErrorCode:
    """Standard error codes"""
    
    # Authentication errors
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_FAILED = "AUTH_FAILED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    
    # Transfer errors
    TRANSFER_ALREADY_ACTIVE = "TRANSFER_ALREADY_ACTIVE"
    INVALID_METADATA = "INVALID_METADATA"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    VERSION_TOO_OLD = "VERSION_TOO_OLD"
    CHUNK_OUT_OF_ORDER = "CHUNK_OUT_OF_ORDER"
    CHUNK_DUPLICATE = "CHUNK_DUPLICATE"
    CHUNK_INVALID = "CHUNK_INVALID"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    
    # System errors
    INSUFFICIENT_STORAGE = "INSUFFICIENT_STORAGE"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    TIMEOUT = "TIMEOUT"
    CANCELLED_BY_USER = "CANCELLED_BY_USER"


# =============================================================================
# Protocol Constants
# =============================================================================

class ProtocolConstants:
    """Protocol configuration constants"""
    
    # BLE constraints
    MAX_CHARACTERISTIC_SIZE = 512  # bytes
    RECOMMENDED_CHUNK_SIZE = 128   # bytes
    
    # Transfer limits
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    MAX_CHUNKS_PER_TRANSFER = 50000  # ~6.4MB at 128 bytes/chunk
    
    # Timeouts
    AUTH_TIMEOUT = 60           # seconds
    TRANSFER_TIMEOUT = 600      # seconds (10 minutes)
    CHUNK_TIMEOUT = 5           # seconds
    
    # Rate limiting
    MAX_CHUNKS_PER_SECOND = 10
    MAX_AUTH_ATTEMPTS = 3
    
    # Compression
    COMPRESSION_THRESHOLD = 1024 * 1024  # 1MB
    COMPRESSION_LEVEL = 6


# =============================================================================
# Message Structures
# =============================================================================

@dataclass
class AuthChallengeMessage:
    """Authentication challenge message structure"""
    type: str = MessageType.AUTH_CHALLENGE
    challenge: str = ""
    server_id: str = ""
    timestamp: float = 0.0
    expires_in: int = 60


@dataclass
class AuthResponseMessage:
    """Authentication response message structure"""
    type: str = MessageType.AUTH_RESPONSE
    challenge: str = ""
    signature: str = ""
    client_info: Dict[str, Any] = None
    timestamp: float = 0.0


@dataclass
class TransferInitMessage:
    """Transfer initialization message structure"""
    type: str = MessageType.TRANSFER_INIT
    metadata: Dict[str, Any] = None
    # metadata contains:
    # - file_size: int
    # - file_hash: str
    # - version: int
    # - signature: str (optional)
    # - compression: str (optional)
    # - compressed_size: int (optional)
    # - compressed_hash: str (optional)


@dataclass
class ChunkDataMessage:
    """Chunk data message structure"""
    type: str = MessageType.CHUNK_DATA
    session_id: str = ""
    chunk_index: int = 0
    data: str = ""  # hex-encoded bytes
    checksum: str = ""


@dataclass
class StatusResponseMessage:
    """Status response message structure"""
    type: str = MessageType.STATUS_RESPONSE
    server_status: str = "ready"  # ready, busy, error
    transfer_state: str = TransferState.IDLE.value
    progress: Dict[str, Any] = None
    # progress contains:
    # - chunks_received: int
    # - total_chunks: int
    # - bytes_received: int
    # - progress_percent: float
    # - transfer_rate_bps: float


@dataclass
class ErrorMessage:
    """Error message structure"""
    type: str = MessageType.TRANSFER_ERROR
    error_code: str = ""
    message: str = ""
    details: Dict[str, Any] = None


# =============================================================================
# Protocol Utilities
# =============================================================================

class ProtocolUtils:
    """Utility functions for protocol handling"""
    
    @staticmethod
    def create_message(message_type: str, **kwargs) -> Dict[str, Any]:
        """Create protocol message"""
        message = {
            "type": message_type,
            "timestamp": kwargs.get("timestamp", 0.0)
        }
        message.update(kwargs)
        return message
    
    @staticmethod
    def validate_message(message: Dict[str, Any], expected_type: str) -> bool:
        """Validate message structure"""
        if not isinstance(message, dict):
            return False
        
        if message.get("type") != expected_type:
            return False
        
        return True
    
    @staticmethod
    def calculate_chunks_needed(file_size: int, chunk_size: int) -> int:
        """Calculate number of chunks needed"""
        return (file_size + chunk_size - 1) // chunk_size
    
    @staticmethod
    def encode_chunk_data(data: bytes) -> str:
        """Encode chunk data to hex string"""
        return data.hex()
    
    @staticmethod
    def decode_chunk_data(hex_string: str) -> bytes:
        """Decode hex string to bytes"""
        return bytes.fromhex(hex_string)
    
    @staticmethod
    def calculate_checksum(data: bytes) -> str:
        """Calculate checksum for chunk data"""
        import hashlib
        return hashlib.md5(data).hexdigest()
    
    @staticmethod
    def verify_checksum(data: bytes, expected_checksum: str) -> bool:
        """Verify chunk checksum"""
        actual_checksum = ProtocolUtils.calculate_checksum(data)
        return actual_checksum == expected_checksum


# =============================================================================
# Protocol Validators
# =============================================================================

class MessageValidator:
    """Validates protocol messages"""
    
    @staticmethod
    def validate_auth_challenge(message: Dict[str, Any]) -> List[str]:
        """Validate authentication challenge message"""
        errors = []
        
        if not ProtocolUtils.validate_message(message, MessageType.AUTH_CHALLENGE):
            errors.append("Invalid message type")
        
        if not message.get("challenge"):
            errors.append("Missing challenge")
        
        if not message.get("server_id"):
            errors.append("Missing server_id")
        
        return errors
    
    @staticmethod
    def validate_auth_response(message: Dict[str, Any]) -> List[str]:
        """Validate authentication response message"""
        errors = []
        
        if not ProtocolUtils.validate_message(message, MessageType.AUTH_RESPONSE):
            errors.append("Invalid message type")
        
        if not message.get("challenge"):
            errors.append("Missing challenge")
        
        if not message.get("signature"):
            errors.append("Missing signature")
        
        return errors
    
    @staticmethod
    def validate_transfer_init(message: Dict[str, Any]) -> List[str]:
        """Validate transfer initialization message"""
        errors = []
        
        if not ProtocolUtils.validate_message(message, MessageType.TRANSFER_INIT):
            errors.append("Invalid message type")
        
        metadata = message.get("metadata", {})
        
        required_fields = ["file_size", "file_hash", "version"]
        for field in required_fields:
            if field not in metadata:
                errors.append(f"Missing metadata field: {field}")
        
        # Validate file size
        file_size = metadata.get("file_size", 0)
        if not isinstance(file_size, int) or file_size <= 0:
            errors.append("Invalid file_size")
        
        if file_size > ProtocolConstants.MAX_FILE_SIZE:
            errors.append(f"File too large: {file_size} > {ProtocolConstants.MAX_FILE_SIZE}")
        
        # Validate version
        version = metadata.get("version")
        if not isinstance(version, int) or version <= 0:
            errors.append("Invalid version")
        
        return errors
    
    @staticmethod
    def validate_chunk_data(message: Dict[str, Any]) -> List[str]:
        """Validate chunk data message"""
        errors = []
        
        if not ProtocolUtils.validate_message(message, MessageType.CHUNK_DATA):
            errors.append("Invalid message type")
        
        if not message.get("session_id"):
            errors.append("Missing session_id")
        
        chunk_index = message.get("chunk_index")
        if not isinstance(chunk_index, int) or chunk_index < 0:
            errors.append("Invalid chunk_index")
        
        if not message.get("data"):
            errors.append("Missing chunk data")
        
        # Validate hex encoding
        try:
            data = ProtocolUtils.decode_chunk_data(message.get("data", ""))
            
            # Validate chunk size
            if len(data) > ProtocolConstants.RECOMMENDED_CHUNK_SIZE * 2:
                errors.append("Chunk too large")
            
            # Validate checksum if provided
            checksum = message.get("checksum")
            if checksum and not ProtocolUtils.verify_checksum(data, checksum):
                errors.append("Checksum mismatch")
                
        except ValueError:
            errors.append("Invalid hex encoding")
        
        return errors


# =============================================================================
# Protocol State Machine
# =============================================================================

class TransferStateMachine:
    """Manages transfer state transitions"""
    
    VALID_TRANSITIONS = {
        TransferState.IDLE: [TransferState.INITIALIZING],
        TransferState.INITIALIZING: [TransferState.METADATA_RECEIVED, TransferState.FAILED],
        TransferState.METADATA_RECEIVED: [TransferState.RECEIVING_CHUNKS, TransferState.FAILED],
        TransferState.RECEIVING_CHUNKS: [
            TransferState.VALIDATING, 
            TransferState.PAUSED, 
            TransferState.CANCELLED, 
            TransferState.FAILED
        ],
        TransferState.PAUSED: [TransferState.RECEIVING_CHUNKS, TransferState.CANCELLED],
        TransferState.VALIDATING: [TransferState.COMPLETING, TransferState.FAILED],
        TransferState.COMPLETING: [TransferState.COMPLETED, TransferState.FAILED],
        TransferState.COMPLETED: [TransferState.IDLE],
        TransferState.FAILED: [TransferState.IDLE],
        TransferState.CANCELLED: [TransferState.IDLE]
    }
    
    @classmethod
    def can_transition(cls, from_state: TransferState, to_state: TransferState) -> bool:
        """Check if state transition is valid"""
        valid_next_states = cls.VALID_TRANSITIONS.get(from_state, [])
        return to_state in valid_next_states
    
    @classmethod
    def get_valid_next_states(cls, current_state: TransferState) -> List[TransferState]:
        """Get list of valid next states"""
        return cls.VALID_TRANSITIONS.get(current_state, [])