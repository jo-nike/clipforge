#!/bin/bash
# Linting script for Python project

echo "🔍 Running Python linting tools..."

echo "1. 🎨 Black (Code Formatting)"
black . --line-length=100 --check --diff

echo -e "\n2. 📏 Flake8 (Style Guide)"
flake8 .

echo -e "\n3. 🔤 isort (Import Sorting)"
isort . --check-only --diff

echo -e "\n4. 🛡️ Bandit (Security)"
bandit -r . -x test_*.py --skip B101,B105,B404,B603,B106,B110

echo -e "\n5. 🏷️ MyPy (Type Checking)"
mypy . --ignore-missing-imports --exclude tests

echo -e "\n✅ Linting complete!"