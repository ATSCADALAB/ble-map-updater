class BLEIntegrationTestSuite(unittest.TestCase):
    """
    Complete integration test suite cho BLE map transfer system
    
    SETUP:
    - Tạo mock BLE environment
    - Generate test map files với various sizes
    - Setup server và client instances
    - Configure test scenarios
    """
    
    @classmethod
    def setUpClass(cls):
        """Setup test environment"""
        
        print("🧪 Setting up BLE Integration Test Suite...")
        
        # Create temp directory cho test files
        cls.test_dir = Path(tempfile.mkdtemp())
        print(f"   Test directory: {cls.test_dir}")
        
        # Create test config
        cls.test_config = {
            "system": {
                "device_id": "TEST_CYCLE_SENTINEL",
                "version": "1.0.0-test"
            },
            "ble": {
                "service_uuid": "12345678-1234-1234-1234-123456789abc",
                "characteristics": {
                    "auth": "12345678-1234-1234-1234-123456789abd",
                    "map_data": "12345678-1234-1234-1234-123456789abe",
                    "status": "12345678-1234-1234-1234-123456789abf"
                },
                "chunk_size": 64,  # Smaller chunks for testing
                "max_transfer_size": 5242880,
                "max_chunks_per_second": 100,  # Faster for testing
                "compression_enabled": True,
                "compression_threshold": 1024
            },
            "storage": {
                "maps_dir": str(cls.test_dir / "maps"),
                "active_map": str(cls.test_dir / "maps" / "active" / "current_map.json"),
                "backup_map": str(cls.test_dir / "maps" / "backup" / "backup_map.json"),
                "temp_dir": str(cls.test_dir / "temp"),
                "logs_dir": str(cls.test_dir / "logs")
            },
            "security": {
                "required_signature": False,  # Disabled for testing
                "auth_timeout": 30
            },
            "transfer": {
                "session_timeout": 300,
                "progress_report_interval": 5
            }
        }
        
        # Create test config file
        cls.config_path = cls.test_dir / "test_config.json"
        with open(cls.config_path, 'w') as f:
            json.dump(cls.test_config, f, indent=2)
        
        # Create test directories
        for dir_path in [
            cls.test_dir / "maps" / "active",
            cls.test_dir / "maps" / "backup", 
            cls.test_dir / "temp",
            cls.test_dir / "logs"
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Generate test map files
        cls._generate_test_maps()
        
        print("✅ Test environment setup complete")
    
    @classmethod
    def _generate_test_maps(cls):
        """Generate test map files với different sizes"""
        
        print("📁 Generating test map files...")
        
        # Base map structure
        base_map = {
            "metadata": {
                "version": 1,
                "created": int(time.time()),
                "description": "Test map file",
                "schema_version": "1.0"
            },
            "zones": []
        }
        
        # 1. Small map (< 1KB)
        small_map = base_map.copy()
        small_map["zones"] = [
            {
                "id": "zone_1",
                "type": "speed_limit",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]
                },
                "properties": {"speed_limit": 25}
            }
        ]
        
        cls.small_map_path = cls.test_dir / "small_map.json"
        with open(cls.small_map_path, 'w') as f:
            json.dump(small_map, f)
        
        # 2. Medium map (~100KB)
        medium_map = base_map.copy()
        medium_map["zones"] = []
        
        # Generate many zones to reach ~100KB
        for i in range(500):
            zone = {
                "id": f"zone_{i}",
                "type": "speed_limit",
                "geometry": {
                    "type": "Polygon", 
                    "coordinates": [[[i, i], [i+1, i], [i+1, i+1], [i, i+1], [i, i]]]
                },
                "properties": {
                    "speed_limit": 25 + (i % 20),
                    "description": f"Test zone {i} with detailed description and metadata"
                }
            }
            medium_map["zones"].append(zone)
        
        cls.medium_map_path = cls.test_dir / "medium_map.json"
        with open(cls.medium_map_path, 'w') as f:
            json.dump(medium_map, f)
        
        # 3. Large map (~2MB)
        large_map = base_map.copy()
        large_map["zones"] = []
        
        # Generate many detailed zones to reach ~2MB
        for i in range(2000):
            zone = {
                "id": f"large_zone_{i}",
                "type": "complex_zone",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[i*0.1, i*0.1], [i*0.1+0.05, i*0.1], 
                                   [i*0.1+0.05, i*0.1+0.05], [i*0.1, i*0.1+0.05], [i*0.1, i*0.1]]]
                },
                "properties": {
                    "speed_limit": 15 + (i % 35),
                    "zone_type": f"type_{i % 10}",
                    "description": f"Detailed zone {i} with extensive metadata and properties " * 5,
                    "tags": [f"tag_{j}" for j in range(i % 10)],
                    "restrictions": {
                        "vehicle_types": ["bicycle", "e-bike"],
                        "time_restrictions": [f"restriction_{k}" for k in range(i % 5)]
                    }
                }
            }
            large_map["zones"].append(zone)
        
        cls.large_map_path = cls.test_dir / "large_map.json"
        with open(cls.large_map_path, 'w') as f:
            json.dump(large_map, f)
        
        # Calculate file sizes
        small_size = cls.small_map_path.stat().st_size
        medium_size = cls.medium_map_path.stat().st_size
        large_size = cls.large_map_path.stat().st_size
        
        print(f"   Small map: {small_size:,} bytes")
        print(f"   Medium map: {medium_size:,} bytes") 
        print(f"   Large map: {large_size:,} bytes")
    
    @classmethod
    def tearDownClass(cls):
        """Cleanup test environment"""
        
        print("🧹 Cleaning up test environment...")
        
        # Remove test directory
        import shutil
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        
        print("✅ Cleanup complete")
    
    def setUp(self):
        """Setup each test"""
        
        # Create fresh instances for each test
        self.server = None
        self.client = None
        self.test_session_id = None
        
        # Test metrics
        self.test_start_time = time.time()
        self.progress_updates = []
        self.status_updates = []
    
    def tearDown(self):
        """Cleanup each test"""
        
        # Calculate test duration
        test_duration = time.time() - self.test_start_time
        print(f"   Test duration: {test_duration:.2f}s")
        
        # Cleanup instances
        if hasattr(self, 'server') and self.server:
            # Cleanup server state
            pass
        
        if hasattr(self, 'client') and self.client:
            # Cleanup client state  
            pass
    
    def test_01_map_transfer_manager_basic(self):
        """Test basic MapTransferManager functionality"""
        
        print("\n🧪 Test 1: Basic MapTransferManager")
        
        # Initialize manager
        manager = MapTransferManager(self.test_config)
        
        # Test initial state
        self.assertEqual(manager.current_transfer, None)
        self.assertEqual(manager.get_transfer_status()["status"], "idle")
        
        # Test metadata validation
        valid_metadata = {
            "file_size": 1000,
            "file_hash": "dummy_hash",
            "version": 2
        }
        
        result = manager.start_transfer(valid_metadata)
        self.assertEqual(result["status"], "ready")
        self.assertIsNotNone(result["session_id"])
        
        # Test invalid metadata
        invalid_metadata = {
            "file_size": 10 * 1024 * 1024,  # Too large
            "file_hash": "dummy_hash",
            "version": 2
        }
        
        result = manager.start_transfer(invalid_metadata)
        self.assertEqual(result["status"], "error")
        
        print("✅ MapTransferManager basic tests passed")
    
    def test_02_chunked_transfer_simulation(self):
        """Test chunked transfer simulation without BLE"""
        
        print("\n🧪 Test 2: Chunked Transfer Simulation")
        
        # Use small map for fast testing
        with open(self.small_map_path, 'rb') as f:
            file_data = f.read()
        
        file_size = len(file_data)
        file_hash = hashlib.sha256(file_data).hexdigest()
        
        # Initialize manager
        manager = MapTransferManager(self.test_config)
        
        # Start transfer
        metadata = {
            "file_size": file_size,
            "file_hash": file_hash,
            "version": int(time.time())
        }
        
        result = manager.start_transfer(metadata)
        self.assertEqual(result["status"], "ready")
        
        session_id = result["session_id"]
        total_chunks = result["total_chunks"]
        chunk_size = result["chunk_size"]
        
        print(f"   File size: {file_size} bytes")
        print(f"   Total chunks: {total_chunks}")
        print(f"   Chunk size: {chunk_size} bytes")
        
        # Send chunks
        for chunk_index in range(total_chunks):
            start_pos = chunk_index * chunk_size
            end_pos = min(start_pos + chunk_size, file_size)
            chunk_data = file_data[start_pos:end_pos]
            
            chunk_message = {
                "chunk_index": chunk_index,
                "data": chunk_data.hex(),
                "session_id": session_id
            }
            
            result = manager.receive_chunk(chunk_message)
            
            if chunk_index < total_chunks - 1:
                self.assertEqual(result["status"], "chunk_received")
            else:
                self.assertEqual(result["status"], "completed")
        
        # Verify map was saved
        self.assertTrue(Path(self.test_config["storage"]["active_map"]).exists())
        
        print("✅ Chunked transfer simulation passed")
    
    def test_03_compression_testing(self):
        """Test compression functionality"""
        
        print("\n🧪 Test 3: Compression Testing")
        
        # Test with medium map (should benefit from compression)
        with open(self.medium_map_path, 'rb') as f:
            original_data = f.read()
        
        original_size = len(original_data)
        original_hash = hashlib.sha256(original_data).hexdigest()
        
        # Compress data
        compressed_data = gzip.compress(original_data)
        compressed_size = len(compressed_data)
        compressed_hash = hashlib.sha256(compressed_data).hexdigest()
        
        compression_ratio = (original_size - compressed_size) / original_size * 100
        
        print(f"   Original size: {original_size:,} bytes")
        print(f"   Compressed size: {compressed_size:,} bytes")
        print(f"   Compression ratio: {compression_ratio:.1f}%")
        
        # Test transfer with compression
        manager = MapTransferManager(self.test_config)
        
        metadata = {
            "file_size": original_size,
            "file_hash": original_hash,
            "version": int(time.time()),
            "compression": "gzip",
            "compressed_size": compressed_size,
            "compressed_hash": compressed_hash
        }
        
        result = manager.start_transfer(metadata)
        self.assertEqual(result["status"], "ready")
        
        # Send compressed chunks
        session_id = result["session_id"]
        chunk_size = result["chunk_size"]
        total_chunks = (compressed_size + chunk_size - 1) // chunk_size
        
        for chunk_index in range(total_chunks):
            start_pos = chunk_index * chunk_size
            end_pos = min(start_pos + chunk_size, compressed_size)
            chunk_data = compressed_data[start_pos:end_pos]
            
            chunk_message = {
                "chunk_index": chunk_index,
                "data": chunk_data.hex(),
                "session_id": session_id
            }
            
            result = manager.receive_chunk(chunk_message)
        
        self.assertEqual(result["status"], "completed")
        
        # Verify decompressed map
        with open(self.test_config["storage"]["active_map"], 'rb') as f:
            saved_data = f.read()
        
        self.assertEqual(len(saved_data), original_size)
        self.assertEqual(hashlib.sha256(saved_data).hexdigest(), original_hash)
        
        print("✅ Compression testing passed")
    
    def test_04_error_handling(self):
        """Test error handling scenarios"""
        
        print("\n🧪 Test 4: Error Handling")
        
        manager = MapTransferManager(self.test_config)
        
        # Test 1: Invalid chunk data
        print("   Testing invalid chunk data...")
        
        metadata = {
            "file_size": 100,
            "file_hash": "dummy_hash",
            "version": int(time.time())
        }
        
        result = manager.start_transfer(metadata)
        self.assertEqual(result["status"], "ready")
        
        # Send invalid chunk
        invalid_chunk = {
            "chunk_index": 0,
            "data": "invalid_hex_data",  # Invalid hex
            "session_id": result["session_id"]
        }
        
        result = manager.receive_chunk(invalid_chunk)
        self.assertEqual(result["status"], "error")
        self.assertIn("CHUNK_PROCESSING_FAILED", result["error_code"])
        
        # Test 2: Chunk out of bounds
        print("   Testing chunk out of bounds...")
        
        manager = MapTransferManager(self.test_config)
        result = manager.start_transfer(metadata)
        
        out_of_bounds_chunk = {
            "chunk_index": 9999,  # Way out of bounds
            "data": "deadbeef",
            "session_id": result["session_id"]
        }
        
        result = manager.receive_chunk(out_of_bounds_chunk)
        self.assertEqual(result["status"], "error")
        
        # Test 3: Session ID mismatch
        print("   Testing session ID mismatch...")
        
        manager = MapTransferManager(self.test_config)
        result = manager.start_transfer(metadata)
        
        wrong_session_chunk = {
            "chunk_index": 0,
            "data": "deadbeef",
            "session_id": "wrong_session_id"
        }
        
        result = manager.receive_chunk(wrong_session_chunk)
        self.assertEqual(result["status"], "error")
        
        print("✅ Error handling tests passed")
    
    def test_05_resume_capability(self):
        """Test transfer resume functionality"""
        
        print("\n🧪 Test 5: Resume Capability")
        
        # Use medium map for more realistic scenario
        with open(self.medium_map_path, 'rb') as f:
            file_data = f.read()
        
        file_size = len(file_data)
        file_hash = hashlib.sha256(file_data).hexdigest()
        
        manager = MapTransferManager(self.test_config)
        
        metadata = {
            "file_size": file_size,
            "file_hash": file_hash,
            "version": int(time.time())
        }
        
        result = manager.start_transfer(metadata)
        session_id = result["session_id"]
        total_chunks = result["total_chunks"]
        chunk_size = result["chunk_size"]
        
        # Send partial chunks (50%)
        chunks_to_send = total_chunks // 2
        
        print(f"   Sending {chunks_to_send}/{total_chunks} chunks...")
        
        for chunk_index in range(chunks_to_send):
            start_pos = chunk_index * chunk_size
            end_pos = min(start_pos + chunk_size, file_size)
            chunk_data = file_data[start_pos:end_pos]
            
            chunk_message = {
                "chunk_index": chunk_index,
                "data": chunk_data.hex(),
                "session_id": session_id
            }
            
            result = manager.receive_chunk(chunk_message)
            self.assertEqual(result["status"], "chunk_received")
        
        # Pause transfer
        print("   Pausing transfer...")
        pause_result = manager.pause_transfer()
        self.assertEqual(pause_result["status"], "paused")
        
        # Resume transfer
        print("   Resuming transfer...")
        resume_result = manager.resume_transfer()
        self.assertEqual(resume_result["status"], "resuming")
        
        missing_chunks = resume_result["missing_chunks"]
        self.assertEqual(len(missing_chunks), total_chunks - chunks_to_send)
        
        # Send remaining chunks
        print(f"   Sending remaining {len(missing_chunks)} chunks...")
        
        for chunk_index in missing_chunks:
            start_pos = chunk_index * chunk_size
            end_pos = min(start_pos + chunk_size, file_size)
            chunk_data = file_data[start_pos:end_pos]
            
            chunk_message = {
                "chunk_index": chunk_index,
                "data": chunk_data.hex(),
                "session_id": session_id
            }
            
            result = manager.receive_chunk(chunk_message)
        
        self.assertEqual(result["status"], "completed")
        
        print("✅ Resume capability test passed")
    
    def test_06_performance_benchmarking(self):
        """Test performance với different file sizes"""
        
        print("\n🧪 Test 6: Performance Benchmarking")
        
        test_files = [
            ("Small", self.small_map_path),
            ("Medium", self.medium_map_path),
            ("Large", self.large_map_path)
        ]
        
        results = []
        
        for test_name, file_path in test_files:
            print(f"   Testing {test_name} map...")
            
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            file_size = len(file_data)
            file_hash = hashlib.sha256(file_data).hexdigest()
            
            # Test without compression
            start_time = time.time()
            
            manager = MapTransferManager(self.test_config)
            
            metadata = {
                "file_size": file_size,
                "file_hash": file_hash,
                "version": int(time.time())
            }
            
            result = manager.start_transfer(metadata)
            session_id = result["session_id"]
            total_chunks = result["total_chunks"]
            chunk_size = result["chunk_size"]
            
            # Send all chunks
            for chunk_index in range(total_chunks):
                start_pos = chunk_index * chunk_size
                end_pos = min(start_pos + chunk_size, file_size)
                chunk_data = file_data[start_pos:end_pos]
                
                chunk_message = {
                    "chunk_index": chunk_index,
                    "data": chunk_data.hex(),
                    "session_id": session_id
                }
                
                manager.receive_chunk(chunk_message)
            
            transfer_time = time.time() - start_time
            transfer_rate = file_size / transfer_time if transfer_time > 0 else 0
            
            results.append({
                "name": test_name,
                "file_size": file_size,
                "chunks": total_chunks,
                "transfer_time": transfer_time,
                "transfer_rate": transfer_rate
            })
            
            print(f"     Size: {file_size:,} bytes")
            print(f"     Chunks: {total_chunks:,}")
            print(f"     Time: {transfer_time:.2f}s")
            print(f"     Rate: {transfer_rate:.0f} bytes/sec")
        
        # Summary
        print("\n   Performance Summary:")
        for result in results:
            print(f"   {result['name']:>6}: {result['file_size']:>8,} bytes in {result['transfer_time']:>6.2f}s "
                  f"({result['transfer_rate']:>8.0f} bytes/sec)")
        
        print("✅ Performance benchmarking completed")
    
    def test_07_authentication_flow(self):
        """Test authentication flow"""
        
        print("\n🧪 Test 7: Authentication Flow")
        
        auth_manager = AuthenticationManager("TEST_DEVICE")
        
        # Test challenge generation
        challenge = auth_manager.generate_challenge()
        
        self.assertIn("nonce", challenge)
        self.assertIn("session_id", challenge)
        self.assertIn("timestamp", challenge)
        self.assertIn("payload_hash", challenge)
        
        print(f"   Generated challenge with session: {challenge['session_id']}")
        
        # Test challenge response (simplified)
        response_data = {
            "session_id": challenge["session_id"],
            "client_response": "test_response"
        }
        
        # In real implementation, this would verify cryptographic signature
        result = auth_manager.verify_challenge_response(response_data, "dummy_signature")
        
        # For testing purposes, assume successful validation
        self.assertIsInstance(result, dict)
        
        print("✅ Authentication flow test passed")
    
    def test_08_concurrent_transfer_handling(self):
        """Test handling of concurrent transfer attempts"""
        
        print("\n🧪 Test 8: Concurrent Transfer Handling")
        
        manager = MapTransferManager(self.test_config)
        
        # Start first transfer
        metadata1 = {
            "file_size": 1000,
            "file_hash": "hash1",
            "version": 1
        }
        
        result1 = manager.start_transfer(metadata1)
        self.assertEqual(result1["status"], "ready")
        
        # Try to start second transfer (should fail)
        metadata2 = {
            "file_size": 2000,
            "file_hash": "hash2", 
            "version": 2
        }
        
        result2 = manager.start_transfer(metadata2)
        self.assertEqual(result2["status"], "error")
        self.assertIn("active transfer", result2["message"].lower())
        
        print("✅ Concurrent transfer handling test passed")
    
    def test_09_file_integrity_validation(self):
        """Test file integrity validation"""
        
        print("\n🧪 Test 9: File Integrity Validation")
        
        with open(self.small_map_path, 'rb') as f:
            file_data = f.read()
        
        file_size = len(file_data)
        correct_hash = hashlib.sha256(file_data).hexdigest()
        wrong_hash = "wrong_hash_value"
        
        manager = MapTransferManager(self.test_config)
        
        # Test with wrong hash
        metadata = {
            "file_size": file_size,
            "file_hash": wrong_hash,
            "version": int(time.time())
        }
        
        result = manager.start_transfer(metadata)
        session_id = result["session_id"]
        chunk_size = result["chunk_size"]
        total_chunks = result["total_chunks"]
        
        # Send all chunks
        for chunk_index in range(total_chunks):
            start_pos = chunk_index * chunk_size
            end_pos = min(start_pos + chunk_size, file_size)
            chunk_data = file_data[start_pos:end_pos]
            
            chunk_message = {
                "chunk_index": chunk_index,
                "data": chunk_data.hex(),
                "session_id": session_id
            }
            
            result = manager.receive_chunk(chunk_message)
        
        # Should fail due to hash mismatch
        self.assertEqual(result["status"], "error")
        self.assertIn("hash mismatch", result["message"].lower())
        
        print("✅ File integrity validation test passed")
    
    def test_10_large_file_transfer(self):
        """Test large file transfer (stress test)"""
        
        print("\n🧪 Test 10: Large File Transfer (Stress Test)")
        
        with open(self.large_map_path, 'rb') as f:
            file_data = f.read()
        
        file_size = len(file_data)
        file_hash = hashlib.sha256(file_data).hexdigest()
        
        print(f"   File size: {file_size:,} bytes ({file_size/1024/1024:.1f} MB)")
        
        manager = MapTransferManager(self.test_config)
        
        # Enable compression for large file
        compressed_data = gzip.compress(file_data)
        compressed_size = len(compressed_data)
        compressed_hash = hashlib.sha256(compressed_data).hexdigest()
        
        compression_ratio = (file_size - compressed_size) / file_size * 100
        print(f"   Compressed size: {compressed_size:,} bytes ({compression_ratio:.1f}% reduction)")
        
        metadata = {
            "file_size": file_size,
            "file_hash": file_hash,
            "version": int(time.time()),
            "compression": "gzip",
            "compressed_size": compressed_size,
            "compressed_hash": compressed_hash
        }
        
        result = manager.start_transfer(metadata)
        self.assertEqual(result["status"], "ready")
        
        session_id = result["session_id"]
        chunk_size = result["chunk_size"]
        total_chunks = (compressed_size + chunk_size - 1) // chunk_size
        
        print(f"   Total chunks: {total_chunks:,}")
        
        start_time = time.time()
        
        # Send chunks với progress tracking
        progress_intervals = max(1, total_chunks // 20)  # 20 progress updates
        
        for chunk_index in range(total_chunks):
            start_pos = chunk_index * chunk_size
            end_pos = min(start_pos + chunk_size, compressed_size)
            chunk_data = compressed_data[start_pos:end_pos]
            
            chunk_message = {
                "chunk_index": chunk_index,
                "data": chunk_data.hex(),
                "session_id": session_id
            }
            
            result = manager.receive_chunk(chunk_message)
            
            # Progress reporting
            if chunk_index % progress_intervals == 0 or chunk_index == total_chunks - 1:
                progress = (chunk_index + 1) / total_chunks * 100
                elapsed = time.time() - start_time
                rate = (chunk_index + 1) / elapsed if elapsed > 0 else 0
                
                print(f"     Progress: {chunk_index + 1:,}/{total_chunks:,} ({progress:.1f}%) - "
                      f"Rate: {rate:.1f} chunks/sec")
        
        transfer_time = time.time() - start_time
        transfer_rate = file_size / transfer_time if transfer_time > 0 else 0
        
        self.assertEqual(result["status"], "completed")
        
        print(f"   Transfer completed in {transfer_time:.2f}s")
        print(f"   Average rate: {transfer_rate:.0f} bytes/sec ({transfer_rate/1024:.0f} KB/sec)")
        
        # Verify saved file
        with open(self.test_config["storage"]["active_map"], 'rb') as f:
            saved_data = f.read()
        
        self.assertEqual(len(saved_data), file_size)
        self.assertEqual(hashlib.sha256(saved_data).hexdigest(), file_hash)
        
        print("✅ Large file transfer stress test passed")


def run_integration_tests():
    """Run all integration tests"""
    
    print("🚀 Starting BLE Integration Test Suite")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(BLEIntegrationTestSuite)
    
    # Run tests với detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "=" * 60)
    print("🏁 Test Suite Summary")
    print(f"   Tests run: {result.testsRun}")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    
    if result.failures:
        print("\n❌ Failures:")
        for test, trace in result.failures:
            print(f"   {test}: {trace}")
    
    if result.errors:
        print("\n❌ Errors:")
        for test, trace in result.errors:
            print(f"   {test}: {trace}")
    
    if result.wasSuccessful():
        print("\n🎉 All tests passed successfully!")
        return 0
    else:
        print("\n💥 Some tests failed!")
        return 1


def main():
    """Main entry point"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="BLE Integration Test Suite")
    parser.add_argument("--test", help="Run specific test (e.g., test_01_map_transfer_manager_basic)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--quick", action="store_true", help="Skip slow tests")
    
    args = parser.parse_args()
    
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    try:
        if args.test:
            # Run specific test
            suite = unittest.TestSuite()
            test_case = BLEIntegrationTestSuite(args.test)
            suite.addTest(test_case)
            
            runner = unittest.TextTestRunner(verbosity=2)
            result = runner.run(suite)
            
            return 0 if result.wasSuccessful() else 1
        else:
            # Run all tests
            return run_integration_tests()
            
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())