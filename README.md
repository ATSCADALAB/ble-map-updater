# 🚀 BLE Map Transfer System - Hướng dẫn hoàn chỉnh

System truyền map files qua Bluetooth Low Energy cho Cycle Sentinel project, hỗ trợ file lên đến **5MB** với compression và security features.

## 📋 Tổng quan hệ thống

```
┌─────────────────┐    BLE Transfer     ┌─────────────────┐
│ Enforcement     │ ─────────────────→ │ Cycle Sentinel  │
│ Device (Client) │    Map Files        │ Pi (Server)     │
│                 │    up to 5MB        │                 │
└─────────────────┘                     └─────────────────┘
```

**Workflow:**
1. **Pi** chạy BLE Server, advertise service
2. **Enforcement Device** scan và connect to Pi
3. **Authentication** qua challenge-response protocol
4. **Map transfer** với chunked protocol (128-byte chunks)
5. **Validation** và atomic file replacement
6. **Completion** notification và disconnect

## 🛠️ Installation & Setup

### 1. Clone và setup project
```bash
git clone <repository>
cd cycle-sentinel
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. System setup (Pi only)
```bash
# Enable Bluetooth on Pi
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# Install system packages
sudo apt-get update
sudo apt-get install bluetooth libbluetooth-dev
```

### 4. Create configuration
```bash
# Tạo config file mặc định
python run_ble_system.py --create-config

# Hoặc copy từ example
cp config.json.example config.json
```

## ⚙️ Configuration

File `config.json` chứa toàn bộ cấu hình:

```json
{
  "ble": {
    "chunk_size": 128,           // Chunk size (bytes)
    "max_transfer_size": 5242880, // 5MB limit
    "compression_enabled": true,  // Auto compression
    "max_chunks_per_second": 10   // Rate limiting
  },
  "security": {
    "required_signature": true,   // Digital signatures
    "auth_timeout": 60           // Auth timeout (seconds)
  },
  "storage": {
    "maps_dir": "./maps",        // Map storage directory
    "active_map": "./maps/active/current_map.json"
  }
}
```

**Quan trọng cho file 5MB:**
- `chunk_size: 128` - Tối ưu cho BLE performance
- `compression_enabled: true` - Giảm transfer time
- `session_timeout: 600` - 10 phút cho file lớn

## 🚀 Cách sử dụng

### 1. Chạy BLE Server (Pi Side)

```bash
# Start server và wait for connections
python run_ble_system.py server

# With custom config
python run_ble_system.py server --config custom_config.json

# Verbose logging
python run_ble_system.py server --verbose
```

**Output sẽ thấy:**
```
🔥 BLE Map Server started successfully!
📡 Service UUID: 12345678-1234-1234-1234-123456789abc
🔒 Waiting for enforcement device connections...
```

### 2. Send Map từ Client (Enforcement Device)

```bash
# Send map file to any Pi device
python run_ble_system.py client map_file.json

# Send to specific device
python run_ble_system.py client map_file.json --device AA:BB:CC:DD:EE:FF

# With custom config
python run_ble_system.py client map_file.json --config client_config.json
```

**Progress tracking:**
```
📤 Sending: 1,234/5,678 chunks (21.7%)
📊 Transfer: 2,500/5,678 chunks (44.0%) - Rate: 1,234 bps
✅ Map sent successfully!
```

### 3. Run Integration Tests

```bash
# Run all tests
python run_ble_system.py test

# Quick test (skip slow tests)
python run_ble_system.py test --quick

# Specific test
python run_ble_system.py test --test test_01_map_transfer_manager_basic

# Verbose test output
python run_ble_system.py test --verbose
```

### 4. Demo Mode

```bash
# Run complete demo với mock data
python run_ble_system.py demo

