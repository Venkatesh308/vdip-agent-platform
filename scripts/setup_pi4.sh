#!/bin/bash
set -e
echo "-> Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y can-utils libopenblas-dev cmake build-essential
echo "-> Enabling SPI for MCP2515..."
sudo raspi-config nonint do_spi 0
if ! grep -q "mcp2515" /boot/config.txt; then
  echo "dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25" | sudo tee -a /boot/config.txt
  echo "dtoverlay=spi-bcm2835-overlay" | sudo tee -a /boot/config.txt
fi
echo "-> Installing Python packages..."
pip install -r requirements.txt --break-system-packages
echo "Done! Reboot to activate CAN interface."
