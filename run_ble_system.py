#!/usr/bin/env python3
"""
BLE System Runner - Complete Management Script
Script quản lý toàn bộ BLE map transfer system

USAGE:
    python run_ble_system.py server          # Chạy BLE server (Pi side)
    python run_ble_system.py client <file>   # Chạy BLE client để send map
    python run_ble_system.py test            # Chạy integration tests
    python run_ble_system.py demo            # Chạy demo với mock data
    python run_ble_system.py --create-config # Tạo config file mặc định

FEATURES:
- Automatic dependency checking
- Configuration validation
- Progress monitoring
- Error handling và logging
- Development utilities
"""

import sys
import os
import argparse
import asyncio
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def check_dependencies():
    """Check required dependencies"""
    
    print("🔍 Checking dependencies...")
    
    missing_deps = []
    
    try:
        import bleak
        print("  ✅ bleak - BLE communication")
    except ImportError:
        missing_deps.append("bleak")
        print("  ❌ bleak - BLE communication")
    
    try:
        import cryptography
        print("  ✅ cryptography - Security functions")
    except ImportError:
        missing_deps.append("cryptography")
        print("  ❌ cryptography - Security functions")
    
    try:
        import jsonschema
        print("  ✅ jsonschema - JSON validation")
    except ImportError:
        missing_deps.append("jsonschema")
        print("  ❌ jsonschema - JSON validation")
    
    if missing_deps:
        print(f"\n❌ Missing dependencies: {', '.join(missing_deps)}")
        print("Install with: pip install " + " ".join(missing_deps))
        return False
    
    print("✅ All dependencies available")
    return True

def validate_config(config_path: Path) -> bool:
    """Validate configuration file"""
    
    print(f"🔧 Validating config: {config_path}")
    
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        print("Create one with: python run_ble_system.py --create-config")
        return False
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Check required sections
        required_sections = ["system", "ble", "storage"]
        for section in required_sections:
            if section not in config:
                print(f"❌ Missing config section: {section}")
                return False
        
        # Check required fields
        if "device_id" not in config["system"]:
            print("❌ Missing system.device_id")
            return False
        
        if "service_uuid" not in config["ble"]:
            print("❌ Missing ble.service_uuid")
            return False
        
        print("✅ Configuration valid")
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in config: {e}")
        return False
    except Exception as e:
        print(f"❌ Config validation error: {e}")
        return False

def create_default_config(config_path: Path):
    """Create default configuration file"""
    
    print(f"📝 Creating default config: {config_path}")
    
    default_config = {
        "system": {
            "device_id": "CYCLE_SENTINEL_PI_001",
            "version": "1.0.0",
            "description": "BLE Map Transfer Server for Cycle Sentinel"
        },
        "ble": {
            "service_uuid": "12345678-1234-1234-1234-123456789abc",
            "characteristics": {
                "auth": "12345678-1234-1234-1234-123456789abd",
                "map_data": "12345678-1234-1234-1234-123456789abe",
                "status": "12345678-1234-1234-1234-123456789abf"
            },
            "chunk_size": 128,
            "max_transfer_size": 5242880,
            "max_chunks_per_second": 10,
            "retry_attempts": 3,
            "retry_delay": 1.0,
            "compression_enabled": True,
            "compression_threshold": 1048576
        },
        "security": {
            "auth_timeout": 60,
            "max_auth_attempts": 3,
            "min_map_version": 1,
            "required_signature": False,
            "signature_algorithm": "ECDSA_P256",
            "hash_algorithm": "SHA256"
        },
        "storage": {
            "maps_dir": "./maps",
            "active_map": "./maps/active/current_map.json",
            "backup_map": "./maps/backup/backup_map.json",
            "temp_dir": "./maps/temp",
            "logs_dir": "./logs",
            "max_backups": 10
        },
        "transfer": {
            "session_timeout": 600,
            "max_concurrent_transfers": 1,
            "progress_report_interval": 5,
            "resume_support": True
        },
        "monitoring": {
            "health_check_interval": 30,
            "performance_logging": True,
            "metrics_retention_days": 7
        }
    }
    
    # Create directories
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write config
    with open(config_path, 'w') as f:
        json.dump(default_config, f, indent=2)
    
    print("✅ Default configuration created")