# Demo sẽ tự động:
# - Tạo demo map files
# - Setup mock BLE environment  
# - Simulate transfer process
# - Test compression
# - Performance benchmarking
```

### 5. System Status

```bash
# Check system status
python run_ble_system.py status
```

**Output:**
```
📊 BLE System Status
Configuration: ✅ Valid
Dependencies: ✅ OK
Maps directory: ✅ Exists
Active map: ✅ 2,345,678 bytes
🟢 System ready
```

## 📁 Cấu trúc Project

```
cycle-sentinel/
├── src/
│   ├── ble/                    # BLE communication modules
│   │   ├── server.py          # BLE Server (Pi side)
│   │   ├── client.py          # BLE Client (enforcement device)
│   │   └── protocol.py        # BLE protocol definitions
│   ├── protocol/              # Transfer protocol
│   │   ├── map_transfer.py    # Enhanced transfer manager
│   │   └── authentication.py  # Security authentication
│   ├── utils/                 # Utilities
│   │   ├── logger.py         # Logging system
│   │   └── file_manager.py   # File management
│   └── tests/                 # Integration tests
│       └── test_ble_integration.py
├── maps/                      # Map storage
│   ├── active/               # Current active map
│   ├── backup/               # Backup maps
│   └── temp/                 # Temporary files
├── logs/                     # System logs
├── config.json              # Main configuration
├── requirements.txt         # Dependencies
└── run_ble_system.py       # Main system runner
```

## 🔧 Development Guide

### Tạo Map File mới

Map file format (JSON):
```json
{
  "metadata": {
    "version": 123456789,
    "created": 1640995200,
    "description": "Speed zones for downtown area",
    "schema_version": "1.0"
  },
  "zones": [
    {
      "id": "zone_001",
      "type": "speed_limit",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[lat1, lng1], [lat2, lng2], ...]]
      },
      "properties": {
        "speed_limit": 25,
        "zone_type": "residential"
      }
    }
  ]
}
```

### Extend BLE Protocol

Để thêm message types mới:

1. **Update protocol constants:**
```python
# src/ble/protocol.py
class MessageType:
    TRANSFER_INIT = "transfer_init"
    CHUNK_DATA = "chunk_data"
    YOUR_NEW_TYPE = "your_new_type"  # ← Add here
```

2. **Handle in server:**
```python
# src/ble/server.py
async def _handle_map_data_write(self, value: bytes):
    message_type = message.get("type")
    
    if message_type == "your_new_type":
        await self._handle_your_new_type(message)
```

3. **Add client support:**
```python
# src/ble/client.py
async def send_your_new_message(self, data):
    message = {
        "type": "your_new_type",
        "data": data
    }
    await self._send_map_data_message(message)
```

### Custom Authentication

Để implement custom authentication:

1. **Extend AuthenticationManager:**
```python
# src/protocol/authentication.py
class CustomAuthManager(AuthenticationManager):
    def generate_challenge(self):
        # Your custom challenge logic
        pass
    
    def verify_challenge_response(self, response, signature):
        # Your custom verification logic
        pass
```

2. **Update server setup:**
```python
self.auth_manager = CustomAuthManager(device_id, logger)
```

## 🧪 Testing Guide

### Unit Tests

```bash
# Run specific test categories
python -m pytest src/tests/test_map_transfer.py -v
python -m pytest src/tests/test_authentication.py -v
```

### Integration Tests

```bash
# Full integration test suite
python run_ble_system.py test

# Test scenarios:
# ✅ Basic map transfer (< 1MB)
# ✅ Large file transfer (5MB) 
# ✅ Compression testing
# ✅ Authentication flow
# ✅ Error handling
# ✅ Resume capability
# ✅ Performance benchmarking
```

### Performance Testing

```bash
# Benchmark different file sizes
python src/tests/test_performance.py

# Expected results for 5MB file:
# - Chunks: ~40,000 (128-byte chunks)
# - Transfer time: 60-120 seconds (depends on BLE speed)
# - Compression: 30-60% reduction (for JSON maps)
```

### Mock Testing (No BLE Hardware)

```bash
# Run tests without BLE hardware
python run_ble_system.py demo

# Uses mock BLE environment:
# - Simulated connections
# - Memory-based transfer
# - All protocol features tested
```

## 🚨 Troubleshooting

### Common Issues

**1. BLE Connection Failed**
```
❌ Connection failed: [Errno 16] Device or resource busy
```
**Solution:**
```bash
# Reset Bluetooth stack
sudo systemctl restart bluetooth
sudo hciconfig hci0 down
sudo hciconfig hci0 up
```

**2. Permission Denied**
```
❌ Permission denied accessing Bluetooth
```
**Solution:**
```bash
# Add user to bluetooth group
sudo usermod -a -G bluetooth $USER
# Logout and login again
```

**3. Transfer Timeout**
```
❌ Transfer completion timeout
```
**Solution:**
- Check BLE signal strength
- Increase timeout in config: `"session_timeout": 1200`
- Try smaller chunk size: `"chunk_size": 64`

**4. Large File Issues**
```
❌ File too large: 6000000 > 5242880
```
**Solution:**
```bash
# Enable compression
"compression_enabled": true

