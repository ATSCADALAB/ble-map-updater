#!/usr/bin/env python3
"""
Enhanced Logging System for BLE Map Transfer
Provides structured logging với multiple channels và performance monitoring

FEATURES:
- Multi-channel logging (system, security, transfer, performance)
- Structured log entries với JSON formatting
- Automatic log rotation và retention
- Performance metrics tracking
- Real-time monitoring hooks
- Thread-safe operations
"""

import logging
import logging.handlers
import json
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    """Custom formatter cho structured JSON logs"""
    
    def format(self, record):
        # Base log entry
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_entry['data'] = record.extra_data
        
        if hasattr(record, 'exception_info'):
            log_entry['exception'] = record.exception_info
        
        if hasattr(record, 'performance_metrics'):
            log_entry['metrics'] = record.performance_metrics
        
        return json.dumps(log_entry, ensure_ascii=False)


class MapUpdaterLogger:
    """
    Comprehensive logging system cho BLE Map Transfer
    
    CHANNELS:
    - system: General system events và errors
    - security: Authentication và security events  
    - transfer: Map transfer operations
    - performance: Performance metrics và monitoring
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logs_dir = Path(config["storage"]["logs_dir"])
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Performance tracking
        self.performance_data = {}
        self.transfer_stats = {}
        self._lock = threading.Lock()
        
        # Setup loggers
        self.system_logger = self._setup_logger(
            "system", 
            self.logs_dir / "system.log",
            logging.INFO
        )
        
        self.security_logger = self._setup_logger(
            "security",
            self.logs_dir / "security.log", 
            logging.WARNING
        )
        
        self.transfer_logger = self._setup_logger(
            "transfer",
            self.logs_dir / "transfer.log",
            logging.INFO
        )
        
        self.performance_logger = self._setup_logger(
            "performance",
            self.logs_dir / "performance.log",
            logging.INFO
        )
        
        # Initialize
        self.system_logger.info("MapUpdaterLogger initialized", {
            "logs_dir": str(self.logs_dir),
            "config": {
                "retention_days": config.get("monitoring", {}).get("metrics_retention_days", 7),
                "performance_logging": config.get("monitoring", {}).get("performance_logging", True)
            }
        })
    
    def _setup_logger(self, name: str, log_file: Path, level: int) -> logging.Logger:
        """Setup individual logger với rotation"""
        
        logger = logging.getLogger(f"ble_map_transfer.{name}")
        logger.setLevel(level)
        
        # Remove existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # File handler với rotation
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)
        
        # Console handler for important logs
        if level <= logging.WARNING:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            logger.addHandler(console_handler)
        
        return logger
    
    # System Events
    def system_startup(self, config_info: Dict[str, Any]):
        """Log system startup"""
        self.system_logger.info("BLE System startup", config_info)
    
    def system_shutdown(self, metrics: Dict[str, Any]):
        """Log system shutdown"""
        self.system_logger.info("BLE System shutdown", metrics)
    
    def connection_established(self, client_info: Dict[str, Any]):
        """Log new client connection"""
        self.system_logger.info("Client connected", client_info)
    
    def connection_closed(self, client_info: Dict[str, Any], duration: float):
        """Log client disconnection"""
        self.system_logger.info("Client disconnected", {
            **client_info,
            "connection_duration": duration
        })
    
    # Security Events
    def auth_attempt(self, client_id: str, success: bool, method: str):
        """Log authentication attempt"""
        level = logging.INFO if success else logging.WARNING
        self.security_logger.log(level, "Authentication attempt", {
            "client_id": client_id,
            "success": success,
            "method": method,
            "timestamp": time.time()
        })
    
    def security_violation(self, violation_type: str, details: Dict[str, Any]):
        """Log security violation"""
        self.security_logger.error("Security violation", {
            "violation_type": violation_type,
            "details": details,
            "timestamp": time.time()
        })
    
    # Transfer Events
    def transfer_start(self, session_id: str, file_size: int, total_chunks: int):
        """Log transfer initiation"""
        with self._lock:
            self.transfer_stats[session_id] = {
                "start_time": time.time(),
                "file_size": file_size,
                "total_chunks": total_chunks,
                "chunks_received": 0,
                "bytes_received": 0
            }
        
        self.transfer_logger.info("Transfer started", {
            "session_id": session_id,
            "file_size": file_size,
            "total_chunks": total_chunks
        })
    
    def transfer_progress(self, session_id: str, chunks_received: int, bytes_received: int):
        """Log transfer progress"""
        with self._lock:
            if session_id in self.transfer_stats:
                stats = self.transfer_stats[session_id]
                stats["chunks_received"] = chunks_received
                stats["bytes_received"] = bytes_received
                
                # Calculate metrics
                elapsed = time.time() - stats["start_time"]
                progress = chunks_received / stats["total_chunks"] * 100
                rate_bps = bytes_received / elapsed if elapsed > 0 else 0
                
                # Log every 10% progress
                if chunks_received % (stats["total_chunks"] // 10) == 0:
                    self.transfer_logger.info("Transfer progress", {
                        "session_id": session_id,
                        "progress_percent": round(progress, 1),
                        "chunks_received": chunks_received,
                        "total_chunks": stats["total_chunks"],
                        "rate_bps": round(rate_bps, 2),
                        "elapsed_time": round(elapsed, 2)
                    })
    
    def transfer_complete(self, session_id: str, success: bool, duration: float):
        """Log transfer completion"""
        with self._lock:
            stats = self.transfer_stats.pop(session_id, {})
        
        metrics = {
            "session_id": session_id,
            "success": success,
            "duration": duration,
            **stats
        }
        
        if success:
            self.transfer_logger.info("Transfer completed successfully", metrics)
        else:
            self.transfer_logger.error("Transfer failed", metrics)
    
    # Performance Monitoring
    def log_performance_metrics(self, metrics: Dict[str, Any]):
        """Log performance metrics"""
        if self.config.get("monitoring", {}).get("performance_logging", True):
            self.performance_logger.info("Performance metrics", {
                "timestamp": time.time(),
                "metrics": metrics
            })
    
    def memory_usage(self, usage_mb: float):
        """Log memory usage"""
        self.performance_logger.info("Memory usage", {
            "usage_mb": usage_mb,
            "timestamp": time.time()
        })
    
    def cpu_usage(self, usage_percent: float):
        """Log CPU usage"""
        self.performance_logger.info("CPU usage", {
            "usage_percent": usage_percent,
            "timestamp": time.time()
        })
    
    # Custom logging with extra data
    def log_with_extra(self, logger_name: str, level: int, message: str, 
                      extra_data: Optional[Dict[str, Any]] = None,
                      exception: Optional[Exception] = None):
        """Log với additional structured data"""
        
        logger = getattr(self, f"{logger_name}_logger", self.system_logger)
        
        # Create log record
        record = logger.makeRecord(
            logger.name, level, "", 0, message, (), None
        )
        
        if extra_data:
            record.extra_data = extra_data
        
        if exception:
            record.exception_info = {
                "type": type(exception).__name__,
                "message": str(exception),
                "traceback": self._format_exception(exception)
            }
        
        logger.handle(record)
    
    def _format_exception(self, exception: Exception) -> str:
        """Format exception cho logging"""
        import traceback
        return ''.join(traceback.format_exception(
            type(exception), exception, exception.__traceback__
        ))
    
    # Context managers
    def performance_context(self, operation_name: str):
        """Context manager cho performance monitoring"""
        return PerformanceContext(self, operation_name)
    
    def get_transfer_stats(self) -> Dict[str, Any]:
        """Get current transfer statistics"""
        with self._lock:
            return dict(self.transfer_stats)


class PerformanceContext:
    """Context manager để monitor performance của operations"""
    
    def __init__(self, logger: MapUpdaterLogger, operation_name: str):
        self.logger = logger
        self.operation_name = operation_name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        self.logger.log_performance_metrics({
            "operation": self.operation_name,
            "duration": duration,
            "success": exc_type is None
        })


# Convenience functions
def create_logger(config: Dict[str, Any]) -> MapUpdaterLogger:
    """Create logger instance"""
    return MapUpdaterLogger(config)


def get_default_config() -> Dict[str, Any]:
    """Get default logging configuration"""
    return {
        "storage": {
            "logs_dir": "./logs"
        },
        "monitoring": {
            "performance_logging": True,
            "metrics_retention_days": 7
        }
    }