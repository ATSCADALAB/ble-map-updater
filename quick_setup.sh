#!/bin/bash
# Quick Setup Script for BLE Map Transfer System
# Automatically sets up the system on Raspberry Pi

echo "🚀 BLE Map Transfer System - Quick Setup"
echo "========================================"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running on Pi
check_system() {
    print_status "Checking system..."
    
    if [[ -f /proc/device-tree/model ]] && grep -q "Raspberry Pi" /proc/device-tree/model; then
        print_success "Running on Raspberry Pi"
        return 0
    else
        print_warning "Not running on Raspberry Pi - continuing anyway"
        return 0
    fi
}

# Update system packages
update_system() {
    print_status "Updating system packages..."
    
    sudo apt-get update
    if [[ $? -eq 0 ]]; then
        print_success "System packages updated"
    else
        print_error "Failed to update system packages"
        exit 1
    fi
}

# Install system dependencies
install_system_deps() {
    print_status "Installing system dependencies..."
    
    sudo apt-get install -y \
        bluetooth \
        libbluetooth-dev \
        bluez \
        python3-pip \
        python3-venv \
        git
    
    if [[ $? -eq 0 ]]; then
        print_success "System dependencies installed"
    else
        print_error "Failed to install system dependencies"
        exit 1
    fi
}

# Setup Bluetooth
setup_bluetooth() {
    print_status "Setting up Bluetooth..."
    
    # Enable Bluetooth service
    sudo systemctl enable bluetooth
    sudo systemctl start bluetooth
    
    # Check if Bluetooth is working
    if hciconfig hci0 >/dev/null 2>&1; then
        print_success "Bluetooth is working"
    else
        print_warning "Bluetooth interface not found - may need reboot"
    fi
}

# Create Python virtual environment
setup_python_env() {
    print_status "Setting up Python environment..."
    
    # Create virtual environment
    python3 -m venv venv
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    print_success "Python virtual environment created"
}

# Install Python dependencies
install_python_deps() {
    print_status "Installing Python dependencies..."
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Install main dependencies
    pip install bleak cryptography jsonschema
    
    if [[ $? -eq 0 ]]; then
        print_success "Python dependencies installed"
    else
        print_error "Failed to install Python dependencies"
        exit 1
    fi
}

# Create project structure
create_structure() {
    print_status "Creating project structure..."
    
    # Create directories
    mkdir -p src/{ble,protocol,utils,tests}
    mkdir -p maps/{active,backup,temp}
    mkdir -p logs
    
    print_success "Project structure created"
}

# Create configuration
create_config() {
    print_status "Creating configuration..."
    
    # Use the main script to create config
    source venv/bin/activate
    python run_ble_system.py --create-config
    
    if [[ $? -eq 0 ]]; then
        print_success "Configuration created"
    else
        print_warning "Failed to create config - will create manually"
        
        # Create basic config manually
        cat > config.json << 'EOF'
{
  "system": {
    "device_id": "CYCLE_SENTINEL_PI_001",
    "version": "1.0.0"
  },
  "ble": {
    "service_uuid": "12345678-1234-1234-1234-123456789abc",
    "characteristics": {
      "auth": "12345678-1234-1234-1234-123456789abd",
      "map_data": "12345678-1234-1234-1234-123456789abe",
      "status": "12345678-1234-1234-1234-123456789abf"
    },
    "chunk_size": 128,
    "max_transfer_size": 5242880
  },
  "storage": {
    "maps_dir": "./maps",
    "active_map": "./maps/active/current_map.json",
    "logs_dir": "./logs"
  },
  "security": {
    "auth_timeout": 60,
    "required_signature": false
  }
}
EOF
        print_success "Basic configuration created manually"
    fi
}

# Set up systemd service (optional)
setup_service() {
    print_status "Setting up systemd service..."
    
    # Get current directory
    CURRENT_DIR=$(pwd)
    
    # Create service file
    sudo tee /etc/systemd/system/ble-map-server.service > /dev/null << EOF
[Unit]
Description=BLE Map Transfer Server
After=bluetooth.service
Wants=bluetooth.service

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=${CURRENT_DIR}
Environment=PATH=${CURRENT_DIR}/venv/bin
ExecStart=${CURRENT_DIR}/venv/bin/python run_ble_system.py server
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd
    sudo systemctl daemon-reload
    
    print_success "Systemd service created"
    print_status "To enable auto-start: sudo systemctl enable ble-map-server"
    print_status "To start service: sudo systemctl start ble-map-server"
}

# Test installation
test_installation() {
    print_status "Testing installation..."
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Run system status check
    python run_ble_system.py status
    
    if [[ $? -eq 0 ]]; then
        print_success "Installation test passed"
    else
        print_warning "Installation test showed some issues"
    fi
}

# Main setup function
main() {
    echo
    print_status "Starting BLE Map Transfer System setup..."
    echo
    
    # Run setup steps
    check_system
    update_system
    install_system_deps
    setup_bluetooth
    setup_python_env
    install_python_deps
    create_structure
    create_config
    
    # Ask about systemd service
    echo
    read -p "🤔 Do you want to set up systemd service? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        setup_service
    fi
    
    # Test installation
    echo
    test_installation
    
    # Final instructions
    echo
    echo "🎉 Setup completed!"
    echo
    print_success "Setup Summary:"
    echo "  ✅ System dependencies installed"
    echo "  ✅ Python environment created"
    echo "  ✅ Project structure ready"
    echo "  ✅ Configuration created"
    echo
    print_status "Next steps:"
    echo "  1. Activate environment: source venv/bin/activate"
    echo "  2. Start server: python run_ble_system.py server"
    echo "  3. Or test demo: python run_ble_system.py demo"
    echo
    print_status "Service management:"
    echo "  • Manual start: python run_ble_system.py server"
    echo "  • Service start: sudo systemctl start ble-map-server"
    echo "  • View logs: journalctl -u ble-map-server -f"
    echo
    print_status "Troubleshooting:"
    echo "  • Check status: python run_ble_system.py status"
    echo "  • View logs: tail -f logs/system.log"
    echo "  • Reset Bluetooth: sudo systemctl restart bluetooth"
    echo
}

# Run main function
main "$@"