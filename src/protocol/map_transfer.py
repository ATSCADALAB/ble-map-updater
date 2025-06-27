"""
Map Transfer Protocol Implementation

Features:
- Chunk-based file transfer optimized for BLE
- A/B partition scheme for atomic updates
- Hash validation and integrity checks
- Resume capability for interrupted transfers
- Progress tracking and error recovery
"""

import json
import hashlib
import time
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
from dataclasses import dataclass

class TransferState(Enum):
    """Transfer state machine"""
    IDLE = "idle"
    METADATA_RECEIVED = "metadata_received"
    RECEIVING_CHUNKS = "receiving_chunks"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class TransferSession:
    """Transfer session information"""
    session_id: str
    file_size: int
    file_hash: str
    total_chunks: int
    chunks_received: int
    start_time: float
    last_activity: float
    metadata: Dict[str, Any]
    received_chunks: Dict[int, bytes]  # chunk_index -> data
    state: TransferState

class MapTransferManager:
    """
    Manages chunked map file transfers over BLE
    
    Protocol Features:
    - Configurable chunk size (optimal: 64 bytes for BLE)
    - Out-of-order chunk delivery support
    - Duplicate chunk detection
    - Transfer timeout and retry logic
    - Atomic file operations with A/B partitioning
    """
    
    def __init__(self, config: Dict[str, Any], logger=None):
        self.config = config
        self.logger = logger
        
        # Transfer settings
        self.chunk_size = config["ble"]["chunk_size"]  # 64 bytes
        self.max_transfer_size = config["ble"]["max_transfer_size"]  # 1MB
        self.transfer_timeout = 300  # 5 minutes
        
        # Storage paths
        self.maps_dir = Path(config["storage"]["maps_dir"])
        self.active_map_path = Path(config["storage"]["active_map"])
        self.backup_map_path = Path(config["storage"]["backup_map"])
        
        # Ensure directories exist
        self.maps_dir.mkdir(parents=True, exist_ok=True)
        self.active_map_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_map_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Current transfer session
        self.current_transfer: Optional[TransferSession] = None
        
        # Progress callback
        self.progress_callback: Optional[Callable] = None
        
    def start_transfer(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Initialize map transfer with metadata validation
        
        Args:
            metadata: Transfer metadata containing file info
            
        Returns:
            Dict: Transfer session info or error response
            
        Validates:
        - File size limits
        - Version requirements
        - Required metadata fields
        - Digital signatures
        """
        
        try:
            # 1. Validate metadata structure
            required_fields = ["version", "file_size", "file_hash", "signature"]
            missing_fields = [field for field in required_fields if field not in metadata]
            
            if missing_fields:
                raise ValueError(f"Missing required metadata fields: {missing_fields}")
            
            # 2. Validate file size
            file_size = metadata["file_size"]
            if file_size <= 0:
                raise ValueError("Invalid file size")
                
            if file_size > self.max_transfer_size:
                raise ValueError(f"File too large: {file_size} > {self.max_transfer_size}")
            
            # 3. Version control validation
            current_version = self._get_current_map_version()
            new_version = metadata["version"]
            
            if new_version <= current_version:
                raise ValueError(
                    f"Version {new_version} is not newer than current {current_version}"
                )
            
            # 4. Validate digital signature (simplified)
            signature = metadata["signature"]
            if not self._validate_signature(metadata, signature):
                raise ValueError("Invalid digital signature")
            
            # 5. Calculate transfer parameters
            total_chunks = self._calculate_total_chunks(file_size)
            session_id = f"transfer_{int(time.time())}_{hash(str(metadata))}"
            
            # 6. Initialize transfer session
            self.current_transfer = TransferSession(
                session_id=session_id,
                file_size=file_size,
                file_hash=metadata["file_hash"],
                total_chunks=total_chunks,
                chunks_received=0,
                start_time=time.time(),
                last_activity=time.time(),
                metadata=metadata.copy(),
                received_chunks={},
                state=TransferState.METADATA_RECEIVED
            )
            
            # 7. Log transfer initiation
            if self.logger:
                self.logger.transfer_start(session_id, file_size, total_chunks)
                self.logger.info("Map transfer initiated", {
                    "session_id": session_id,
                    "version": new_version,
                    "file_size": file_size,
                    "chunks": total_chunks
                })
            
            # 8. Return transfer session info
            return {
                "status": "ready",
                "session_id": session_id,
                "chunk_size": self.chunk_size,
                "total_chunks": total_chunks,
                "expected_hash": metadata["file_hash"]
            }
            
        except Exception as e:
            if self.logger:
                self.logger.error("Transfer initialization failed", {
                    "error": str(e),
                    "metadata": metadata
                }, e)
                
            return {
                "status": "error",
                "error_code": "INIT_FAILED",
                "message": str(e)
            }
    
    def receive_chunk(self, chunk_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process received chunk data
        
        Args:
            chunk_data: Chunk information and data
            
        Returns:
            Dict: Chunk processing result
            
        Handles:
        - Out-of-order delivery
        - Duplicate detection
        - Data validation
        - Progress tracking
        - Transfer completion detection
        """
        
        # 1. Validate active transfer session
        if not self.current_transfer:
            return {
                "status": "error",
                "error_code": "NO_ACTIVE_TRANSFER", 
                "message": "No active transfer session"
            }
        
        if self.current_transfer.state not in [TransferState.METADATA_RECEIVED, TransferState.RECEIVING_CHUNKS]:
            return {
                "status": "error",
                "error_code": "INVALID_STATE",
                "message": f"Invalid transfer state: {self.current_transfer.state.value}"
            }
        
        try:
            # 2. Extract and validate chunk information
            chunk_index = chunk_data.get("chunk_index")
            chunk_hex_data = chunk_data.get("data")
            session_id = chunk_data.get("session_id")
            
            # Validate chunk parameters
            if chunk_index is None or chunk_hex_data is None:
                raise ValueError("Missing chunk_index or data")
                
            if session_id and session_id != self.current_transfer.session_id:
                raise ValueError("Session ID mismatch")
            
            if not isinstance(chunk_index, int) or chunk_index < 0:
                raise ValueError("Invalid chunk_index")
                
            if chunk_index >= self.current_transfer.total_chunks:
                raise ValueError(f"Chunk index {chunk_index} exceeds total {self.current_transfer.total_chunks}")
            
            # 3. Decode chunk data
            try:
                chunk_bytes = bytes.fromhex(chunk_hex_data)
            except ValueError:
                raise ValueError("Invalid hex data in chunk")
            
            # 4. Validate chunk size
            expected_size = self._get_expected_chunk_size(chunk_index)
            if len(chunk_bytes) != expected_size:
                raise ValueError(f"Chunk size mismatch: got {len(chunk_bytes)}, expected {expected_size}")
            
            # 5. Check for duplicate chunks
            if chunk_index in self.current_transfer.received_chunks:
                if self.logger:
                    self.logger.warning("Duplicate chunk received", {
                        "session_id": self.current_transfer.session_id,
                        "chunk_index": chunk_index
                    })
                
                # Return success for duplicate (idempotent)
                return {
                    "status": "duplicate",
                    "chunk_index": chunk_index,
                    "progress": self._calculate_progress()
                }
            
            # 6. Store chunk data
            self.current_transfer.received_chunks[chunk_index] = chunk_bytes
            self.current_transfer.chunks_received = len(self.current_transfer.received_chunks)
            self.current_transfer.last_activity = time.time()
            self.current_transfer.state = TransferState.RECEIVING_CHUNKS
            
            # 7. Log progress
            if self.logger:
                self.logger.transfer_progress(
                    self.current_transfer.session_id,
                    chunk_index,
                    self.current_transfer.total_chunks
                )
            
            # 8. Call progress callback if set
            if self.progress_callback:
                self.progress_callback(
                    self.current_transfer.chunks_received,
                    self.current_transfer.total_chunks
                )
            
            # 9. Check if transfer is complete
            if self.current_transfer.chunks_received >= self.current_transfer.total_chunks:
                return self._complete_transfer()
            
            # 10. Return chunk acknowledgment
            return {
                "status": "chunk_received",
                "chunk_index": chunk_index,
                "chunks_received": self.current_transfer.chunks_received,
                "total_chunks": self.current_transfer.total_chunks,
                "progress": self._calculate_progress()
            }
            
        except Exception as e:
            if self.logger:
                self.logger.error("Chunk processing failed", {
                    "session_id": self.current_transfer.session_id if self.current_transfer else None,
                    "chunk_index": chunk_data.get("chunk_index"),
                    "error": str(e)
                }, e)
            
            return {
                "status": "error",
                "error_code": "CHUNK_PROCESSING_FAILED",
                "message": str(e)
            }
    
    def _complete_transfer(self) -> Dict[str, Any]:
        """
        Complete transfer with validation and atomic file operations
        
        Process:
        1. Reconstruct file from chunks
        2. Validate file hash
        3. Parse and validate JSON structure
        4. Backup current map
        5. Atomic file replacement
        6. Cleanup
        """
        
        try:
            self.current_transfer.state = TransferState.VALIDATING
            
            # 1. Reconstruct file from chunks
            if self.logger:
                self.logger.info("Reconstructing file from chunks", {
                    "session_id": self.current_transfer.session_id,
                    "chunks": len(self.current_transfer.received_chunks)
                })
            
            file_data = self._reconstruct_file()
            
            # 2. Validate file hash
            calculated_hash = hashlib.sha256(file_data).hexdigest()
            expected_hash = self.current_transfer.file_hash
            
            if calculated_hash != expected_hash:
                raise ValueError(
                    f"Hash mismatch: calculated {calculated_hash}, expected {expected_hash}"
                )
            
            # 3. Parse and validate JSON structure
            try:
                map_data = json.loads(file_data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ValueError(f"Invalid JSON data: {e}")
            
            # Validate map structure (using validator)
            from ..utils.validator import MapValidator
            validator = MapValidator()
            validator.validate_map_structure(map_data)
            
            # 4. Backup current map (A/B partition scheme)
            if self.active_map_path.exists():
                if self.logger:
                    self.logger.info("Backing up current map")
                
                # Create backup
                import shutil
                shutil.copy2(self.active_map_path, self.backup_map_path)
            
            # 5. Write new map to temporary location first
            temp_map_path = self.active_map_path.with_suffix('.tmp')
            
            with open(temp_map_path, 'w', encoding='utf-8') as f:
                json.dump(map_data, f, indent=2, ensure_ascii=False)
            
            # 6. Atomic replacement
            temp_map_path.replace(self.active_map_path)
            
            # 7. Calculate transfer statistics
            duration = time.time() - self.current_transfer.start_time
            transfer_rate = self.current_transfer.file_size / duration if duration > 0 else 0
            
            # 8. Log successful completion
            if self.logger:
                self.logger.transfer_complete(
                    self.current_transfer.session_id,
                    True,
                    duration
                )
                
                self.logger.info("Map transfer completed successfully", {
                    "session_id": self.current_transfer.session_id,
                    "version": self.current_transfer.metadata["version"],
                    "file_size": self.current_transfer.file_size,
                    "duration": round(duration, 2),
                    "transfer_rate": round(transfer_rate, 2),
                    "hash": calculated_hash[:16]
                })
            
            # 9. Mark transfer as completed
            self.current_transfer.state = TransferState.COMPLETED
            
            # 10. Prepare completion response
            completion_response = {
                "status": "completed",
                "session_id": self.current_transfer.session_id,
                "file_hash": calculated_hash,
                "file_size": self.current_transfer.file_size,
                "duration": round(duration, 2),
                "transfer_rate": round(transfer_rate, 2),
                "new_version": self.current_transfer.metadata["version"]
            }
            
            # 11. Reset transfer state
            self.current_transfer = None
            
            return completion_response
            
        except Exception as e:
            # Transfer failed - cleanup and log error
            self.current_transfer.state = TransferState.FAILED
            
            if self.logger:
                self.logger.transfer_complete(
                    self.current_transfer.session_id,
                    False,
                    time.time() - self.current_transfer.start_time
                )
                
                self.logger.error("Map transfer failed", {
                    "session_id": self.current_transfer.session_id,
                    "error": str(e)
                }, e)
            
            # Cleanup temporary files
            temp_map_path = self.active_map_path.with_suffix('.tmp')
            if temp_map_path.exists():
                temp_map_path.unlink()
            
            return {
                "status": "error",
                "error_code": "TRANSFER_VALIDATION_FAILED",
                "message": str(e)
            }
    
    def _reconstruct_file(self) -> bytes:
        """Reconstruct complete file from received chunks"""
        
        # Sort chunks by index
        sorted_chunks = sorted(self.current_transfer.received_chunks.items())
        
        # Verify we have all chunks
        expected_indices = set(range(self.current_transfer.total_chunks))
        received_indices = set(self.current_transfer.received_chunks.keys())
        
        missing_chunks = expected_indices - received_indices
        if missing_chunks:
            raise ValueError(f"Missing chunks: {sorted(missing_chunks)}")
        
        # Concatenate chunks in order
        file_data = b''.join(chunk_data for _, chunk_data in sorted_chunks)
        
        # Verify total file size
        if len(file_data) != self.current_transfer.file_size:
            raise ValueError(
                f"File size mismatch: reconstructed {len(file_data)}, "
                f"expected {self.current_transfer.file_size}"
            )
        
        return file_data
    
    def _calculate_total_chunks(self, file_size: int) -> int:
        """Calculate total number of chunks needed"""
        return (file_size + self.chunk_size - 1) // self.chunk_size
    
    def _get_expected_chunk_size(self, chunk_index: int) -> int:
        """Get expected size for specific chunk"""
        if chunk_index == self.current_transfer.total_chunks - 1:
            # Last chunk might be smaller
            remaining = self.current_transfer.file_size % self.chunk_size
            return remaining if remaining > 0 else self.chunk_size
        else:
            return self.chunk_size
    
    def _calculate_progress(self) -> float:
        """Calculate transfer progress percentage"""
        if not self.current_transfer:
            return 0.0
        
        return round(
            (self.current_transfer.chunks_received / self.current_transfer.total_chunks) * 100,
            1
        )
    
    def _get_current_map_version(self) -> int:
        """Get version of currently active map"""
        try:
            if self.active_map_path.exists():
                with open(self.active_map_path, 'r', encoding='utf-8') as f:
                    map_data = json.load(f)
                    return map_data.get("metadata", {}).get("version", 0)
        except Exception:
            pass
        return 0
    
    def _validate_signature(self, metadata: Dict[str, Any], signature: str) -> bool:
        """
        Validate digital signature of metadata
        
        In production: implement ECDSA P-256 verification
        For testing: simplified validation
        """
        
        # TODO: Implement real signature verification
        # 1. Extract public key from certificate
        # 2. Verify signature against metadata hash
        # 3. Check certificate chain and validity
        
        # Simplified validation for testing
        return signature and len(signature) > 10 and signature != "invalid"
    
    def cancel_transfer(self, reason: str = "User cancelled") -> Dict[str, Any]:
        """Cancel current transfer"""
        
        if not self.current_transfer:
            return {"status": "no_active_transfer"}
        
        session_id = self.current_transfer.session_id
        self.current_transfer.state = TransferState.CANCELLED
        
        if self.logger:
            self.logger.info("Transfer cancelled", {
                "session_id": session_id,
                "reason": reason,
                "chunks_received": self.current_transfer.chunks_received,
                "total_chunks": self.current_transfer.total_chunks
            })
        
        self.current_transfer = None
        
        return {
            "status": "cancelled",
            "session_id": session_id,
            "reason": reason
        }
    
    def get_transfer_status(self) -> Dict[str, Any]:
        """Get current transfer status"""
        
        if not self.current_transfer:
            return {"status": "no_active_transfer"}
        
        # Check for timeout
        current_time = time.time()
        if current_time - self.current_transfer.last_activity > self.transfer_timeout:
            self.cancel_transfer("Transfer timeout")
            return {"status": "timeout"}
        
        return {
            "status": "active",
            "session_id": self.current_transfer.session_id,
            "state": self.current_transfer.state.value,
            "chunks_received": self.current_transfer.chunks_received,
            "total_chunks": self.current_transfer.total_chunks,
            "progress": self._calculate_progress(),
            "file_size": self.current_transfer.file_size,
            "elapsed_time": current_time - self.current_transfer.start_time
        }
    
    def set_progress_callback(self, callback: Callable[[int, int], None]):
        """Set callback function for progress updates"""
        self.progress_callback = callback