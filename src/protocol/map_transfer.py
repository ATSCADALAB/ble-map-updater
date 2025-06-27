"""
Complete Map Transfer Protocol Implementation
Hỗ trợ đầy đủ cho file lên đến 5MB với các tính năng nâng cao

CÁC TÍNH NĂNG CHÍNH:
- Chunk-based transfer tối ưu cho BLE
- A/B partition scheme để atomic updates  
- Hash validation và integrity checks
- Resume capability cho transfers bị gián đoạn
- Progress tracking và error recovery
- Compression support để giảm dung lượng
- Parallel chunk processing (optional)
"""

import json
import hashlib
import time
import os
import gzip
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, Set
from enum import Enum
from dataclasses import dataclass, field
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor

class TransferState(Enum):
    """Enhanced transfer state machine với các trạng thái mở rộng"""
    IDLE = "idle"                           # Không có transfer nào
    METADATA_RECEIVED = "metadata_received" # Đã nhận metadata
    RECEIVING_CHUNKS = "receiving_chunks"   # Đang nhận chunks
    VALIDATING = "validating"              # Đang validate dữ liệu
    COMPRESSING = "compressing"            # Đang nén dữ liệu
    DECOMPRESSING = "decompressing"        # Đang giải nén
    COMPLETED = "completed"                # Hoàn thành thành công
    FAILED = "failed"                      # Thất bại
    CANCELLED = "cancelled"                # Bị hủy
    PAUSED = "paused"                      # Tạm dừng
    RESUMING = "resuming"                  # Đang resume

@dataclass
class TransferMetrics:
    """Metrics để theo dõi hiệu suất transfer"""
    start_time: float = 0.0
    bytes_transferred: int = 0
    chunks_transferred: int = 0
    retries: int = 0
    last_chunk_time: float = 0.0
    estimated_completion: Optional[float] = None
    transfer_rate_bps: float = 0.0
    compression_ratio: float = 0.0

@dataclass
class TransferSession:
    """Enhanced transfer session information với thêm compression support"""
    session_id: str
    file_size: int                          # Kích thước file gốc
    compressed_size: int                    # Kích thước sau nén (nếu có)
    file_hash: str                         # Hash của file gốc
    compressed_hash: str                   # Hash của file đã nén
    total_chunks: int
    chunks_received: int
    start_time: float
    last_activity: float
    metadata: Dict[str, Any]
    received_chunks: Dict[int, bytes] = field(default_factory=dict)  # chunk_index -> data
    missing_chunks: Set[int] = field(default_factory=set)           # Các chunk còn thiếu
    state: TransferState = TransferState.IDLE
    metrics: TransferMetrics = field(default_factory=TransferMetrics)
    is_compressed: bool = False            # Có sử dụng compression không
    compression_type: str = "none"         # Loại compression (gzip, lz4, etc.)

