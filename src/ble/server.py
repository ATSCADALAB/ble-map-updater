"""
BLE Server (Pi Side) - Complete Implementation
Server BLE chạy trên Pi để nhận map updates từ enforcement devices

TÍNH NĂNG CHÍNH:
- Hỗ trợ file lên đến 5MB
- Enhanced security với challenge-response authentication  
- Robust chunk management với resume capability
- Real-time progress tracking
- A/B partition atomic updates
- Comprehensive error handling và logging

WORKFLOW:
1. Advertise BLE service và đợi connections
2. Handle authentication challenge-response
3. Receive map file qua chunked transfer protocol
4. Validate và atomically update active map
5. Send completion response và disconnect
"""

import asyncio
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import uuid

# BLE libraries
try:
    from bleak import BleakServer, BleakCharacteristic, BleakGATTCharacteristic
    from bleak.backends.characteristic import BleakGATTCharacteristic
    from bleak.server.characteristic import BleakServerCharacteristic
except ImportError:
    print("⚠️ Warning: bleak not installed. Install with: pip install bleak")
    # Mock classes for development
    class BleakServer:
        pass
    class BleakCharacteristic:
        pass

# Import custom modules
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from protocol.map_transfer import MapTransferManager, TransferState
from protocol.authentication import AuthenticationManager, AuthState
from utils.logger import MapUpdaterLogger

