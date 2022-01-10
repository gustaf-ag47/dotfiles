#!/bin/bash

if command -v acpi >/dev/null 2>&1; then
	acpi -b | grep "Battery 0:" | awk '{print $4 " " $5}' | tr -d ','
else
	echo "acpi not installed"
fi
