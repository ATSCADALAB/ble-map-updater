#!/usr/bin/env python3
"""
BLE System Runner - Complete Management Script
Script quản lý toàn bộ BLE map transfer system

USAGE:
    python run_ble_system.py server          # Chạy BLE server (Pi side)
    python run_ble_system.py client <file>   # Chạy BLE client để send map
    python run_ble_system.py test            # Chạy integration tests
    python run_ble_system.py demo            # Chạy demo với mock data

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
        return False
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Check required sections
        required_sections = ["system", "ble", "storage", "security", "transfer"]
        for section in required_sections:
            if section not in config:
                print(f"❌ Missing config section: {section}")
                return False
        
        # Check BLE config
        ble_config = config["ble"]
        required_ble_fields = ["service_uuid", "characteristics", "chunk_size", "max_transfer_size"]
        for field in required_ble_fields:
            if field not in ble_config:
                print(f"❌ Missing BLE config field: {field}")
                return False
        
        # Validate file size limits
        max_size = ble_config["max_transfer_size"]
        if max_size > 10 * 1024 * 1024:  # 10MB
            print(f"⚠️ Warning: Large max transfer size: {max_size:,} bytes")
        
        print("✅ Configuration valid")
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in config: {e}")
        return False
    except Exception as e:
        print(f"❌ Config validation failed: {e}")
        return False

def create_default_config(config_path: Path):
    """Create default configuration file"""
    
    print(f"📝 Creating default config: {config_path}")
    
    default_config = {
        "system": {
            "device_id": "CYCLE_SENTINEL_001",
            "version": "1.0.0",
            "debug_mode": True
        },
        "ble": {
            "service_uuid": "12345678-1234-1234-1234-123456789abc",
            "characteristics": {
                "auth": "12345678-1234-1234-1234-123456789abd",
                "map_data": "12345678-1234-1234-1234-123456789abe",
                "status": "12345678-1234-1234-1234-123456789abf"
            },
            "connection_timeout": 60,
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
            "required_signature": True,
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
        from ble.server import BLEMapServer, run_ble_server
        
        # Progress callback
        def progress_callback(chunks_received, total_chunks, progress, metrics):
            if chunks_received % 50 == 0 or chunks_received == total_chunks:
                print(f"📊 Transfer: {chunks_received:,}/{total_chunks:,} chunks ({progress:.1f}%) - "
                      f"Rate: {metrics.transfer_rate_bps:.0f} bps")
        
        print(f"🔧 Using config: {config_path}")
        print(f"📡 Server will advertise and wait for connections...")
        print(f"🔒 Authentication required for all transfers")
        print(f"📱 Use enforcement device client to connect")
        print()
        print("Press Ctrl+C to stop server")
        print("-" * 50)
        
        await run_ble_server(str(config_path), progress_callback)
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed")
    except Exception as e:
        print(f"❌ Server error: {e}")
        if verbose:
            import traceback
            traceback.print_exc()

async def run_client(map_file_path: Path, config_path: Path, device_address: Optional[str] = None, verbose: bool = False):
    """Run BLE client to send map"""
    
    print("🚀 Starting BLE Map Client (Enforcement Device)")
    print("=" * 50)
    
    if not map_file_path.exists():
        print(f"❌ Map file not found: {map_file_path}")
        return False
    
    file_size = map_file_path.stat().st_size
    print(f"📁 Map file: {map_file_path}")
    print(f"📏 File size: {file_size:,} bytes ({file_size/1024/1024:.1f} MB)")
    
    if device_address:
        print(f"🎯 Target device: {device_address}")
    
    try:
        from ble.client import BLEMapClient, send_map_to_device
        
        # Progress callback
        def progress_callback(chunks_sent, total_chunks, progress):
            if chunks_sent % 100 == 0 or chunks_sent == total_chunks:
                print(f"📤 Sending: {chunks_sent:,}/{total_chunks:,} chunks ({progress:.1f}%)")
        
        print(f"🔧 Using config: {config_path}")
        print("🔍 Scanning for compatible devices...")
        print("-" * 50)
        
        success = await send_map_to_device(
            map_file_path,
            device_address,
            str(config_path)
        )
        
        if success:
            print("✅ Map sent successfully!")
            return True
        else:
            print("❌ Failed to send map")
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed")
        return False
    except Exception as e:
        print(f"❌ Client error: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False

def run_tests(quick: bool = False, verbose: bool = False):
    """Run integration tests"""
    
    print("🧪 Running BLE Integration Tests")
    print("=" * 40)
    
    try:
        from tests.test_ble_integration import run_integration_tests
        
        if quick:
            print("⚡ Quick test mode - skipping slow tests")
        
        return run_integration_tests()
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure test modules are available")
        return 1
    except Exception as e:
        print(f"❌ Test error: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return 1

def create_demo_map(output_path: Path, size_category: str = "medium") -> Path:
    """Create demo map file for testing"""
    
    print(f"📝 Creating demo map file ({size_category})...")
    
    base_map = {
        "metadata": {
            "version": int(time.time()),
            "created": int(time.time()),
            "description": f"Demo map file ({size_category} size)",
            "schema_version": "1.0",
            "created_by": "BLE System Demo"
        },
        "zones": []
    }
    
    if size_category == "small":
        # ~1KB
        num_zones = 5
    elif size_category == "medium":
        # ~100KB  
        num_zones = 500
    elif size_category == "large":
        # ~2MB
        num_zones = 2000
    else:
        num_zones = 100
    
    # Generate zones
    for i in range(num_zones):
        zone = {
            "id": f"demo_zone_{i}",
            "type": "speed_limit",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[i*0.001, i*0.001], [i*0.001+0.0005, i*0.001], 
                               [i*0.001+0.0005, i*0.001+0.0005], [i*0.001, i*0.001+0.0005], [i*0.001, i*0.001]]]
            },
            "properties": {
                "speed_limit": 15 + (i % 30),
                "zone_type": f"demo_type_{i % 5}",
                "description": f"Demo zone {i} with example properties and metadata",
                "tags": [f"demo", f"zone_{i}", f"type_{i % 3}"],
                "created": int(time.time()) - (i * 60)  # Stagger creation times
            }
        }
        base_map["zones"].append(zone)
    
    # Create output directory
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write map file
    with open(output_path, 'w') as f:
        json.dump(base_map, f, indent=2)
    
    file_size = output_path.stat().st_size
    print(f"   Created: {output_path}")
    print(f"   Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
    print(f"   Zones: {num_zones:,}")
    
    return output_path

async def run_demo(config_path: Path, verbose: bool = False):
    """Run complete demo scenario"""
    from pathlib import Path
    print("🎬 Running BLE System Demo")
    print("=" * 40)
    
    # Create demo directory
    demo_dir = Path("demo_output")
    demo_dir.mkdir(exist_ok=True)
    
    # Create demo map
    demo_map_path = create_demo_map(demo_dir / "demo_map.json", "medium")
    
    print("\n📋 Demo Scenario:")
    print("1. Create mock BLE environment") 
    print("2. Initialize server components")
    print("3. Simulate client connection")
    print("4. Transfer demo map file")
    print("5. Validate results")
    
    try:
        # Import test modules for mock environment
        from tests.test_ble_integration import BLEIntegrationTestSuite
        
        print("\n🔧 Setting up mock environment...")
        
        # Create test instance
        test_suite = BLEIntegrationTestSuite()
        test_suite.setUpClass()
        
        print("✅ Mock environment ready")
        
        # Run chunked transfer simulation
        print("\n📤 Simulating map transfer...")
        
        test_suite.setUp()
        test_suite.test_02_chunked_transfer_simulation()
        
        print("✅ Transfer simulation completed")
        
        # Run compression test
        print("\n🗜️ Testing compression...")
        
        test_suite.test_03_compression_testing()
        
        print("✅ Compression test completed")
        
        # Performance test
        print("\n📊 Performance benchmarking...")
        
        test_suite.test_06_performance_benchmarking()
        
        print("✅ Performance test completed")
        
        # Cleanup
        test_suite.tearDownClass()
        
        print("\n🎉 Demo completed successfully!")
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
        """
    )
    
    parser.add_argument("command", choices=["server", "client", "test", "demo", "status"],
                       help="Command to run")
    parser.add_argument("file", nargs="?", help="Map file to send (for client)")
    parser.add_argument("--config", default="config.json", help="Config file path")
    parser.add_argument("--device", help="Target device address (for client)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--quick", action="store_true", help="Quick mode (for tests)")
    parser.add_argument("--create-config", action="store_true", help="Create default config")
    
    args = parser.parse_args()
    
    # Setup
    config_path = Path(args.config)
    
    print("🚀 BLE Map Transfer System")
    print(f"⚙️ Config: {config_path}")
    print()
    
    # Create config if requested
    if args.create_config:
        create_default_config(config_path)
        return 0
    
    # Create default config if missing
    if not config_path.exists() and args.command != "status":
        print("📝 Config file not found, creating default...")
        create_default_config(config_path)
    
    # Check dependencies (except for status)
    if args.command != "status":
        if not check_dependencies():
            return 1
    
    # Validate config (except for status and demo)
    if args.command not in ["status", "demo"]:
        if not validate_config(config_path):
            return 1
    
    # Run command
    try:
        if args.command == "server":
            asyncio.run(run_server(config_path, args.verbose))
            return 0
            
        elif args.command == "client":
            if not args.file:
                print("❌ Map file required for client mode")
                print("Usage: python run_ble_system.py client <map_file>")
                return 1
            
            map_file_path = Path(args.file)
            success = asyncio.run(run_client(map_file_path, config_path, args.device, args.verbose))
            return 0 if success else 1
            
        elif args.command == "test":
            return run_tests(args.quick, args.verbose)
            
        elif args.command == "demo":
            success = asyncio.run(run_demo(config_path, args.verbose))
            return 0 if success else 1
            
        elif args.command == "status":
            show_status(config_path)
            return 0
            
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Command failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())