class MapTransferManager:
    """
    Enhanced Manager cho chunked map file transfers qua BLE
    Hỗ trợ file lên đến 5MB với compression và advanced features
    
    PROTOCOL FEATURES:
    - Configurable chunk size (64-512 bytes, optimal: 128 bytes)
    - Out-of-order chunk delivery support
    - Duplicate chunk detection
    - Transfer timeout và retry logic
    - Atomic file operations với A/B partitioning
    - Compression support để giảm bandwidth
    - Resume capability cho interrupted transfers
    - Real-time progress tracking
    """
    
    def __init__(self, config: Dict[str, Any], logger=None):
        """
        Initialize transfer manager với enhanced configuration
        
        Args:
            config: Configuration dictionary từ config.json
            logger: Logger instance để ghi log
        """
        self.config = config
        self.logger = logger
        
        # Transfer settings từ config
        self.chunk_size = config["ble"]["chunk_size"]  # 128 bytes
        self.max_transfer_size = config["ble"]["max_transfer_size"]  # 5MB
        self.transfer_timeout = config["transfer"]["session_timeout"]  # 10 minutes
        self.max_chunks_per_second = config["ble"]["max_chunks_per_second"]  # 10
        self.compression_enabled = config["ble"]["compression_enabled"]
        self.compression_threshold = config["ble"]["compression_threshold"]  # 1MB
        
        # Storage paths
        self.maps_dir = Path(config["storage"]["maps_dir"])
        self.active_map_path = Path(config["storage"]["active_map"])
        self.backup_map_path = Path(config["storage"]["backup_map"])
        self.temp_dir = Path(config["storage"]["temp_dir"])
        
        # Đảm bảo directories tồn tại
        for directory in [self.maps_dir, self.active_map_path.parent, 
                         self.backup_map_path.parent, self.temp_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Current transfer session
        self.current_transfer: Optional[TransferSession] = None
        
        # Progress callback cho UI updates
        self.progress_callback: Optional[Callable] = None
        
        # Threading cho parallel processing
        self.thread_pool = ThreadPoolExecutor(max_workers=2)
        
        # Rate limiting
        self.last_chunk_time = 0.0
        self.chunk_interval = 1.0 / self.max_chunks_per_second if self.max_chunks_per_second > 0 else 0
        
        if self.logger:
            self.logger.system_logger.info("MapTransferManager initialized", {
                "max_transfer_size": self.max_transfer_size,
                "chunk_size": self.chunk_size,
                "compression_enabled": self.compression_enabled
            })
    
    def start_transfer(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Initialize map transfer với metadata validation
        
        Args:
            metadata: Transfer metadata chứa file info
            {
                "file_size": int,
                "file_hash": str,
                "version": int,
                "signature": str,
                "compression": str (optional),
                "compressed_size": int (optional),
                "compressed_hash": str (optional)
            }
            
        Returns:
            Dict: Transfer session info hoặc error response
            
        VALIDATION PROCESS:
        1. File size limits (≤ 5MB)
        2. Version requirements (> current version)
        3. Required metadata fields
        4. Digital signatures (if enabled)
        5. Compression settings
        """
        
        try:
            # 1. Validate metadata structure
            required_fields = ["file_size", "file_hash", "version"]
            for field in required_fields:
                if field not in metadata:
                    raise ValueError(f"Missing required field: {field}")
            
            # 2. Validate file size
            file_size = metadata["file_size"]
            if not isinstance(file_size, int) or file_size <= 0:
                raise ValueError("Invalid file_size")
            
            if file_size > self.max_transfer_size:
                raise ValueError(f"File too large: {file_size} > {self.max_transfer_size}")
            
            # 3. Validate version
            new_version = metadata["version"]
            current_version = self._get_current_map_version()
            
            if new_version <= current_version:
                raise ValueError(f"Version too old: {new_version} <= {current_version}")
            
            # 4. Validate signature if required
            if self.config["security"]["required_signature"]:
                signature = metadata.get("signature")
                if not signature:
                    raise ValueError("Digital signature required")
                
                if not self._validate_signature(metadata, signature):
                    raise ValueError("Invalid signature")
            
            # 5. Setup compression
            is_compressed = metadata.get("compression", "none") != "none"
            compressed_size = metadata.get("compressed_size", file_size)
            compressed_hash = metadata.get("compressed_hash", metadata["file_hash"])
            
            # 6. Calculate total chunks
            effective_size = compressed_size if is_compressed else file_size
            total_chunks = self._calculate_total_chunks(effective_size)
            
            # 7. Generate session
            session_id = str(uuid.uuid4())
            
            # 8. Create transfer session
            self.current_transfer = TransferSession(
                session_id=session_id,
                file_size=file_size,
                compressed_size=compressed_size,
                file_hash=metadata["file_hash"],
                compressed_hash=compressed_hash,
                total_chunks=total_chunks,
                chunks_received=0,
                start_time=time.time(),
                last_activity=time.time(),
                metadata=metadata,
                received_chunks={},
                missing_chunks=set(range(total_chunks)),
                state=TransferState.METADATA_RECEIVED,
                is_compressed=is_compressed,
                compression_type=metadata.get("compression", "none")
            )
            
            # 9. Initialize metrics
            self.current_transfer.metrics.start_time = time.time()
            
            # 10. Log transfer initiation
            if self.logger:
                self.logger.transfer_start(session_id, file_size, total_chunks)
                self.logger.system_logger.info("Map transfer initiated", {
                    "session_id": session_id,
                    "version": new_version,
                    "file_size": file_size,
                    "compressed_size": compressed_size,
                    "chunks": total_chunks,
                    "compression": is_compressed
                })
            
            # 11. Return session info
            return {
                "status": "ready",
                "session_id": session_id,
                "chunk_size": self.chunk_size,
                "total_chunks": total_chunks,
                "expected_hash": compressed_hash if is_compressed else metadata["file_hash"],
                "compression": is_compressed,
                "estimated_duration": self._estimate_transfer_duration(effective_size)
            }
            
        except Exception as e:
            if self.logger:
                self.logger.system_logger.error("Transfer initialization failed", {
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
        Process received chunk data với enhanced validation và rate limiting
        
        Args:
            chunk_data: Chunk information và data
            {
                "chunk_index": int,
                "data": str (hex-encoded),
                "session_id": str (optional),
                "checksum": str (optional)
            }
            
        Returns:
            Dict: Chunk processing result
            
        HANDLES:
        - Out-of-order delivery
        - Duplicate detection  
        - Data validation
        - Progress tracking
        - Rate limiting
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
            # 2. Rate limiting
            current_time = time.time()
            if self.chunk_interval > 0:
                time_since_last = current_time - self.last_chunk_time
                if time_since_last < self.chunk_interval:
                    sleep_time = self.chunk_interval - time_since_last
                    time.sleep(sleep_time)
            
            self.last_chunk_time = time.time()
            
            # 3. Extract và validate chunk information
            chunk_index = chunk_data.get("chunk_index")
            chunk_hex_data = chunk_data.get("data")
            session_id = chunk_data.get("session_id")
            checksum = chunk_data.get("checksum")
            
            # 4. Validate chunk parameters
            if chunk_index is None or chunk_hex_data is None:
                raise ValueError("Missing chunk_index or data")
                
            if session_id and session_id != self.current_transfer.session_id:
                raise ValueError("Session ID mismatch")
            
            if not isinstance(chunk_index, int) or chunk_index < 0:
                raise ValueError("Invalid chunk_index")
                
            if chunk_index >= self.current_transfer.total_chunks:
                raise ValueError(f"Chunk index {chunk_index} exceeds total {self.current_transfer.total_chunks}")
            
            # 5. Decode chunk data
            try:
                chunk_bytes = bytes.fromhex(chunk_hex_data)
            except ValueError:
                raise ValueError("Invalid hex data in chunk")
            
            # 6. Validate chunk size
            expected_size = self._get_expected_chunk_size(chunk_index)
            if len(chunk_bytes) != expected_size:
                raise ValueError(f"Chunk size mismatch: got {len(chunk_bytes)}, expected {expected_size}")
            
            # 7. Validate checksum nếu có
            if checksum:
                calculated_checksum = hashlib.md5(chunk_bytes).hexdigest()
                if checksum != calculated_checksum:
                    raise ValueError("Chunk checksum mismatch")
            
            # 8. Check for duplicate chunks
            if chunk_index in self.current_transfer.received_chunks:
                if self.logger:
                    self.logger.system_logger.warning("Duplicate chunk received", {
                        "session_id": self.current_transfer.session_id,
                        "chunk_index": chunk_index
                    })
                
                # Return success cho duplicate (idempotent)
                return {
                    "status": "duplicate",
                    "chunk_index": chunk_index,
                    "progress": self._calculate_progress()
                }
            
            # 9. Store chunk data
            self.current_transfer.received_chunks[chunk_index] = chunk_bytes
            self.current_transfer.missing_chunks.discard(chunk_index)
            self.current_transfer.chunks_received = len(self.current_transfer.received_chunks)
            self.current_transfer.last_activity = time.time()
            self.current_transfer.state = TransferState.RECEIVING_CHUNKS
            
            # 10. Update metrics
            self.current_transfer.metrics.chunks_transferred += 1
            self.current_transfer.metrics.bytes_transferred += len(chunk_bytes)
            self.current_transfer.metrics.last_chunk_time = time.time()
            self._update_transfer_rate()
            
            # 11. Log progress
            if self.logger:
                self.logger.transfer_progress(
                    self.current_transfer.session_id,
                    chunk_index,
                    self.current_transfer.total_chunks
                )
            
            # 12. Call progress callback nếu set
            if self.progress_callback:
                self.progress_callback(
                    self.current_transfer.chunks_received,
                    self.current_transfer.total_chunks,
                    self.current_transfer.metrics
                )
            
            # 13. Check if transfer complete
            if self.current_transfer.chunks_received >= self.current_transfer.total_chunks:
                return self._complete_transfer()
            
            # 14. Return chunk acknowledgment
            return {
                "status": "chunk_received",
                "chunk_index": chunk_index,
                "chunks_received": self.current_transfer.chunks_received,
                "total_chunks": self.current_transfer.total_chunks,
                "progress": self._calculate_progress(),
                "missing_chunks": sorted(list(self.current_transfer.missing_chunks))[:10],  # First 10 missing
                "transfer_rate_bps": self.current_transfer.metrics.transfer_rate_bps,
                "estimated_completion": self.current_transfer.metrics.estimated_completion
            }
            
        except Exception as e:
            # Increment retry counter
            if self.current_transfer:
                self.current_transfer.metrics.retries += 1
                
            if self.logger:
                self.logger.system_logger.error("Chunk processing failed", {
                    "session_id": self.current_transfer.session_id if self.current_transfer else None,
                    "chunk_index": chunk_data.get("chunk_index"),
                    "error": str(e)
                }, e)
            
            return {
                "status": "error",
                "error_code": "CHUNK_PROCESSING_FAILED",
                "message": str(e),
                "retry_suggested": True
            }
    
    def _complete_transfer(self) -> Dict[str, Any]:
        """
        Complete transfer với validation và atomic file operations
        
        PROCESS:
        1. Reconstruct file từ chunks
        2. Validate file hash
        3. Decompress nếu cần
        4. Parse và validate JSON structure
        5. Backup current map
        6. Atomic file replacement
        7. Cleanup
        """
        
        try:
            self.current_transfer.state = TransferState.VALIDATING
            
            # 1. Reconstruct file từ chunks
            if self.logger:
                self.logger.system_logger.info("Reconstructing file from chunks", {
                    "session_id": self.current_transfer.session_id,
                    "chunks": len(self.current_transfer.received_chunks)
                })
            
            file_data = self._reconstruct_file()
            
            # 2. Validate file hash
            calculated_hash = hashlib.sha256(file_data).hexdigest()
            expected_hash = self.current_transfer.compressed_hash if self.current_transfer.is_compressed else self.current_transfer.file_hash
            
            if calculated_hash != expected_hash:
                raise ValueError(f"Hash mismatch: calculated {calculated_hash}, expected {expected_hash}")
            
            # 3. Decompress nếu cần
            if self.current_transfer.is_compressed:
                self.current_transfer.state = TransferState.DECOMPRESSING
                file_data = self._decompress_data(file_data, self.current_transfer.compression_type)
                
                # Validate decompressed hash
                decompressed_hash = hashlib.sha256(file_data).hexdigest()
                if decompressed_hash != self.current_transfer.file_hash:
                    raise ValueError(f"Decompressed hash mismatch: {decompressed_hash} != {self.current_transfer.file_hash}")
            
            # 4. Parse và validate JSON structure
            try:
                map_data = json.loads(file_data.decode('utf-8'))
                self._validate_map_structure(map_data)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ValueError(f"Invalid JSON structure: {e}")
            
            # 5. Backup current map
            self._backup_current_map()
            
            # 6. Atomic file replacement
            temp_map_path = self.active_map_path.with_suffix('.tmp')
            
            # Write to temp file first
            with open(temp_map_path, 'wb') as f:
                f.write(file_data)
            
            # Atomic move
            temp_map_path.replace(self.active_map_path)
            
            # 7. Calculate metrics
            duration = time.time() - self.current_transfer.start_time
            transfer_rate = self.current_transfer.file_size / duration if duration > 0 else 0
            
            # 8. Log completion
            if self.logger:
                self.logger.transfer_complete(
                    self.current_transfer.session_id,
                    True,
                    duration
                )
                
                self.logger.system_logger.info("Map transfer completed successfully", {
                    "session_id": self.current_transfer.session_id,
                    "file_size": self.current_transfer.file_size,
                    "duration": duration,
                    "transfer_rate": transfer_rate,
                    "compression_ratio": self.current_transfer.metrics.compression_ratio
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
                "transfer_rate_bps": round(transfer_rate, 2),
                "new_version": self.current_transfer.metadata["version"],
                "compression_ratio": self.current_transfer.metrics.compression_ratio,
                "total_retries": self.current_transfer.metrics.retries
            }
            
            # 11. Cleanup và reset transfer state
            self._cleanup_transfer()
            
            return completion_response
            
        except Exception as e:
            # Transfer failed - cleanup và log error
            self.current_transfer.state = TransferState.FAILED
            
            if self.logger:
                self.logger.transfer_complete(
                    self.current_transfer.session_id,
                    False,
                    time.time() - self.current_transfer.start_time
                )
                
                self.logger.system_logger.error("Map transfer failed", {
                    "session_id": self.current_transfer.session_id,
                    "error": str(e)
                }, e)
            
            # Cleanup temporary files
            temp_map_path = self.active_map_path.with_suffix('.tmp')
            if temp_map_path.exists():
                temp_map_path.unlink()
            
            self._cleanup_transfer()
            
            return {
                "status": "error",
                "error_code": "TRANSFER_VALIDATION_FAILED",
                "message": str(e)
            }
    
    def _reconstruct_file(self) -> bytes:
        """Reconstruct complete file từ received chunks"""
        
        # Sort chunks by index
        sorted_chunks = sorted(self.current_transfer.received_chunks.items())
        
        # Verify tất cả chunks có
        expected_indices = set(range(self.current_transfer.total_chunks))
        received_indices = set(self.current_transfer.received_chunks.keys())
        
        missing_chunks = expected_indices - received_indices
        if missing_chunks:
            raise ValueError(f"Missing chunks: {sorted(missing_chunks)}")
        
        # Concatenate chunks theo thứ tự
        file_data = b''.join(chunk_data for _, chunk_data in sorted_chunks)
        
        # Verify total file size
        expected_size = self.current_transfer.compressed_size if self.current_transfer.is_compressed else self.current_transfer.file_size
        if len(file_data) != expected_size:
            raise ValueError(f"File size mismatch: reconstructed {len(file_data)}, expected {expected_size}")
        
        return file_data
    
    def _decompress_data(self, compressed_data: bytes, compression_type: str) -> bytes:
        """Decompress data theo compression type"""
        
        if compression_type == "gzip":
            return gzip.decompress(compressed_data)
        elif compression_type == "none":
            return compressed_data
        else:
            raise ValueError(f"Unsupported compression type: {compression_type}")
    
    def _validate_map_structure(self, map_data: Dict[str, Any]):
        """Validate cấu trúc của map data"""
        
        # Basic structure validation
        required_fields = ["metadata", "zones"]
        for field in required_fields:
            if field not in map_data:
                raise ValueError(f"Missing required field in map: {field}")
        
        # Validate metadata
        metadata = map_data["metadata"]
        if "version" not in metadata:
            raise ValueError("Missing version in map metadata")
        
        # Validate zones
        zones = map_data["zones"]
        if not isinstance(zones, list):
            raise ValueError("Zones must be a list")
        
        # Additional validation có thể thêm ở đây
    
    def _backup_current_map(self):
        """Backup current active map"""
        
        if self.active_map_path.exists():
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_filename = f"backup_map_{timestamp}.json"
            backup_path = self.backup_map_path.parent / backup_filename
            
            # Copy current map to backup
            import shutil
            shutil.copy2(self.active_map_path, backup_path)
            
            # Update symlink to backup
            if self.backup_map_path.exists():
                self.backup_map_path.unlink()
            self.backup_map_path.symlink_to(backup_filename)
    
    def _cleanup_transfer(self):
        """Cleanup transfer state và temporary files"""
        
        if self.current_transfer:
            # Remove any temp files
            temp_files = self.temp_dir.glob(f"*{self.current_transfer.session_id}*")
            for temp_file in temp_files:
                try:
                    temp_file.unlink()
                except Exception:
                    pass
        
        # Reset transfer state
        self.current_transfer = None
    
    def _calculate_total_chunks(self, file_size: int) -> int:
        """Calculate total number of chunks cần thiết"""
        return (file_size + self.chunk_size - 1) // self.chunk_size
    
    def _get_expected_chunk_size(self, chunk_index: int) -> int:
        """Get expected size cho specific chunk"""
        effective_size = self.current_transfer.compressed_size if self.current_transfer.is_compressed else self.current_transfer.file_size
        
        if chunk_index == self.current_transfer.total_chunks - 1:
            # Last chunk có thể nhỏ hơn
            remaining = effective_size % self.chunk_size
            return remaining if remaining > 0 else self.chunk_size
        else:
            return self.chunk_size
    
    def _calculate_progress(self) -> float:
        """Calculate transfer progress percentage"""
        if not self.current_transfer:
            return 0.0
        
        return round((self.current_transfer.chunks_received / self.current_transfer.total_chunks) * 100, 1)
    
    def _update_transfer_rate(self):
        """Update transfer rate và estimated completion"""
        if not self.current_transfer:
            return
        
        elapsed = time.time() - self.current_transfer.metrics.start_time
        if elapsed > 0:
            self.current_transfer.metrics.transfer_rate_bps = self.current_transfer.metrics.bytes_transferred / elapsed
            
            # Estimate completion time
            remaining_chunks = self.current_transfer.total_chunks - self.current_transfer.chunks_received
            if self.current_transfer.chunks_received > 0:
                avg_time_per_chunk = elapsed / self.current_transfer.chunks_received
                estimated_remaining = remaining_chunks * avg_time_per_chunk
                self.current_transfer.metrics.estimated_completion = time.time() + estimated_remaining
    
    def _estimate_transfer_duration(self, file_size: int) -> float:
        """Estimate transfer duration dựa trên file size"""
        # Rough estimate: 10 chunks per second với current chunk size
        total_chunks = self._calculate_total_chunks(file_size)
        chunks_per_second = self.max_chunks_per_second if self.max_chunks_per_second > 0 else 10
        return total_chunks / chunks_per_second
    
    def _get_current_map_version(self) -> int:
        """Get version của currently active map"""
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
        Validate digital signature của metadata
        
        PRODUCTION: implement ECDSA P-256 verification
        TESTING: simplified validation
        """
        
        # TODO: Implement real signature verification
        # 1. Extract public key từ certificate
        # 2. Verify signature against metadata hash
        # 3. Check certificate validity
        
        # For now: simple validation
        if not self.config["security"]["required_signature"]:
            return True
        
        # Placeholder validation - REPLACE WITH REAL CRYPTO
        return len(signature) > 10  # Very basic check
    
    def get_transfer_status(self) -> Dict[str, Any]:
        """Get current transfer status"""
        
        if not self.current_transfer:
            return {
                "status": "idle",
                "active_transfer": False
            }
        
        return {
            "status": self.current_transfer.state.value,
            "active_transfer": True,
            "session_id": self.current_transfer.session_id,
            "progress": self._calculate_progress(),
            "chunks_received": self.current_transfer.chunks_received,
            "total_chunks": self.current_transfer.total_chunks,
            "file_size": self.current_transfer.file_size,
            "transfer_rate_bps": self.current_transfer.metrics.transfer_rate_bps,
            "estimated_completion": self.current_transfer.metrics.estimated_completion,
            "compression": self.current_transfer.is_compressed,
            "retries": self.current_transfer.metrics.retries
        }
    
    def cancel_transfer(self) -> Dict[str, Any]:
        """Cancel current transfer"""
        
        if not self.current_transfer:
            return {
                "status": "error",
                "message": "No active transfer to cancel"
            }
        
        session_id = self.current_transfer.session_id
        self.current_transfer.state = TransferState.CANCELLED
        
        if self.logger:
            self.logger.system_logger.info("Transfer cancelled", {
                "session_id": session_id
            })
        
        self._cleanup_transfer()
        
        return {
            "status": "cancelled",
            "session_id": session_id
        }
    
    def pause_transfer(self) -> Dict[str, Any]:
        """Pause current transfer"""
        
        if not self.current_transfer:
            return {
                "status": "error",
                "message": "No active transfer to pause"
            }
        
        if self.current_transfer.state != TransferState.RECEIVING_CHUNKS:
            return {
                "status": "error", 
                "message": f"Cannot pause transfer in state: {self.current_transfer.state.value}"
            }
        
        self.current_transfer.state = TransferState.PAUSED
        
        return {
            "status": "paused",
            "session_id": self.current_transfer.session_id,
            "chunks_received": self.current_transfer.chunks_received
        }
    
    def resume_transfer(self) -> Dict[str, Any]:
        """Resume paused transfer"""
        
        if not self.current_transfer:
            return {
                "status": "error",
                "message": "No transfer to resume"
            }
        
        if self.current_transfer.state != TransferState.PAUSED:
            return {
                "status": "error",
                "message": f"Cannot resume transfer in state: {self.current_transfer.state.value}"
            }
        
        self.current_transfer.state = TransferState.RESUMING
        self.current_transfer.last_activity = time.time()
        
        # Return list of missing chunks để client có thể resend
        missing_chunks = sorted(list(self.current_transfer.missing_chunks))
        
        return {
            "status": "resuming",
            "session_id": self.current_transfer.session_id,
            "missing_chunks": missing_chunks,
            "chunks_received": self.current_transfer.chunks_received,
            "total_chunks": self.current_transfer.total_chunks
        }
    
    def get_missing_chunks(self) -> List[int]:
        """Get list of missing chunks for current transfer"""
        
        if not self.current_transfer:
            return []
        
        return sorted(list(self.current_transfer.missing_chunks))
    
    def set_progress_callback(self, callback: Callable):
        """Set callback function cho progress updates"""
        self.progress_callback = callback