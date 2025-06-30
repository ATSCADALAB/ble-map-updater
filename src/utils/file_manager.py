"""
File Management Utilities

Handles:
- Safe file operations with atomic writes
- Backup and restore functionality
- Directory management
- File locking and concurrent access protection
- Cleanup operations
"""

import os
import json
import shutil
import hashlib
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List
from contextlib import contextmanager
import fcntl  # For file locking on Unix systems

class FileManager:
    """
    Secure file operations manager
    
    Features:
    - Atomic file operations
    - Backup/restore with versioning
    - File integrity verification
    - Concurrent access protection
    - Automatic cleanup
    """
    
    def __init__(self, base_dir: str, logger=None):
        self.base_dir = Path(base_dir)
        self.logger = logger
        
        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Subdirectories
        self.active_dir = self.base_dir / "active"
        self.backup_dir = self.base_dir / "backup"
        self.temp_dir = self.base_dir / "temp"
        
        # Create subdirectories
        for directory in [self.active_dir, self.backup_dir, self.temp_dir]:
            directory.mkdir(exist_ok=True)
    
    @contextmanager
    def file_lock(self, file_path: Path, mode: str = 'r'):
        """
        Context manager for file locking
        
        Usage:
            with file_manager.file_lock(path, 'w') as f:
                # file operations
        """
        
        file_handle = None
        try:
            file_handle = open(file_path, mode)
            
            # Acquire exclusive lock
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)
            
            yield file_handle
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"File lock error for {file_path}", {"error": str(e)}, e)
            raise
            
        finally:
            if file_handle:
                try:
                    # Release lock
                    fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
                    file_handle.close()
                except:
                    pass
    
    def atomic_write_json(self, data: Dict[str, Any], target_path: Path) -> bool:
        """
        Atomically write JSON data to file
        
        Process:
        1. Write to temporary file
        2. Verify data integrity
        3. Atomic move to target location
        
        Args:
            data: Data to write
            target_path: Final file location
            
        Returns:
            bool: Success status
        """
        temp_path = None
        try:
            # Create temporary file in same directory for atomic move
            temp_path = target_path.with_suffix('.tmp')
            
            # Write to temporary file
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Verify written data
            with open(temp_path, 'r', encoding='utf-8') as f:
                verification_data = json.load(f)
            
            # Simple verification - could be enhanced with deep comparison
            if len(str(verification_data)) != len(str(data)):
                raise ValueError("Data verification failed after write")
            
            # Atomic move
            temp_path.replace(target_path)
            
            if self.logger:
                self.logger.info(f"Atomic write successful", {
                    "target": str(target_path),
                    "size": target_path.stat().st_size
                })
            
            return True
            
        except Exception as e:
            # Cleanup temporary file on failure
            if temp_path.exists():
                temp_path.unlink()
            
            if self.logger:
                self.logger.error(f"Atomic write failed", {
                    "target": str(target_path),
                    "error": str(e)
                }, e)
            
            return False
    
    def create_backup(self, source_path: Path, backup_name: Optional[str] = None) -> Optional[Path]:
        """
        Create backup of file with versioning
        
        Args:
            source_path: File to backup
            backup_name: Optional custom backup name
            
        Returns:
            Path: Backup file path if successful
        """
        
        if not source_path.exists():
            if self.logger:
                self.logger.warning(f"Source file does not exist for backup: {source_path}")
            return None
        
        try:
            # Generate backup filename
            if backup_name:
                backup_filename = backup_name
            else:
                # Include timestamp and hash for uniqueness
                import time
                timestamp = int(time.time())
                file_hash = self._calculate_file_hash(source_path)[:8]
                backup_filename = f"{source_path.stem}_{timestamp}_{file_hash}{source_path.suffix}"
            
            backup_path = self.backup_dir / backup_filename
            
            # Copy file
            shutil.copy2(source_path, backup_path)
            
            # Verify backup
            if self._verify_file_integrity(source_path, backup_path):
                if self.logger:
                    self.logger.info(f"Backup created successfully", {
                        "source": str(source_path),
                        "backup": str(backup_path),
                        "size": backup_path.stat().st_size
                    })
                
                return backup_path
            else:
                if backup_path.exists():
                    backup_path.unlink()  # Remove failed backup
                raise ValueError("Backup verification failed")
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Backup creation failed", {
                    "source": str(source_path),
                    "error": str(e)
                }, e)
            
            return None
    
    def restore_from_backup(self, backup_path: Path, target_path: Path) -> bool:
        """
        Restore file from backup
        
        Args:
            backup_path: Backup file to restore from
            target_path: Target location for restored file
            
        Returns:
            bool: Success status
        """
        
        if not backup_path.exists():
            if self.logger:
                self.logger.error(f"Backup file does not exist: {backup_path}")
            return False
        
        try:
            # Create backup of current file (if exists)
            if target_path.exists():
                current_backup = self.create_backup(target_path, f"pre_restore_{target_path.name}")
                if self.logger:
                    self.logger.info(f"Created pre-restore backup: {current_backup}")
            
            # Copy backup to target
            shutil.copy2(backup_path, target_path)
            
            # Verify restoration
            if self._verify_file_integrity(backup_path, target_path):
                if self.logger:
                    self.logger.info(f"Restore successful", {
                        "backup": str(backup_path),
                        "target": str(target_path)
                    })
                return True
            else:
                raise ValueError("Restore verification failed")
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Restore failed", {
                    "backup": str(backup_path),
                    "target": str(target_path),
                    "error": str(e)
                }, e)
            
            return False
    
    def list_backups(self, file_pattern: str = "*") -> List[Dict[str, Any]]:
        """
        List available backups
        
        Args:
            file_pattern: Pattern to match backup files
            
        Returns:
            List of backup information dictionaries
        """
        
        backups = []
        
        try:
            backup_files = list(self.backup_dir.glob(file_pattern))
            
            for backup_file in sorted(backup_files, key=lambda x: x.stat().st_mtime, reverse=True):
                stat = backup_file.stat()
                
                backup_info = {
                    "name": backup_file.name,
                    "path": str(backup_file),
                    "size": stat.st_size,
                    "created": stat.st_mtime,
                    "hash": self._calculate_file_hash(backup_file)
                }
                
                backups.append(backup_info)
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to list backups", {"error": str(e)}, e)
        
        return backups
    
    def cleanup_old_backups(self, max_backups: int = 10) -> int:
        """
        Clean up old backup files
        
        Args:
            max_backups: Maximum number of backups to keep
            
        Returns:
            int: Number of files removed
        """
        
        try:
            backup_files = list(self.backup_dir.glob("*"))
            
            # Sort by modification time (newest first)
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Remove excess backups
            files_to_remove = backup_files[max_backups:]
            removed_count = 0
            
            for backup_file in files_to_remove:
                try:
                    backup_file.unlink()
                    removed_count += 1
                    
                    if self.logger:
                        self.logger.info(f"Removed old backup: {backup_file.name}")
                        
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Failed to remove backup {backup_file.name}: {e}")
            
            return removed_count
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Backup cleanup failed", {"error": str(e)}, e)
            
            return 0
    
    def cleanup_temp_files(self, max_age_hours: int = 24) -> int:
        """
        Clean up temporary files older than specified age
        
        Args:
            max_age_hours: Maximum age of temp files to keep
            
        Returns:
            int: Number of files removed
        """
        
        import time
        
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            temp_files = list(self.temp_dir.glob("*"))
            removed_count = 0
            
            for temp_file in temp_files:
                try:
                    file_age = current_time - temp_file.stat().st_mtime
                    
                    if file_age > max_age_seconds:
                        temp_file.unlink()
                        removed_count += 1
                        
                        if self.logger:
                            self.logger.info(f"Removed old temp file: {temp_file.name}")
                            
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Failed to remove temp file {temp_file.name}: {e}")
            
            return removed_count
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Temp cleanup failed", {"error": str(e)}, e)
            
            return 0
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file"""
        
        hash_sha256 = hashlib.sha256()
        
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
        except Exception:
            return "unknown"
        
        return hash_sha256.hexdigest()
    
    def _verify_file_integrity(self, file1: Path, file2: Path) -> bool:
        """Verify two files have identical content"""
        
        try:
            hash1 = self._calculate_file_hash(file1)
            hash2 = self._calculate_file_hash(file2)
            
            return hash1 == hash2 and hash1 != "unknown"
            
        except Exception:
            return False
    
    def get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage information for managed directories"""
        
        usage_info = {}
        
        try:
            for name, directory in [
                ("active", self.active_dir),
                ("backup", self.backup_dir), 
                ("temp", self.temp_dir)
            ]:
                files = list(directory.glob("*"))
                total_size = sum(f.stat().st_size for f in files if f.is_file())
                
                usage_info[name] = {
                    "directory": str(directory),
                    "file_count": len(files),
                    "total_size": total_size,
                    "total_size_mb": round(total_size / (1024 * 1024), 2)
                }
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to get disk usage", {"error": str(e)}, e)
        
        return usage_info