class BLEMapServer:
    """
    BLE Server chạy trên Pi để receive map updates từ enforcement devices
    
    PROTOCOL FLOW:
    1. Advertise BLE service với predefined UUIDs
    2. Accept connection từ enforcement device
    3. Perform mutual authentication qua challenge-response
    4. Receive map metadata và initialize transfer session  
    5. Receive chunks qua BLE characteristics
    6. Validate, decompress, và atomically update map
    7. Send completion status và cleanup
    """
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize BLE server với configuration"""
        
        # Load configuration
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # Initialize components
        self.logger = MapUpdaterLogger(self.config)
        self.map_transfer = MapTransferManager(self.config, self.logger)
        self.auth_manager = AuthenticationManager(
            self.config["system"]["device_id"],
            self.logger
        )
        
        # BLE server setup
        self.server: Optional[BleakServer] = None
        self.current_client = None
        self.is_running = False
        self.connection_active = False
        
        # Service và characteristics
        self.service_uuid = self.config["ble"]["service_uuid"]
        self.char_uuids = self.config["ble"]["characteristics"]
        
        # Characteristics references
        self.auth_char: Optional[BleakServerCharacteristic] = None
        self.map_data_char: Optional[BleakServerCharacteristic] = None
        self.status_char: Optional[BleakServerCharacteristic] = None
        
        # Connection state
        self.authenticated = False
        self.transfer_in_progress = False
        
        # Progress tracking cho UI
        self.progress_callback: Optional[Callable] = None
        
        # Setup map transfer progress callback
        self.map_transfer.set_progress_callback(self._on_transfer_progress)
        
        self.logger.system_logger.info("BLE Map Server initialized", {
            "device_id": self.config["system"]["device_id"],
            "service_uuid": self.service_uuid,
            "max_transfer_size": self.config["ble"]["max_transfer_size"],
            "chunk_size": self.config["ble"]["chunk_size"]
        })
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration từ file"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Failed to load config: {e}")
            # Return default config
            return {
                "system": {"device_id": "CYCLE_SENTINEL_001"},
                "ble": {
                    "service_uuid": "12345678-1234-1234-1234-123456789abc",
                    "characteristics": {
                        "auth": "12345678-1234-1234-1234-123456789abd",
                        "map_data": "12345678-1234-1234-1234-123456789abe",
                        "status": "12345678-1234-1234-1234-123456789abf"
                    },
                    "chunk_size": 128,
                    "max_transfer_size": 5242880
                }
            }
    
    async def start_server(self):
        """Start BLE server và begin advertising"""
        
        try:
            print("🔥 Starting BLE Map Server...")
            
            # Create BLE server
            self.server = BleakServer()
            
            # Add service và characteristics
            await self._setup_ble_service()
            
            # Start server
            await self.server.start()
            self.is_running = True
            
            self.logger.system_logger.info("BLE Server started and advertising")
            print(f"✅ BLE Map Server started successfully!")
            print(f"📡 Service UUID: {self.service_uuid}")
            print(f"🔒 Waiting for enforcement device connections...")
            
            # Keep server running
            while self.is_running:
                await asyncio.sleep(1)
                
                # Check for connection timeout
                if self.connection_active and self.current_client:
                    await self._check_connection_timeout()
                
        except Exception as e:
            self.logger.system_logger.error("Failed to start BLE server", {
                "error": str(e)
            }, e)
            print(f"❌ Failed to start BLE server: {e}")
            raise
    
    async def stop_server(self):
        """Stop BLE server"""
        
        self.is_running = False
        
        if self.current_client:
            await self._disconnect_client("Server shutdown")
        
        if self.server:
            await self.server.stop()
        
        self.logger.system_logger.info("BLE Server stopped")
        print("🛑 BLE Map Server stopped")
    
    async def _setup_ble_service(self):
        """Setup BLE service và characteristics"""
        
        print("🔧 Setting up BLE service and characteristics...")
        
        # Create main service
        await self.server.add_service(self.service_uuid)
        
        # 1. Authentication characteristic (Read/Write/Notify)
        # Dùng để exchange authentication challenges/responses
        self.auth_char = await self.server.add_characteristic(
            self.char_uuids["auth"],
            properties=["read", "write", "notify"],
            value=b"",
            descriptors=None
        )
        self.auth_char.set_write_callback(self._handle_auth_write)
        print(f"  ✅ Auth characteristic: {self.char_uuids['auth']}")
        
        # 2. Map data characteristic (Write/Notify)  
        # Dùng để receive chunks của map data
        self.map_data_char = await self.server.add_characteristic(
            self.char_uuids["map_data"],
            properties=["write", "notify"],
            value=b"",
            descriptors=None
        )
        self.map_data_char.set_write_callback(self._handle_map_data_write)
        print(f"  ✅ Map data characteristic: {self.char_uuids['map_data']}")
        
        # 3. Status characteristic (Read/Notify)
        # Dùng để send status updates về client
        self.status_char = await self.server.add_characteristic(
            self.char_uuids["status"],
            properties=["read", "notify"],
            value=b"",
            descriptors=None
        )
        print(f"  ✅ Status characteristic: {self.char_uuids['status']}")
        
        # Set connection callbacks
        self.server.set_connect_callback(self._on_client_connect)
        self.server.set_disconnect_callback(self._on_client_disconnect)
        
        print("✅ BLE service setup completed")
    
    async def _on_client_connect(self, client):
        """Handle khi client connect"""
        
        if self.current_client:
            # Already have a client, reject new connection
            self.logger.system_logger.warning("Connection rejected - client already connected", {
                "existing_client": str(self.current_client),
                "new_client": str(client)
            })
            return
        
        self.current_client = client
        self.connection_active = True
        self.authenticated = False
        self.transfer_in_progress = False
        
        self.logger.system_logger.info("Client connected", {
            "client": str(client)
        })
        print(f"📱 Client connected: {client}")
        
        # Send welcome status
        await self._send_status({
            "status": "connected",
            "device_id": self.config["system"]["device_id"],
            "server_version": self.config["system"]["version"],
            "max_transfer_size": self.config["ble"]["max_transfer_size"],
            "chunk_size": self.config["ble"]["chunk_size"],
            "authentication_required": True
        })
    
    async def _on_client_disconnect(self, client):
        """Handle khi client disconnect"""
        
        if client == self.current_client:
            self.logger.system_logger.info("Client disconnected", {
                "client": str(client)
            })
            print(f"📱 Client disconnected: {client}")
            
            await self._cleanup_connection()
    
    async def _cleanup_connection(self):
        """Cleanup connection state"""
        
        self.current_client = None
        self.connection_active = False
        self.authenticated = False
        self.transfer_in_progress = False
        
        # Cancel any active transfers
        if self.map_transfer.current_transfer:
            self.map_transfer.cancel_transfer()
        
        # Reset authentication
        self.auth_manager.auth_state = AuthState.IDLE
    
    async def _handle_auth_write(self, value: bytes):
        """
        Handle authentication messages
        
        MESSAGE TYPES:
        - challenge_request: Client yêu cầu authentication challenge
        - challenge_response: Client response cho server challenge
        - mutual_auth: Client gửi challenge cho server
        """
        
        try:
            # Parse message
            message_str = value.decode('utf-8')
            message = json.loads(message_str)
            
            message_type = message.get("type")
            
            self.logger.system_logger.info("Authentication message received", {
                "type": message_type,
                "client": str(self.current_client)
            })
            
            if message_type == "challenge_request":
                await self._handle_challenge_request(message)
                
            elif message_type == "challenge_response":
                await self._handle_challenge_response(message)
                
            elif message_type == "mutual_auth":
                await self._handle_mutual_auth(message)
                
            else:
                await self._send_auth_error(f"Unknown message type: {message_type}")
                
        except Exception as e:
            self.logger.system_logger.error("Authentication message processing failed", {
                "error": str(e),
                "value": value.hex()
            }, e)
            
            await self._send_auth_error(f"Invalid authentication message: {e}")
    
    async def _handle_challenge_request(self, message: Dict[str, Any]):
        """Handle client challenge request"""
        
        try:
            # Generate challenge
            challenge_data = self.auth_manager.generate_challenge()
            
            # Send challenge response
            response = {
                "type": "challenge",
                "challenge_data": challenge_data,
                "server_id": self.config["system"]["device_id"],
                "timestamp": int(time.time())
            }
            
            await self._send_auth_message(response)
            
            self.logger.system_logger.info("Authentication challenge sent", {
                "session_id": challenge_data.get("session_id")
            })
            
        except Exception as e:
            await self._send_auth_error(f"Failed to generate challenge: {e}")
    
    async def _handle_challenge_response(self, message: Dict[str, Any]):
        """Handle client challenge response"""
        
        try:
            # Validate challenge response
            result = self.auth_manager.verify_challenge_response(
                message.get("response_data", {}),
                message.get("signature", "")
            )
            
            if result["valid"]:
                self.authenticated = True
                
                # Send authentication success
                response = {
                    "type": "auth_success",
                    "session_id": result.get("session_id"),
                    "server_capabilities": {
                        "max_transfer_size": self.config["ble"]["max_transfer_size"],
                        "chunk_size": self.config["ble"]["chunk_size"],
                        "compression_support": ["none", "gzip"],
                        "resume_support": True
                    }
                }
                
                await self._send_auth_message(response)
                
                self.logger.system_logger.info("Client authenticated successfully", {
                    "session_id": result.get("session_id")
                })
                print("🔒 Client authenticated successfully!")
                
            else:
                await self._send_auth_error("Authentication failed")
                
        except Exception as e:
            await self._send_auth_error(f"Authentication verification failed: {e}")
    
    async def _handle_mutual_auth(self, message: Dict[str, Any]):
        """Handle mutual authentication từ client"""
        
        try:
            # Process client's challenge
            challenge = message.get("challenge")
            
            # Generate our response
            response_data = self.auth_manager.generate_mutual_response(challenge)
            
            response = {
                "type": "mutual_response", 
                "response_data": response_data
            }
            
            await self._send_auth_message(response)
            
        except Exception as e:
            await self._send_auth_error(f"Mutual authentication failed: {e}")
    
    async def _send_auth_message(self, message: Dict[str, Any]):
        """Send authentication message qua auth characteristic"""
        
        try:
            message_bytes = json.dumps(message).encode('utf-8')
            
            # Truncate nếu message quá dài cho BLE
            if len(message_bytes) > 512:  # BLE MTU limit
                self.logger.system_logger.warning("Auth message truncated", {
                    "original_size": len(message_bytes)
                })
                message_bytes = message_bytes[:512]
            
            await self.auth_char.notify(message_bytes)
            
        except Exception as e:
            self.logger.system_logger.error("Failed to send auth message", {
                "error": str(e)
            }, e)
    
    async def _send_auth_error(self, error_message: str):
        """Send authentication error"""
        
        error_response = {
            "type": "auth_error",
            "error": error_message,
            "timestamp": int(time.time())
        }
        
        await self._send_auth_message(error_response)
        
        self.logger.security_logger.warning("Authentication error", {
            "error": error_message,
            "client": str(self.current_client)
        })
    
    async def _handle_map_data_write(self, value: bytes):
        """
        Handle map data messages
        
        MESSAGE TYPES:
        - transfer_init: Initialize map transfer với metadata
        - chunk_data: Map chunk data
        - transfer_control: Control commands (pause/resume/cancel)
        """
        
        if not self.authenticated:
            await self._send_status({
                "status": "error",
                "error": "Authentication required"
            })
            return
        
        try:
            # Parse message
            message_str = value.decode('utf-8')
            message = json.loads(message_str)
            
            message_type = message.get("type")
            
            if message_type == "transfer_init":
                await self._handle_transfer_init(message)
                
            elif message_type == "chunk_data":
                await self._handle_chunk_data(message)
                
            elif message_type == "transfer_control":
                await self._handle_transfer_control(message)
                
            else:
                await self._send_status({
                    "status": "error",
                    "error": f"Unknown message type: {message_type}"
                })
                
        except Exception as e:
            self.logger.system_logger.error("Map data message processing failed", {
                "error": str(e),
                "value_size": len(value)
            }, e)
            
            await self._send_status({
                "status": "error", 
                "error": f"Invalid message: {e}"
            })
    
    async def _handle_transfer_init(self, message: Dict[str, Any]):
        """Handle transfer initialization"""
        
        try:
            metadata = message.get("metadata", {})
            
            # Start transfer
            result = self.map_transfer.start_transfer(metadata)
            
            if result["status"] == "ready":
                self.transfer_in_progress = True
                print(f"📥 Starting map transfer: {metadata.get('file_size', 0)} bytes")
                
            # Send result back to client
            await self._send_status(result)
            
        except Exception as e:
            await self._send_status({
                "status": "error",
                "error": f"Transfer init failed: {e}"
            })
    
    async def _handle_chunk_data(self, message: Dict[str, Any]):
        """Handle chunk data"""
        
        try:
            chunk_data = message.get("chunk_data", {})
            
            # Process chunk
            result = self.map_transfer.receive_chunk(chunk_data)
            
            # Send acknowledgment
            await self._send_status(result)
            
            # Check if transfer completed
            if result["status"] == "completed":
                self.transfer_in_progress = False
                print("✅ Map transfer completed successfully!")
                
                # Optionally disconnect after completion
                await asyncio.sleep(1)  # Give time for final status
                await self._disconnect_client("Transfer completed")
                
        except Exception as e:
            await self._send_status({
                "status": "error",
                "error": f"Chunk processing failed: {e}"
            })
    
    async def _handle_transfer_control(self, message: Dict[str, Any]):
        """Handle transfer control commands"""
        
        try:
            command = message.get("command")
            
            if command == "pause":
                result = self.map_transfer.pause_transfer()
            elif command == "resume":
                result = self.map_transfer.resume_transfer()
            elif command == "cancel":
                result = self.map_transfer.cancel_transfer()
                self.transfer_in_progress = False
            elif command == "status":
                result = self.map_transfer.get_transfer_status()
            else:
                result = {
                    "status": "error",
                    "error": f"Unknown command: {command}"
                }
            
            await self._send_status(result)
            
        except Exception as e:
            await self._send_status({
                "status": "error",
                "error": f"Control command failed: {e}"
            })
    
    async def _send_status(self, status: Dict[str, Any]):
        """Send status message qua status characteristic"""
        
        try:
            # Add timestamp
            status["timestamp"] = int(time.time())
            
            status_bytes = json.dumps(status).encode('utf-8')
            
            # Handle large messages bằng cách chia nhỏ
            if len(status_bytes) > 512:
                # Truncate hoặc split message
                self.logger.system_logger.warning("Status message truncated", {
                    "original_size": len(status_bytes)
                })
                status_bytes = status_bytes[:512]
            
            await self.status_char.notify(status_bytes)
            
        except Exception as e:
            self.logger.system_logger.error("Failed to send status", {
                "error": str(e)
            }, e)
    
    async def _disconnect_client(self, reason: str):
        """Disconnect current client với reason"""
        
        if self.current_client:
            self.logger.system_logger.info("Disconnecting client", {
                "reason": reason,
                "client": str(self.current_client)
            })
            
            # Send final status
            await self._send_status({
                "status": "disconnecting",
                "reason": reason
            })
            
            # Clean up
            await self._cleanup_connection()
    
    async def _check_connection_timeout(self):
        """Check for connection timeout"""
        
        timeout = self.config["ble"]["connection_timeout"]
        
        if self.map_transfer.current_transfer:
            last_activity = self.map_transfer.current_transfer.last_activity
            if time.time() - last_activity > timeout:
                await self._disconnect_client("Connection timeout")
    
    def _on_transfer_progress(self, chunks_received: int, total_chunks: int, metrics):
        """Handle transfer progress updates"""
        
        progress = (chunks_received / total_chunks) * 100 if total_chunks > 0 else 0
        
        # Log progress periodically
        if chunks_received % 50 == 0 or chunks_received == total_chunks:
            print(f"📊 Transfer progress: {chunks_received}/{total_chunks} chunks ({progress:.1f}%)")
        
        # Call external progress callback nếu có
        if self.progress_callback:
            self.progress_callback(chunks_received, total_chunks, progress, metrics)
    
    def set_progress_callback(self, callback: Callable):
        """Set external progress callback cho UI updates"""
        self.progress_callback = callback
    
    def get_server_status(self) -> Dict[str, Any]:
        """Get current server status"""
        
        return {
            "running": self.is_running,
            "client_connected": self.connection_active,
            "authenticated": self.authenticated,
            "transfer_in_progress": self.transfer_in_progress,
            "current_client": str(self.current_client) if self.current_client else None,
            "transfer_status": self.map_transfer.get_transfer_status() if self.map_transfer else None
        }


# Convenience functions để run server
async def run_ble_server(config_path: str = "config.json", progress_callback: Optional[Callable] = None):
    """
    Convenience function để run BLE server
    
    Args:
        config_path: Path to config file
        progress_callback: Optional callback cho progress updates
    """
    
    server = BLEMapServer(config_path)
    
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
    """Main entry point"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="BLE Map Server for Cycle Sentinel")
    parser.add_argument("--config", default="config.json", help="Config file path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    
    print("🚀 Starting Cycle Sentinel BLE Map Server...")
    print("Press Ctrl+C to stop")
    
    # Simple progress callback
    def progress_callback(chunks_received, total_chunks, progress, metrics):
        if chunks_received % 100 == 0:  # Log every 100 chunks
            print(f"📊 Progress: {progress:.1f}% - Rate: {metrics.transfer_rate_bps:.0f} bps")
    
    try:
        asyncio.run(run_ble_server(args.config, progress_callback))
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")


if __name__ == "__main__":
    main()