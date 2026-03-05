#!/bin/bash
# Script to run property-based tests for task 1.1

echo "Running Property-Based Tests for Bot Detection and Data Model Validation"
echo "=========================================================================="
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run property tests for data models
echo "1. Running data model property tests..."
python -m pytest tests/unit/test_data_models.py -v -m property --tb=short

echo ""
echo "2. Running bot detection property tests..."
python -m pytest tests/unit/test_bot_detection_properties.py -v -m property --tb=short

echo ""
echo "=========================================================================="
echo "Property-based tests completed!"
