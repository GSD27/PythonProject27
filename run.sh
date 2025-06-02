#!/bin/bash

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
source venv/Scripts/activate

# Install requirements
echo "Installing requirements..."
pip install -r requirements.txt

# Run Django server
echo "Starting Django server..."
python manage.py runserver 