# Convenience functions
def create_file_manager(config: Dict[str, Any], logger=None) -> FileManager:
    """Create file manager from config"""
    
    maps_dir = config["storage"]["maps_dir"]
    return FileManager(maps_dir, logger)

# Testing function
def test_file_manager():
    """Test file manager functionality"""
    
    print("🧪 Testing File Manager")
    print("=" * 25)
    
    # Create test file manager
    test_dir = Path("./test_file_manager")
    file_manager = FileManager(str(test_dir))
    
    try:
        # Test 1: Atomic write
        print("1️⃣ Testing atomic write...")
        test_data = {"test": "data", "number": 42}
        target_path = file_manager.active_dir / "test.json"
        
        if file_manager.atomic_write_json(test_data, target_path):
            print("   ✅ Atomic write successful")
        else:
            print("   ❌ Atomic write failed")
        
        # Test 2: Backup
        print("\n2️⃣ Testing backup creation...")
        backup_path = file_manager.create_backup(target_path)
        
        if backup_path and backup_path.exists():
            print(f"   ✅ Backup created: {backup_path.name}")
        else:
            print("   ❌ Backup creation failed")
        
        # Test 3: List backups
        print("\n3️⃣ Testing backup listing...")
        backups = file_manager.list_backups()
        print(f"   📁 Found {len(backups)} backups")
        
        # Test 4: Disk usage
        print("\n4️⃣ Testing disk usage...")
        usage = file_manager.get_disk_usage()
        for dir_name, info in usage.items():
            print(f"   📊 {dir_name}: {info['file_count']} files, {info['total_size_mb']} MB")
        
        print("\n🎉 File manager tests completed!")
        
    finally:
        # Cleanup test directory
        if test_dir.exists():
            shutil.rmtree(test_dir)
            print("🧹 Test directory cleaned up")

if __name__ == "__main__":
    test_file_manager()