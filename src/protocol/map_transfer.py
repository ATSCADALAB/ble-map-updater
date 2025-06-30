#!/usr/bin/env python3
"""
Map Transfer Manager for BLE System
Handles chunked file transfer với compression và validation

FEATURES:
- Chunked transfer protocol
- File compression/decompression
- Hash validation
- Progress tracking
- Resume capability
"""

import time
import json
import hashlib
import gzip
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass


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


@dataclass
class TransferSession:
    """Transfer session data"""
    session_id: str
    file_size: int
    total_chunks: int
    chunk_size: int
    file_hash: str
    version: int
    state: TransferState
    start_time: float
    received_chunks: Dict[int, bytes]
    bytes_received: int = 0
    last_chunk_time: float = 0.0
    compressed: bool = False
    compressed_hash: str = ""


class MapTransferManager:
    """
    Manages map file transfers với enhanced features
    """
    
    def __init__(self, config: Dict[str, Any], logger=None):
        self.config = config
        self.logger = logger
        
        # Configuration
        self.chunk_size = config.get("ble", {}).get("chunk_size", 128)
        self.max_transfer_size = config.get("ble", {}).get("max_transfer_size", 5242880)  # 5MB
        self.compression_enabled = config.get("ble", {}).get("compression_enabled", True)
        self.compression_threshold = config.get("ble", {}).get("compression_threshold", 1048576)  # 1MB
        
        # Storage paths
        storage_config = config.get("storage", {})
        self.maps_dir = Path(storage_config.get("maps_dir", "./maps"))
        self.active_map_path = Path(storage_config.get("active_map", "./maps/active/current_map.json"))
        self.backup_map_path = Path(storage_config.get("backup_map", "./maps/backup/backup_map.json"))
        self.temp_dir = Path(storage_config.get("temp_dir", "./maps/temp"))
        
        # Create directories
        self.maps_dir.mkdir(parents=True, exist_ok=True)
        self.active_map_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_map_path.parent.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Current transfer session
        self.current_transfer: Optional[TransferSession] = None
        
        # Progress callback
        self.progress_callback: Optional[Callable] = None
        
        # Rate limiting
        max_chunks_per_second = config.get("ble", {}).get("max_chunks_per_second", 10)
        self.chunk_interval = 1.0 / max_chunks_per_second if max_chunks_per_second > 0 else 0
        
        if self.logger:
            self.logger.system_logger.info("MapTransferManager initialized", {
                "max_transfer_size": self.max_transfer_size,
                "chunk_size": self.chunk_size,
                "compression_enabled": self.compression_enabled
            })
    
    def set_progress_callback(self, callback: Callable):
        """Set progress callback function"""
        self.progress_callback = callback
    
    def start_transfer(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Initialize map transfer với metadata validation
        """
        
        try:
            # Check if transfer already active
            if self.current_transfer and self.current_transfer.state not in [
                TransferState.COMPLETED, TransferState.FAILED, TransferState.CANCELLED
            ]:
                return {
                    "status": "error",
                    "error_code": "TRANSFER_ALREADY_ACTIVE",
                    "message": "Transfer already in progress"
                }
            
            # Validate metadata
            required_fields = ["file_size", "file_hash", "version"]
            for field in required_fields:
                if field not in metadata:
                    return {
                        "status": "error",
                        "error_code": "INVALID_METADATA",
                        "message": f"Missing required field: {field}"
                    }
            
            # Validate file size
            file_size = metadata["file_size"]
            if file_size > self.max_transfer_size:
                return {
                    "status": "error",
                    "error_code": "FILE_TOO_LARGE",
                    "message": f"File size {file_size} exceeds limit {self.max_transfer_size}"
                }
            
            # Validate version
            new_version = metadata["version"]
            current_version = self._get_current_map_version()
            if new_version <= current_version:
                return {
                    "status": "error",
                    "error_code": "VERSION_TOO_OLD",
                    "message": f"Version {new_version} is not newer than current {current_version}"
                }
            
            # Calculate chunks
            total_chunks = (file_size + self.chunk_size - 1) // self.chunk_size
            
            # Create session
            session_id = self._generate_session_id()
            
            self.current_transfer = TransferSession(
                session_id=session_id,
                file_size=file_size,
                total_chunks=total_chunks,
                chunk_size=self.chunk_size,
                file_hash=metadata["file_hash"],
                version=new_version,
                state=TransferState.METADATA_RECEIVED,
                start_time=time.time(),
                received_chunks={},
                compressed=metadata.get("compression", False),
                compressed_hash=metadata.get("compressed_hash", "")
            )
            
            if self.logger:
                self.logger.transfer_logger.info("Transfer initialized", {
                    "session_id": session_id,
                    "file_size": file_size,
                    "total_chunks": total_chunks,
                    "version": new_version
                })
            
            return {
                "status": "ready",
                "session_id": session_id,
                "chunk_size": self.chunk_size,
                "total_chunks": total_chunks,
                "expected_hash": metadata["file_hash"]
            }
            
        except Exception as e:
            if self.logger:
                self.logger.system_logger.error("Transfer initialization failed", {
                    "error": str(e),
                    "metadata": metadata
                })
            
            return {
                "status": "error",
                "error_code": "INIT_FAILED",
                "message": str(e)
            }
    
    def receive_chunk(self, chunk_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process received chunk data
        """
        
        if not self.current_transfer:
            return {
                "status": "error",
                "error_code": "NO_ACTIVE_TRANSFER",
                "message": "No active transfer session"
            }
        
        try:
            # Validate chunk data
            required_fields = ["chunk_index", "data"]
            for field in required_fields:
                if field not in chunk_data:
                    return {
                        "status": "error",
                        "error_code": "INVALID_CHUNK_DATA",
                        "message": f"Missing field: {field}"
                    }
            
            chunk_index = chunk_data["chunk_index"]
            hex_data = chunk_data["data"]
            
            # Validate chunk index
            if chunk_index < 0 or chunk_index >= self.current_transfer.total_chunks:
                return {
                    "status": "error",
                    "error_code": "CHUNK_OUT_OF_RANGE",
                    "message": f"Chunk index {chunk_index} out of range"
                }
            
            # Check for duplicate
            if chunk_index in self.current_transfer.received_chunks:
                return {
                    "status": "duplicate",
                    "message": f"Chunk {chunk_index} already received"
                }
            
            # Decode chunk data
            try:
                chunk_bytes = bytes.fromhex(hex_data)
            except ValueError:
                return {
                    "status": "error",
                    "error_code": "INVALID_HEX_DATA",
                    "message": "Invalid hex encoding"
                }
            
            # Validate checksum if provided
            if "checksum" in chunk_data:
                expected_checksum = chunk_data["checksum"]
                actual_checksum = hashlib.md5(chunk_bytes).hexdigest()
                if actual_checksum != expected_checksum:
                    return {
                        "status": "error",
                        "error_code": "CHECKSUM_MISMATCH",
                        "message": "Chunk checksum mismatch"
                    }
            
            # Store chunk
            self.current_transfer.received_chunks[chunk_index] = chunk_bytes
            self.current_transfer.bytes_received += len(chunk_bytes)
            self.current_transfer.last_chunk_time = time.time()
            self.current_transfer.state = TransferState.RECEIVING_CHUNKS
            
            # Calculate progress
            chunks_received = len(self.current_transfer.received_chunks)
            progress = chunks_received / self.current_transfer.total_chunks * 100
            
            # Update progress
            if self.progress_callback:
                metrics = {
                    "transfer_rate_bps": self._calculate_transfer_rate(),
                    "elapsed_time": time.time() - self.current_transfer.start_time
                }
                self.progress_callback(chunks_received, self.current_transfer.total_chunks, progress, metrics)
            
            # Check if transfer complete
            if chunks_received == self.current_transfer.total_chunks:
                return self.complete_transfer()
            
            return {
                "status": "received",
                "progress": progress,
                "chunks_received": chunks_received,
                "total_chunks": self.current_transfer.total_chunks
            }
            
        except Exception as e:
            if self.logger:
                self.logger.system_logger.error("Chunk processing failed", {
                    "error": str(e),
                    "chunk_data": chunk_data
                })
            
            return {
                "status": "error",
                "error_code": "CHUNK_PROCESSING_FAILED",
                "message": str(e)
            }
    
    def complete_transfer(self) -> Dict[str, Any]:
        """
        Complete transfer và validate file
        """
        
        if not self.current_transfer:
            return {
                "status": "error",
                "error_code": "NO_ACTIVE_TRANSFER",
                "message": "No active transfer session"
            }
        
        try:
            self.current_transfer.state = TransferState.VALIDATING
            
            # Reconstruct file
            file_data = self._reconstruct_file()
            
            # Validate hash
            if self.current_transfer.compressed and self.current_transfer.compressed_hash:
                # Validate compressed hash
                actual_hash = hashlib.sha256(file_data).hexdigest()
                if actual_hash != self.current_transfer.compressed_hash:
                    raise ValueError("Compressed file hash mismatch")
                
                # Decompress
                try:
                    file_data = gzip.decompress(file_data)
                except Exception as e:
                    raise ValueError(f"Decompression failed: {e}")
            
            # Validate final hash
            actual_hash = hashlib.sha256(file_data).hexdigest()
            if actual_hash != self.current_transfer.file_hash:
                raise ValueError("File hash mismatch")
            
            # Validate JSON
            try:
                map_data = json.loads(file_data.decode('utf-8'))
            except Exception as e:
                raise ValueError(f"Invalid JSON: {e}")
            
            # Save file atomically
            self.current_transfer.state = TransferState.COMPLETING
            self._save_map_atomically(map_data)
            
            # Update state
            self.current_transfer.state = TransferState.COMPLETED
            
            completion_time = time.time() - self.current_transfer.start_time
            
            if self.logger:
                self.logger.transfer_logger.info("Transfer completed successfully", {
                    "session_id": self.current_transfer.session_id,
                    "file_size": self.current_transfer.file_size,
                    "completion_time": completion_time
                })
            
            return {
                "status": "completed",
                "session_id": self.current_transfer.session_id,
                "file_size": len(file_data),
                "completion_time": completion_time,
                "map_version": self.current_transfer.version
            }
            
        except Exception as e:
            self.current_transfer.state = TransferState.FAILED
            
            if self.logger:
                self.logger.system_logger.error("Transfer completion failed", {
                    "session_id": self.current_transfer.session_id,
                    "error": str(e)
                })
            
            return {
                "status": "error",
                "error_code": "COMPLETION_FAILED",
                "message": str(e)
            }
    
    def _reconstruct_file(self) -> bytes:
        """Reconstruct complete file from chunks"""
        
        # Sort chunks by index
        sorted_chunks = sorted(self.current_transfer.received_chunks.items())
        
        # Verify all chunks received
        expected_indices = set(range(self.current_transfer.total_chunks))
        received_indices = set(self.current_transfer.received_chunks.keys())
        
        missing_chunks = expected_indices - received_indices
        if missing_chunks:
            raise ValueError(f"Missing chunks: {sorted(missing_chunks)}")
        
        # Concatenate chunks
        file_data = b''.join(chunk_data for _, chunk_data in sorted_chunks)
        
        return file_data
    
    def _save_map_atomically(self, map_data: Dict[str, Any]):
        """Save map file atomically"""
        
        # Create backup of current map
        if self.active_map_path.exists():
            import shutil
            shutil.copy2(self.active_map_path, self.backup_map_path)
        
        # Write to temporary file first
        temp_file = self.temp_dir / f"new_map_{int(time.time())}.json"
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(map_data, f, indent=2, ensure_ascii=False)
        
        # Atomic move
        temp_file.replace(self.active_map_path)
    
    def _get_current_map_version(self) -> int:
        """Get current map version"""
        
        try:
            if self.active_map_path.exists():
                with open(self.active_map_path, 'r', encoding='utf-8') as f:
                    map_data = json.load(f)
                return map_data.get("metadata", {}).get("version", 0)
        except Exception:
            pass
        
        return 0
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _calculate_transfer_rate(self) -> float:
        """Calculate current transfer rate in bytes per second"""
        
        if not self.current_transfer:
            return 0.0
        
        elapsed_time = time.time() - self.current_transfer.start_time
        if elapsed_time <= 0:
            return 0.0
        
        return self.current_transfer.bytes_received / elapsed_time
    
    def get_transfer_status(self) -> Dict[str, Any]:
        """Get current transfer status"""
        
        if not self.current_transfer:
            return {
                "state": TransferState.IDLE.value,
                "active_transfer": False
            }
        
        chunks_received = len(self.current_transfer.received_chunks)
        progress = chunks_received / self.current_transfer.total_chunks * 100
        
        return {
            "state": self.current_transfer.state.value,
            "active_transfer": True,
            "session_id": self.current_transfer.session_id,
            "progress": progress,
            "chunks_received": chunks_received,
            "total_chunks": self.current_transfer.total_chunks,
            "bytes_received": self.current_transfer.bytes_received,
            "file_size": self.current_transfer.file_size,
            "transfer_rate_bps": self._calculate_transfer_rate(),
            "elapsed_time": time.time() - self.current_transfer.start_time
        }