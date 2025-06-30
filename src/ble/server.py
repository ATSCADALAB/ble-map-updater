#!/usr/bin/env python3
"""
Simplified BLE Server for Map Transfer
Simplified version để test server functionality

BASIC FEATURES:
- BLE advertising và connection handling
- Simple authentication
- Basic file transfer
- Progress monitoring
"""

import asyncio
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable

# Try to import BLE libraries
try:
    from bleak import BleakServer, BleakCharacteristic
    from bleak.server.characteristic import BleakServerCharacteristic
    BLE_AVAILABLE = True
except ImportError:
    print("⚠️ BLE libraries not available - running in mock mode")
    BLE_AVAILABLE = False
    
    # Mock classes for development
    class BleakServer:
        def __init__(self, *args, **kwargs):
            pass
        async def start(self):
            pass
        async def stop(self):
            pass
        @property
        def is_serving(self):
            return True
    
    class BleakCharacteristic:
        def __init__(self, *args, **kwargs):
            pass
    
    class BleakServerCharacteristic:
        def __init__(self, *args, **kwargs):
            pass

# Import local modules with fallbacks
try:
    from utils.logger import MapUpdaterLogger
except ImportError:
    # Fallback logger
    class MapUpdaterLogger:
        def __init__(self, config):
            self.system_logger = logging.getLogger("system")
            self.transfer_logger = logging.getLogger("transfer")
            self.security_logger = logging.getLogger("security")

try:
    from protocol.authentication import AuthenticationManager
except ImportError:
    # Fallback auth manager
    class AuthenticationManager:
        def __init__(self, device_id, logger):
            self.device_id = device_id
            self.logger = logger
        
        def generate_challenge(self, client_id):
            return {
                "status": "challenge_generated",
                "challenge": "demo_challenge_123",
                "server_id": self.device_id,
                "timestamp": time.time()
            }
        
        def verify_challenge_response(self, client_id, response):
            return {
                "status": "authenticated",
                "session_id": f"session_{int(time.time())}",
                "server_info": {"device_id": self.device_id}
            }
        
        def is_authenticated(self, client_id):
            return True

try:
    from protocol.map_transfer import MapTransferManager
except ImportError:
    # Fallback transfer manager
    class MapTransferManager:
        def __init__(self, config, logger):
            self.config = config
            self.logger = logger
            self.progress_callback = None
        
        def set_progress_callback(self, callback):
            self.progress_callback = callback
        
        def start_transfer(self, metadata):
            return {
                "status": "ready",
                "session_id": f"transfer_{int(time.time())}",
                "chunk_size": 128,
                "total_chunks": 100
            }
        
        def receive_chunk(self, chunk_data):
            return {"status": "received", "progress": 50.0}
        
        def complete_transfer(self):
            return {"status": "completed"}