# Or increase limit (not recommended)
"max_transfer_size": 10485760  # 10MB
```

### Debug Mode

```bash
# Enable debug logging
python run_ble_system.py server --verbose

# Check logs
tail -f logs/system.log
tail -f logs/transfers.log
```

### Performance Optimization

**For 5MB files:**

1. **Optimize chunk size:**
```json
{
  "chunk_size": 128,  // Best for BLE MTU
  "max_chunks_per_second": 20  // Increase if stable
}
```

2. **Enable compression:**
```json
{
  "compression_enabled": true,
  "compression_threshold": 1048576  // 1MB
}
```

3. **Tune timeouts:**
```json
{
  "session_timeout": 600,      // 10 minutes
  "connection_timeout": 120    // 2 minutes
}
```

## 📊 Performance Expectations

### Transfer Rates (5MB file)

| Configuration | Time | Rate | Notes |
|---------------|------|------|-------|
| No compression | 180s | 28 KB/s | Raw JSON transfer |
| With compression | 120s | 42 KB/s | ~40% faster |
| Optimized settings | 90s | 56 KB/s | Tuned chunk size |

### Memory Usage

| Component | RAM Usage | Notes |
|-----------|-----------|-------|
| BLE Server | ~50MB | Base server |
| 5MB Transfer | +15MB | Temporary buffers |
| Compression | +10MB | Compression overhead |
| **Total** | **~75MB** | Peak during transfer |

## 🔒 Security Considerations

### Authentication

- **Challenge-Response:** Mutual authentication
- **Signatures:** ECDSA P-256 (configurable)
- **Timeouts:** 60-second auth window
- **Replay Protection:** Nonces và timestamps

### Data Integrity

- **Hash Validation:** SHA-256 checksums
- **Chunk Verification:** MD5 per chunk
- **Atomic Updates:** A/B partition scheme
- **Rollback:** Automatic on validation failure

### Network Security

- **BLE Encryption:** Built-in BLE security
- **Range Limitation:** ~10m range naturally limits exposure
- **Device Pairing:** Optional BLE pairing support

## 📚 API Reference

### MapTransferManager

```python
from protocol.map_transfer import MapTransferManager

manager = MapTransferManager(config)

# Start transfer
result = manager.start_transfer(metadata)

# Receive chunks
result = manager.receive_chunk(chunk_data)

# Control transfer
manager.pause_transfer()
manager.resume_transfer()
manager.cancel_transfer()

# Get status
status = manager.get_transfer_status()
```

### BLEMapServer

```python
from ble.server import BLEMapServer

server = BLEMapServer("config.json")

# Set progress callback
server.set_progress_callback(progress_func)

# Start server
await server.start_server()

# Get status
status = server.get_server_status()
```

### BLEMapClient

```python
from ble.client import BLEMapClient

client = BLEMapClient("config.json")

# Scan for devices
devices = await client.scan_for_devices()

# Connect
await client.connect_to_device(device)

# Authenticate
await client.authenticate()

# Send file
await client.send_map_file(file_path)
```

## 🤝 Contributing

### Code Style

- **Python 3.8+** required
- **Type hints** for all functions
- **Docstrings** for public APIs
- **Error handling** with proper logging

### Pull Request Process

1. Fork repository
2. Create feature branch
3. Add tests for new features
4. Run test suite: `python run_ble_system.py test`
5. Update documentation
6. Submit pull request

### Testing Requirements

- All new features need tests
- Integration tests for BLE components
- Performance tests for large files
- Mock tests for CI/CD

## 📞 Support

### Issues

- **BLE connectivity:** Check hardware compatibility
- **Large file transfers:** Verify configuration
- **Authentication:** Check certificates/keys
- **Performance:** Use profiling tools

### Resources

- **BLE Documentation:** [Bleak library docs](https://bleak.readthedocs.io/)
- **Raspberry Pi BLE:** [Official Pi documentation](https://www.raspberrypi.org/documentation/)
- **Bluetooth Low Energy:** [BLE specification](https://www.bluetooth.com/specifications/specs/)

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **Bleak library** for Python BLE support
- **Raspberry Pi Foundation** for excellent BLE hardware
- **Bluetooth SIG** for BLE specifications
- **Contributors** to the Cycle Sentinel project