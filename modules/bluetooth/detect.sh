#!/bin/bash

# Bluetooth Module Detection Script
# Checks if bluetooth functionality is available

# Check if bluetoothctl is available
if ! command -v bluetoothctl >/dev/null 2>&1; then
    exit 1
fi

# Check if bluetooth service exists
if ! systemctl list-unit-files bluetooth.service >/dev/null 2>&1; then
    exit 1
fi

# Check if we have bluetooth hardware
if [ ! -d /sys/class/bluetooth ] || [ -z "$(ls -A /sys/class/bluetooth 2>/dev/null)" ]; then
    exit 1
fi

# All checks passed
exit 0