class SimpleBLEServer:
    """
    Simplified BLE Server implementation
    Focuses on getting basic server running for testing
    """
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize simplified BLE server"""
        
        # Load configuration
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # Initialize basic components
        try:
            self.logger = MapUpdaterLogger(self.config)
        except:
            # Fallback to basic logging
            logging.basicConfig(level=logging.INFO)
            self.logger = type('MockLogger', (), {
                'system_logger': logging.getLogger("system"),
                'transfer_logger': logging.getLogger("transfer"),
                'security_logger': logging.getLogger("security")
            })()
        
        # Initialize managers
        self.auth_manager = AuthenticationManager(
            self.config["system"]["device_id"],
            self.logger
        )
        
        self.map_transfer = MapTransferManager(self.config, self.logger)
        
        # BLE server setup
        self.server: Optional[BleakServer] = None
        self.is_running = False
        self.connected_client = None
        
        # Progress tracking
        self.progress_callback: Optional[Callable] = None
        
        print(f"🔷 SimpleBLEServer initialized")
        print(f"   Device ID: {self.config['system']['device_id']}")
        print(f"   BLE Available: {BLE_AVAILABLE}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            else:
                print(f"⚠️ Config file not found: {self.config_path}")
        except Exception as e:
            print(f"⚠️ Failed to load config: {e}")
        
        # Return default config
        return {
            "system": {
                "device_id": "CYCLE_SENTINEL_DEMO",
                "version": "1.0.0-demo"
            },
            "ble": {
                "service_uuid": "12345678-1234-1234-1234-123456789abc",
                "characteristics": {
                    "auth": "12345678-1234-1234-1234-123456789abd",
                    "map_data": "12345678-1234-1234-1234-123456789abe",
                    "status": "12345678-1234-1234-1234-123456789abf"
                },
                "chunk_size": 128
            },
            "storage": {
                "maps_dir": "./maps",
                "logs_dir": "./logs"
            },
            "security": {
                "auth_timeout": 60
            }
        }
    
    def set_progress_callback(self, callback: Callable):
        """Set progress callback function"""
        self.progress_callback = callback
        if self.map_transfer:
            self.map_transfer.set_progress_callback(callback)
    
    async def start_server(self):
        """Start BLE server"""
        
        print("🚀 Starting BLE Map Server...")
        
        if not BLE_AVAILABLE:
            print("🔄 Running in MOCK mode (BLE not available)")
            await self._run_mock_server()
            return
        
        try:
            await self._start_real_server()
        except Exception as e:
            print(f"❌ Failed to start real BLE server: {e}")
            print("🔄 Falling back to MOCK mode...")
            await self._run_mock_server()
    
    async def _start_real_server(self):
        """Start real BLE server with bleak"""
        
        # Create BLE characteristics
        auth_char = BleakCharacteristic(
            self.config["ble"]["characteristics"]["auth"],
            ["write", "notify"],
            None,
            self._handle_auth_write
        )
        
        map_data_char = BleakCharacteristic(
            self.config["ble"]["characteristics"]["map_data"],
            ["write", "notify"],
            None,
            self._handle_map_data_write
        )
        
        status_char = BleakCharacteristic(
            self.config["ble"]["characteristics"]["status"],
            ["read", "notify"],
            None,
            self._handle_status_read
        )
        
        # Create and start server
        self.server = BleakServer([auth_char, map_data_char, status_char])
        
        await self.server.start()
        self.is_running = True
        
        print("✅ BLE Server started successfully!")
        print(f"📡 Service UUID: {self.config['ble']['service_uuid']}")
        print("🔒 Waiting for client connections...")
        
        # Keep server running
        try:
            while self.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Shutting down server...")
        finally:
            await self.stop_server()
    
    async def _run_mock_server(self):
        """Run mock server for testing without BLE hardware"""
        
        self.is_running = True
        
        print("✅ Mock BLE Server started!")
        print(f"📡 Service UUID: {self.config['ble']['service_uuid']}")
        print("🔄 Simulating BLE operations...")
        print("Press Ctrl+C to stop")
        
        # Simulate some activity
        try:
            await self._simulate_client_interaction()
        except KeyboardInterrupt:
            print("\n🛑 Shutting down mock server...")
        finally:
            self.is_running = False
    
    async def _simulate_client_interaction(self):
        """Simulate client interaction for demo purposes"""
        
        await asyncio.sleep(2)
        print("\n🔔 Simulating client connection...")
        
        # Simulate authentication
        print("🔐 Simulating authentication...")
        await asyncio.sleep(1)
        
        auth_result = self.auth_manager.generate_challenge("mock_client")
        print(f"   Challenge generated: {auth_result['status']}")
        
        await asyncio.sleep(1)
        verify_result = self.auth_manager.verify_challenge_response("mock_client", {
            "challenge": "demo_challenge_123",
            "signature": "demo_signature"
        })
        print(f"   Authentication: {verify_result['status']}")
        
        # Simulate file transfer
        print("\n📤 Simulating map transfer...")
        
        transfer_result = self.map_transfer.start_transfer({
            "file_size": 12800,  # 100 chunks * 128 bytes
            "file_hash": "demo_hash",
            "version": int(time.time())
        })
        
        if transfer_result["status"] == "ready":
            total_chunks = transfer_result["total_chunks"]
            print(f"   Transfer initialized: {total_chunks} chunks")
            
            # Simulate chunk reception
            for i in range(total_chunks):
                await asyncio.sleep(0.1)  # Simulate chunk delay
                
                chunk_result = self.map_transfer.receive_chunk({
                    "chunk_index": i,
                    "data": "41424344",  # "ABCD" in hex
                    "session_id": transfer_result["session_id"]
                })
                
                if i % 10 == 0:  # Progress every 10 chunks
                    progress = (i + 1) / total_chunks * 100
                    print(f"   Progress: {progress:.1f}% ({i+1}/{total_chunks} chunks)")
                    
                    if self.progress_callback:
                        self.progress_callback(i + 1, total_chunks, progress, {
                            "transfer_rate_bps": 1024  # Mock rate
                        })
            
            # Complete transfer
            complete_result = self.map_transfer.complete_transfer()
            print(f"   Transfer: {complete_result['status']}")
        
        print("\n✅ Mock session completed!")
        print("🔄 Server continues running... (Ctrl+C to stop)")
        
        # Keep running
        while self.is_running:
            await asyncio.sleep(1)
    
    async def _handle_auth_write(self, characteristic, value):
        """Handle authentication characteristic writes"""
        
        try:
            message = json.loads(value.decode('utf-8'))
            message_type = message.get("type")
            
            if message_type == "auth_request":
                # Generate challenge
                result = self.auth_manager.generate_challenge(
                    message.get("client_id", "unknown")
                )
                await self._send_auth_response(result)
                
            elif message_type == "auth_response":
                # Verify response
                client_id = message.get("client_id", "unknown")
                result = self.auth_manager.verify_challenge_response(client_id, message)
                await self._send_auth_response(result)
                
        except Exception as e:
            print(f"❌ Auth handler error: {e}")
    
    async def _handle_map_data_write(self, characteristic, value):
        """Handle map data characteristic writes"""
        
        try:
            message = json.loads(value.decode('utf-8'))
            message_type = message.get("type")
            
            if message_type == "transfer_init":
                result = self.map_transfer.start_transfer(message.get("metadata", {}))
                await self._send_status_response(result)
                
            elif message_type == "chunk_data":
                result = self.map_transfer.receive_chunk(message)
                await self._send_status_response(result)
                
        except Exception as e:
            print(f"❌ Map data handler error: {e}")
    
    async def _handle_status_read(self, characteristic):
        """Handle status characteristic reads"""
        
        status = {
            "server_status": "ready" if self.is_running else "stopped",
            "timestamp": time.time(),
            "device_id": self.config["system"]["device_id"]
        }
        
        return json.dumps(status).encode('utf-8')
    
    async def _send_auth_response(self, response):
        """Send authentication response"""
        print(f"🔐 Auth response: {response.get('status', 'unknown')}")
    
    async def _send_status_response(self, response):
        """Send status response"""
        print(f"📊 Status: {response.get('status', 'unknown')}")
    
    async def stop_server(self):
        """Stop BLE server"""
        
        self.is_running = False
        
        if self.server and BLE_AVAILABLE:
            await self.server.stop()
        
        print("🔌 BLE Server stopped")


# Alias for compatibility
BLEMapServer = SimpleBLEServer


async def run_ble_server(config_path: str = "config.json", progress_callback: Optional[Callable] = None):
    """
    Convenience function to run BLE server
    """
    
    server = SimpleBLEServer(config_path)
    
    if progress_callback:
        server.set_progress_callback(progress_callback)
    
    try:
        await server.start_server()
    except KeyboardInterrupt:
        print("\n🛑 Received interrupt signal")
    except Exception as e:
        print(f"❌ Server error: {e}")
    finally:
        await server.stop_server()


def main():
    """Main entry point for direct execution"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Simple BLE Map Server")
    parser.add_argument("--config", default="config.json", help="Config file path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    
    print("🚀 Starting Simple BLE Map Server...")
    print("Press Ctrl+C to stop")
    
    # Simple progress callback
    def progress_callback(chunks_received, total_chunks, progress, metrics):
        if chunks_received % 50 == 0:  # Log every 50 chunks
            rate = metrics.get("transfer_rate_bps", 0)
            print(f"📊 Progress: {progress:.1f}% - Rate: {rate:.0f} bps")
    
    try:
        asyncio.run(run_ble_server(args.config, progress_callback))
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")


if __name__ == "__main__":
    main()