async def run_server(config_path: Path, verbose: bool = False):
    """Run BLE server"""
    
    print("🚀 Starting BLE Map Server (Pi Side)")
    print("=" * 50)
    
    try:
        # Import here to avoid import errors if modules not available
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        
        from ble.server import BLEMapServer
        
        # Progress callback
        def progress_callback(chunks_received, total_chunks, progress, metrics):
            if chunks_received % 50 == 0 or chunks_received == total_chunks:
                print(f"📊 Transfer: {chunks_received:,}/{total_chunks:,} chunks ({progress:.1f}%) - "
                      f"Rate: {metrics.get('transfer_rate_bps', 0):.0f} bps")
        
        # Create server
        server = BLEMapServer(str(config_path))
        server.set_progress_callback(progress_callback)
        
        print(f"🔥 BLE Map Server started successfully!")
        print(f"📡 Device ID: {server.config['system']['device_id']}")
        print(f"📱 Service UUID: {server.config['ble']['service_uuid']}")
        print("🔒 Waiting for enforcement device connections...")
        print("Press Ctrl+C to stop")
        
        # Start server
        await server.start_server()
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed: pip install -r requirements.txt")
        return False
    except Exception as e:
        print(f"❌ Server failed: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False

async def run_client(config_path: Path, map_file: Path, device_address: Optional[str] = None, verbose: bool = False):
    """Run BLE client to send map"""
    
    print("📤 Starting BLE Map Client")
    print("=" * 40)
    
    try:
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        
        from ble.client import BLEMapClient
        
        # Create client
        client = BLEMapClient(str(config_path))
        
        print(f"📄 Map file: {map_file}")
        
        # Send map
        result = await client.send_map_file(str(map_file), device_address)
        
        if result:
            print("✅ Map sent successfully!")
        else:
            print("❌ Failed to send map")
        
        return result
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Client failed: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False

async def run_tests(config_path: Path, test_name: Optional[str] = None, quick: bool = False, verbose: bool = False):
    """Run integration tests"""
    
    print("🧪 Running BLE Integration Tests")
    print("=" * 40)
    
    try:
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        
        from tests.test_ble_integration import BLEIntegrationTestSuite
        
        # Run tests
        import unittest
        
        if test_name:
            # Run specific test
            suite = unittest.TestSuite()
            test_case = BLEIntegrationTestSuite(test_name)
            suite.addTest(test_case)
        else:
            # Run all tests
            suite = unittest.TestLoader().loadTestsFromTestCase(BLEIntegrationTestSuite)
        
        runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
        result = runner.run(suite)
        
        if result.wasSuccessful():
            print("✅ All tests passed!")
            return True
        else:
            print("❌ Some tests failed!")
            return False
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Tests failed: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False

async def run_demo(config_path: Path, verbose: bool = False):
    """Run demo scenario"""
    
    print("🎭 Running BLE System Demo")
    print("=" * 30)
    
    try:
        # Create demo directory
        demo_dir = Path("./demo")
        demo_dir.mkdir(exist_ok=True)
        
        # Create demo map file
        demo_map = {
            "metadata": {
                "version": int(time.time()),
                "created": time.time(),
                "description": "Demo speed zones",
                "schema_version": "1.0"
            },
            "zones": [
                {
                    "id": "demo_zone_001",
                    "type": "speed_limit",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[106.6297, 10.8231], [106.6298, 10.8232], [106.6299, 10.8231], [106.6297, 10.8231]]]
                    },
                    "properties": {
                        "speed_limit": 30,
                        "zone_type": "school_zone"
                    }
                }
            ]
        }
        
        demo_map_file = demo_dir / "demo_map.json"
        with open(demo_map_file, 'w') as f:
            json.dump(demo_map, f, indent=2)
        
        print(f"📄 Demo map created: {demo_map_file}")
        print(f"📊 Map size: {demo_map_file.stat().st_size} bytes")
        
        # Demo completed
        print("🎉 Demo setup completed!")
        print(f"📁 Demo files saved in: {demo_dir}")
        
        return True
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False

