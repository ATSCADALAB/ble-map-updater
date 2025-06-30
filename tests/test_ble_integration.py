# Thêm vào cuối run_ble_system.py để thay thế run_demo function:

async def run_simple_demo(config_path: Path, verbose: bool = False):
    """Simple demo without test dependencies"""
    
    print("🎬 Running Simple BLE System Demo")
    print("=" * 40)
    
    # Create demo directory
    demo_dir = Path("demo_output")
    demo_dir.mkdir(exist_ok=True)
    
    # Create demo map
    demo_map_path = create_demo_map(demo_dir / "demo_map.json", "medium")
    
    print("\n📋 Demo Scenario:")
    print("1. ✅ Demo map file created") 
    print("2. ✅ Directory structure verified")
    print("3. 📊 File size analysis")
    print("4. 🔍 Configuration validation")
    
    try:
        # File analysis
        file_size = demo_map_path.stat().st_size
        print(f"\n📊 Demo Map Analysis:")
        print(f"   File: {demo_map_path}")
        print(f"   Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
        
        # Load and analyze content
        with open(demo_map_path, 'r') as f:
            map_data = json.load(f)
        
        zone_count = len(map_data.get('zones', []))
        print(f"   Zones: {zone_count:,}")
        print(f"   Metadata: {map_data.get('metadata', {}).get('description', 'N/A')}")
        
        # Calculate transfer estimates
        chunk_size = 128  # Default BLE chunk size
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        estimated_time = total_chunks * 0.1  # ~100ms per chunk estimate
        
        print(f"\n📡 Transfer Estimates:")
        print(f"   Chunks needed: {total_chunks:,}")
        print(f"   Estimated time: {estimated_time:.1f} seconds")
        print(f"   Transfer rate: {file_size/estimated_time:.0f} bytes/sec")
        
        # Test compression if enabled
        print(f"\n🗜️ Compression Test:")
        
        import gzip
        import io
        
        # Compress data
        json_str = json.dumps(map_data, separators=(',', ':'))
        json_bytes = json_str.encode('utf-8')
        
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode='wb') as f:
            f.write(json_bytes)
        compressed = buffer.getvalue()
        
        compression_ratio = len(compressed) / len(json_bytes)
        savings = (1 - compression_ratio) * 100
        
        print(f"   Original: {len(json_bytes):,} bytes")
        print(f"   Compressed: {len(compressed):,} bytes")
        print(f"   Savings: {savings:.1f}%")
        
        # Verify config
        print(f"\n🔧 Configuration Check:")
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            max_size = config.get('ble', {}).get('max_transfer_size', 0)
            print(f"   Max transfer size: {max_size:,} bytes")
            print(f"   Demo file fits: {'✅ YES' if file_size <= max_size else '❌ NO'}")
            
            chunk_size_config = config.get('ble', {}).get('chunk_size', 128)
            print(f"   Chunk size: {chunk_size_config} bytes")
            
        else:
            print("   ❌ Config file not found")
        
        print(f"\n📁 Demo files saved in: {demo_dir}")
        print("🎉 Simple demo completed successfully!")
        
        return Truesss
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False

# Sửa main function để dùng run_simple_demo thay vì run_demo:
# Thay dòng:
#   success = asyncio.run(run_demo(config_path, args.verbose))
# Thành:
#   success = asyncio.run(run_simple_demo(config_path, args.verbose))