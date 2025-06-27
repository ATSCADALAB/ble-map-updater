"""
Logging system cho BLE Map Updater
Handles: File logging, console output, performance tracking
"""

import logging
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

class MapUpdaterLogger:
    """
    Centralized logging cho map update system
    
    Features:
    - File và console logging
    - Structured JSON logs  
    - Performance timing
    - Security event logging
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logs_dir = Path(config["storage"]["logs_dir"])
        self.logs_dir.mkdir(exist_ok=True)
        
        # Setup loggers
        self._setup_loggers()
        
    def _setup_loggers(self):
        """Setup different loggers for different purposes"""
        
        # Main system logger
        self.system_logger = self._create_logger(
            "system", 
            self.logs_dir / "system.log",
            logging.INFO
        )
        
        # Security events logger
        self.security_logger = self._create_logger(
            "security",
            self.logs_dir / "security.log", 
            logging.WARNING
        )
        
        # Transfer logger
        self.transfer_logger = self._create_logger(
            "transfer",
            self.logs_dir / "transfers.log",
            logging.INFO
        )
        
    def _create_logger(self, name: str, log_file: Path, level: int) -> logging.Logger:
        """Create individual logger with file and console handlers"""
        
        logger = logging.getLogger(f"map_updater.{name}")
        logger.setLevel(level)
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # File handler
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Console handler (if debug mode)
        if self.config["system"]["debug_mode"]:
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter(
                '%(levelname)s: %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
            
        return logger
    
    # System events
    def info(self, message: str, data: Optional[Dict] = None):
        """Log general system information"""
        log_entry = self._format_log_entry(message, data)
        self.system_logger.info(log_entry)
        
    def warning(self, message: str, data: Optional[Dict] = None):
        """Log system warnings"""
        log_entry = self._format_log_entry(message, data)
        self.system_logger.warning(log_entry)
        
    def error(self, message: str, data: Optional[Dict] = None, exc: Optional[Exception] = None):
        """Log system errors"""
        if exc:
            data = data or {}
            data["exception"] = str(exc)
            data["exception_type"] = type(exc).__name__
            
        log_entry = self._format_log_entry(message, data)
        self.system_logger.error(log_entry)
    
    # Security events
    def security_event(self, event_type: str, details: Dict[str, Any]):
        """Log security-related events"""
        log_data = {
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "details": details
        }
        self.security_logger.warning(json.dumps(log_data))
    
    # Transfer events  
    def transfer_start(self, session_id: str, file_size: int, chunks: int):
        """Log transfer start"""
        data = {
            "session_id": session_id,
            "file_size": file_size,
            "total_chunks": chunks,
            "timestamp": datetime.now().isoformat()
        }
        self.transfer_logger.info(f"TRANSFER_START | {json.dumps(data)}")
    
    def transfer_progress(self, session_id: str, chunk_index: int, total_chunks: int):
        """Log transfer progress"""
        progress = (chunk_index + 1) / total_chunks * 100
        data = {
            "session_id": session_id,
            "chunk": chunk_index + 1,
            "total": total_chunks,
            "progress": round(progress, 1)
        }
        
        # Only log every 10% to avoid spam
        if chunk_index % max(1, total_chunks // 10) == 0:
            self.transfer_logger.info(f"TRANSFER_PROGRESS | {json.dumps(data)}")
    
    def transfer_complete(self, session_id: str, success: bool, duration: float):
        """Log transfer completion"""
        data = {
            "session_id": session_id,
            "success": success,
            "duration_seconds": round(duration, 2),
            "timestamp": datetime.now().isoformat()
        }
        
        level = "TRANSFER_SUCCESS" if success else "TRANSFER_FAILED"
        self.transfer_logger.info(f"{level} | {json.dumps(data)}")
    
    def _format_log_entry(self, message: str, data: Optional[Dict] = None) -> str:
        """Format log entry with optional structured data"""
        if data:
            return f"{message} | DATA: {json.dumps(data)}"
        return message

class PerformanceTimer:
    """
    Context manager để đo performance
    
    Usage:
        with PerformanceTimer("operation_name") as timer:
            # do something
            pass
        print(f"Operation took {timer.duration}s")
    """
    
    def __init__(self, operation_name: str, logger: Optional[MapUpdaterLogger] = None):
        self.operation_name = operation_name
        self.logger = logger
        self.start_time = None
        self.duration = None
        
    def __enter__(self):
        self.start_time = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.time() - self.start_time
        
        if self.logger:
            perf_data = {
                "operation": self.operation_name,
                "duration_seconds": round(self.duration, 4),
                "timestamp": datetime.now().isoformat()
            }
            
            if exc_type:
                perf_data["error"] = str(exc_val)
                self.logger.error(f"Operation failed: {self.operation_name}", perf_data)
            else:
                self.logger.info(f"Operation completed: {self.operation_name}", perf_data)

# Factory function
def create_logger(config_path: str = "config.json") -> MapUpdaterLogger:
    """Create logger instance from config file"""
    import json
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    return MapUpdaterLogger(config)