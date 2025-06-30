#!/usr/bin/env python3
"""
Installation Verification Script
Kiểm tra xem tất cả components đã sẵn sàng để chạy server

FEATURES:
- Comprehensive dependency checking
- Module import testing
- Configuration validation
- Directory structure verification
- Mock server test run
"""

import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any


class InstallationVerifier:
    """Verify BLE system installation"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.src_dir = self.project_root / "src"
        self.issues = []
        self.warnings = []
        
        # Add src to path
        sys.path.insert(0, str(self.src_dir))
    
    def print_header(self, title: str):
        """Print section header"""
        print(f"\n{'=' * 60}")
        print(f"🔍 {title}")
        print('=' * 60)
    
    def print_success(self, message: str):
        """Print success message"""
        print(f"✅ {message}")
    
    def print_warning(self, message: str):
        """Print warning message"""
        print(f"⚠️  {message}")
        self.warnings.append(message)
    
    def print_error(self, message: str):
        """Print error message"""
        print(f"❌ {message}")
        self.issues.append(message)
    
    def check_python_version(self):
        """Check Python version"""
        self.print_header("Python Version Check")
        
        version = sys.version_info
        print(f"Python version: {version.major}.{version.minor}.{version.micro}")
        
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            self.print_error("Python 3.8+ required")
        else:
            self.print_success("Python version is compatible")
    
    def check_dependencies(self):
        """Check required dependencies"""
        self.print_header("Dependency Check")
        
        dependencies = [
            ('bleak', 'BLE communication library'),
            ('cryptography', 'Security and encryption'),
            ('jsonschema', 'JSON validation'),
        ]
        
        optional_dependencies = [
            ('pytest', 'Testing framework'),
            ('psutil', 'System monitoring'),
        ]
        
        # Check required dependencies
        for dep_name, description in dependencies:
            try:
                __import__(dep_name)
                self.print_success(f"{dep_name} - {description}")
            except ImportError:
                self.print_error(f"{dep_name} - {description} (REQUIRED)")
        
        # Check optional dependencies
        for dep_name, description in optional_dependencies:
            try:
                __import__(dep_name)
                self.print_success(f"{dep_name} - {description} (optional)")
            except ImportError:
                self.print_warning(f"{dep_name} - {description} (optional)")
    
    def check_project_structure(self):
        """Check project directory structure"""
        self.print_header("Project Structure Check")
        
        required_dirs = [
            "src",
            "src/ble",
            "src/protocol", 
            "src/utils",
            "src/tests"
        ]
        
        required_files = [
            "run_ble_system.py",
            "src/ble/server.py",
            "src/ble/protocol.py",
            "src/protocol/map_transfer.py",
            "src/protocol/authentication.py",
            "src/utils/logger.py",
            "src/tests/test_ble_integration.py"
        ]
        
        # Check directories
        for dir_path in required_dirs:
            full_path = self.project_root / dir_path
            if full_path.exists():
                self.print_success(f"Directory: {dir_path}")
            else:
                self.print_error(f"Missing directory: {dir_path}")
        
        # Check files
        for file_path in required_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                self.print_success(f"File: {file_path}")
            else:
                self.print_error(f"Missing file: {file_path}")
        
        # Check __init__.py files
        init_files = [
            "src/__init__.py",
            "src/ble/__init__.py", 
            "src/protocol/__init__.py",
            "src/utils/__init__.py",
            "src/tests/__init__.py"
        ]
        
        for init_file in init_files:
            full_path = self.project_root / init_file
            if not full_path.exists():
                self.print_warning(f"Missing __init__.py: {init_file}")
                # Create it
                full_path.touch()
                self.print_success(f"Created __init__.py: {init_file}")
    
    def check_module_imports(self):
        """Check if all modules can be imported"""
        self.print_header("Module Import Check")
        
        modules_to_test = [
            ('ble.server', 'BLE Server module'),
            ('ble.protocol', 'BLE Protocol definitions'),
            ('protocol.map_transfer', 'Map Transfer Manager'),
            ('protocol.authentication', 'Authentication Manager'),
            ('utils.logger', 'Logging system'),
            ('tests.test_ble_integration', 'Integration tests')
        ]
        
        for module_name, description in modules_to_test:
            try:
                __import__(module_name)
                self.print_success(f"{module_name} - {description}")
            except ImportError as e:
                self.print_error(f"{module_name} - Import failed: {e}")
            except Exception as e:
                self.print_warning(f"{module_name} - Import warning: {e}")
    
    def check_configuration(self):
        """Check configuration file"""
        self.print_header("Configuration Check")
        
        config_path = self.project_root / "config.json"
        
        if not config_path.exists():
            self.print_warning("config.json not found - will create default")
            try:
                # Try to create default config
                from run_ble_system import create_default_config
                create_default_config(config_path)
                self.print_success("Default config.json created")
            except Exception as e:
                self.print_error(f"Failed to create config: {e}")
                return
        
        # Validate config
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            required_sections = ["system", "ble", "storage"]
            for section in required_sections:
                if section in config:
                    self.print_success(f"Config section: {section}")
                else:
                    self.print_error(f"Missing config section: {section}")
            
            # Check specific required fields
            if "device_id" in config.get("system", {}):
                self.print_success("Config: system.device_id")
            else:
                self.print_error("Config: missing system.device_id")
            
            if "service_uuid" in config.get("ble", {}):
                self.print_success("Config: ble.service_uuid")
            else:
                self.print_error("Config: missing ble.service_uuid")
        
        except json.JSONDecodeError as e:
            self.print_error(f"Invalid JSON in config.json: {e}")
        except Exception as e:
            self.print_error(f"Config validation error: {e}")
    
    def check_directory_structure(self):
        """Check and create required directories"""
        self.print_header("Directory Structure Check")
        
        # Read config to get directory paths
        config_path = self.project_root / "config.json"
        
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                
                storage_config = config.get("storage", {})
                
                dirs_to_check = [
                    storage_config.get("maps_dir", "./maps"),
                    Path(storage_config.get("active_map", "./maps/active/current_map.json")).parent,
                    Path(storage_config.get("backup_map", "./maps/backup/backup_map.json")).parent,
                    storage_config.get("temp_dir", "./maps/temp"),
                    storage_config.get("logs_dir", "./logs")
                ]
                
                for dir_path in dirs_to_check:
                    full_path = Path(dir_path)
                    if full_path.exists():
                        self.print_success(f"Directory exists: {dir_path}")
                    else:
                        full_path.mkdir(parents=True, exist_ok=True)
                        self.print_success(f"Created directory: {dir_path}")
            
            except Exception as e:
                self.print_warning(f"Directory check failed: {e}")
        else:
            self.print_warning("No config.json found - skipping directory check")
    
    def test_server_initialization(self):
        """Test server can be initialized"""
        self.print_header("Server Initialization Test")
        
        try:
            from ble.server import SimpleBLEServer
            
            # Test server initialization
            server = SimpleBLEServer("config.json")
            self.print_success("Server initialization successful")
            
            # Test configuration loading
            if hasattr(server, 'config') and server.config:
                self.print_success("Server configuration loaded")
            else:
                self.print_warning("Server configuration issue")
            
            # Test component initialization
            if hasattr(server, 'auth_manager') and server.auth_manager:
                self.print_success("Authentication manager initialized")
            else:
                self.print_warning("Authentication manager issue")
            
            if hasattr(server, 'map_transfer') and server.map_transfer:
                self.print_success("Map transfer manager initialized")
            else:
                self.print_warning("Map transfer manager issue")
        
        except Exception as e:
            self.print_error(f"Server initialization failed: {e}")
    
    def run_quick_test(self):
        """Run a quick integration test"""
        self.print_header("Quick Integration Test")
        
        try:
            # Try to run a basic test
            from tests.test_ble_integration import BLEIntegrationTestSuite
            import unittest
            
            # Run just one basic test
            suite = unittest.TestSuite()
            suite.addTest(BLEIntegrationTestSuite('test_01_map_transfer_manager_basic'))
            
            runner = unittest.TextTestRunner(verbosity=0, stream=open('/dev/null', 'w'))
            result = runner.run(suite)
            
            if result.wasSuccessful():
                self.print_success("Basic integration test passed")
            else:
                self.print_warning("Basic integration test had issues")
        
        except Exception as e:
            self.print_warning(f"Integration test failed: {e}")
    
    def generate_summary(self):
        """Generate verification summary"""
        self.print_header("Verification Summary")
        
        print(f"📊 Issues found: {len(self.issues)}")
        print(f"⚠️  Warnings: {len(self.warnings)}")
        
        if self.issues:
            print("\n🚨 Critical Issues (Must Fix):")
            for issue in self.issues:
                print(f"   • {issue}")
        
        if self.warnings:
            print("\n⚠️  Warnings (Recommended to Fix):")
            for warning in self.warnings:
                print(f"   • {warning}")
        
        print("\n" + "=" * 60)
        
        if not self.issues:
            print("🎉 SYSTEM READY TO RUN!")
            print("\n📋 Next steps:")
            print("   1. Activate virtual environment: source venv/bin/activate")
            print("   2. Start server: python run_ble_system.py server")
            print("   3. Or run demo: python run_ble_system.py demo")
            print("   4. Check status: python run_ble_system.py status")
            return True
        else:
            print("🚨 SYSTEM NOT READY - Fix critical issues above")
            print("\n🔧 Quick fixes:")
            print("   • Install missing dependencies: pip install bleak cryptography jsonschema")
            print("   • Create missing files using the artifacts provided")
            print("   • Run setup script: ./quick_setup.sh")
            return False
    
    def run_full_verification(self):
        """Run complete verification"""
        print("🔍 BLE Map Transfer System - Installation Verification")
        print("=" * 60)
        print("Checking if system is ready to run...")
        
        # Run all checks
        self.check_python_version()
        self.check_dependencies()
        self.check_project_structure()
        self.check_configuration()
        self.check_directory_structure()
        self.check_module_imports()
        self.test_server_initialization()
        self.run_quick_test()
        
        # Generate summary
        return self.generate_summary()


def main():
    """Main entry point"""
    
    verifier = InstallationVerifier()
    
    try:
        success = verifier.run_full_verification()
        return 0 if success else 1
    
    except KeyboardInterrupt:
        print("\n🛑 Verification interrupted")
        return 1
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())