def show_status(config_path: Path):
    """Show system status"""
    
    print("📊 BLE System Status")
    print("=" * 30)
    
    # Check config
    config_valid = validate_config(config_path)
    print(f"Configuration: {'✅ Valid' if config_valid else '❌ Invalid'}")
    
    # Check dependencies
    deps_ok = check_dependencies()
    print(f"Dependencies: {'✅ OK' if deps_ok else '❌ Missing'}")
    
    # Check directories
    if config_valid:
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            storage_config = config["storage"]
            
            maps_dir = Path(storage_config["maps_dir"])
            logs_dir = Path(storage_config["logs_dir"])
            
            print(f"Maps directory: {'✅ Exists' if maps_dir.exists() else '❌ Missing'}")
            print(f"Logs directory: {'✅ Exists' if logs_dir.exists() else '❌ Missing'}")
            
            # Active map
            active_map = Path(storage_config["active_map"])
            if active_map.exists():
                size = active_map.stat().st_size
                print(f"Active map: ✅ {size:,} bytes")
            else:
                print("Active map: ❌ No active map")
                
        except Exception as e:
            print(f"Storage check failed: {e}")
    
    print()
    if config_valid and deps_ok:
        print("🟢 System ready")
    else:
        print("🔴 System not ready - fix issues above")

def main():
    """Main entry point"""
    
    parser = argparse.ArgumentParser(
        description="BLE Map Transfer System Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s server                           # Start BLE server (Pi side)
  %(prog)s client map.json                  # Send map to any device
  %(prog)s client map.json --device AA:BB  # Send to specific device
  %(prog)s test                            # Run integration tests
  %(prog)s test --quick                    # Quick test run
  %(prog)s demo                            # Run demo scenario
  %(prog)s status                          # Show system status
  %(prog)s --create-config                 # Create default config
        """
    )
    
    parser.add_argument("command", nargs="?", choices=["server", "client", "test", "demo", "status"],
                       help="Command to run")
    parser.add_argument("file", nargs="?", help="Map file to send (for client command)")
    parser.add_argument("--config", "-c", default="config.json", help="Config file path")
    parser.add_argument("--device", "-d", help="Target device address (for client)")
    parser.add_argument("--test", "-t", help="Specific test to run")
    parser.add_argument("--quick", "-q", action="store_true", help="Quick test mode")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--create-config", action="store_true", help="Create default config file")
    
    args = parser.parse_args()
    
    # Handle config creation
    if args.create_config:
        create_default_config(Path(args.config))
        return 0
    
    # Check if command provided
    if not args.command:
        parser.print_help()
        return 1
    
    config_path = Path(args.config)
    
    # Pre-flight checks
    if args.command != "status":
        if not validate_config(config_path):
            return 1
        
        if not check_dependencies():
            return 1
    
    try:
        # Run command
        if args.command == "server":
            asyncio.run(run_server(config_path, args.verbose))
            
        elif args.command == "client":
            if not args.file:
                print("❌ Map file required for client command")
                return 1
            
            map_file = Path(args.file)
            if not map_file.exists():
                print(f"❌ Map file not found: {map_file}")
                return 1
            
            result = asyncio.run(run_client(config_path, map_file, args.device, args.verbose))
            return 0 if result else 1
            
        elif args.command == "test":
            result = asyncio.run(run_tests(config_path, args.test, args.quick, args.verbose))
            return 0 if result else 1
            
        elif args.command == "demo":
            result = asyncio.run(run_demo(config_path, args.verbose))
            return 0 if result else 1
            
        elif args.command == "status":
            show_status(config_path)
            
        return 0
        
    except KeyboardInterrupt:
        print("\n🛑 Operation interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())