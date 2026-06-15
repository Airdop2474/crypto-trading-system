#!/usr/bin/env python3
"""
Environment Check Script - Phase 1

Quick check for development environment setup
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def check_python_version():
    """Check Python version"""
    print("\n[1] Checking Python version...")
    version = sys.version_info
    if version.major == 3 and version.minor >= 11:
        print(f"    OK: Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"    FAIL: Python {version.major}.{version.minor}.{version.micro}")
        print(f"    Need Python 3.11+")
        return False


def check_dependencies():
    """Check required packages"""
    print("\n[2] Checking dependencies...")

    required_packages = [
        "ccxt",
        "pandas",
        "numpy",
        "psycopg2",
        "redis",
        "sqlalchemy",
        "dotenv",
        "loguru",
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package if package != "dotenv" else "dotenv")
            print(f"    OK: {package}")
        except ImportError:
            print(f"    MISSING: {package}")
            missing.append(package)

    if missing:
        print(f"\n    Run: pip install -r requirements.txt")
        return False

    return True


def check_env_file():
    """Check .env file"""
    print("\n[3] Checking .env file...")

    env_path = project_root / ".env"
    env_example_path = project_root / ".env.example"

    if not env_path.exists():
        print(f"    MISSING: .env file")
        if env_example_path.exists():
            print(f"    Run: cp .env.example .env")
            print(f"    Then edit .env with actual values")
        return False

    print(f"    OK: .env file exists")
    return True


def check_config():
    """Check configuration"""
    print("\n[4] Checking configuration...")

    try:
        from src.utils.config import config

        print(f"    Environment: {config.ENVIRONMENT}")
        print(f"    Database: {config._mask_url(config.DATABASE_URL)}")
        print(f"    Testnet: {config.BINANCE_TESTNET}")
        print(f"    Live Trading: {config.LIVE_TRADING_ENABLED}")

        # Validate config
        is_valid, errors = config.validate()

        if is_valid:
            print(f"    OK: Config validation passed")
            return True
        else:
            print(f"    WARNING: Config validation issues:")
            for error in errors:
                print(f"      - {error}")
            return "warning"

    except Exception as e:
        print(f"    FAIL: Config load failed: {e}")
        return False


def check_database():
    """Check database connections"""
    print("\n[5] Checking database connections...")

    try:
        from src.utils.database import db

        status = db.test_connection()

        if status["postgres"]:
            print(f"    OK: PostgreSQL connected")
        else:
            print(f"    FAIL: PostgreSQL connection failed")
            print(f"    Run: docker-compose up -d")

        if status["redis"]:
            print(f"    OK: Redis connected")
        else:
            print(f"    FAIL: Redis connection failed")
            print(f"    Run: docker-compose up -d")

        return status["postgres"] and status["redis"]

    except Exception as e:
        print(f"    FAIL: Database check failed: {e}")
        print(f"    Run: docker-compose up -d")
        return False


def check_directories():
    """Check directory structure"""
    print("\n[6] Checking directory structure...")

    required_dirs = [
        "src/data",
        "src/utils",
        "tests/unit",
        "scripts",
        "data",
        "logs",
    ]

    for dir_path in required_dirs:
        full_path = project_root / dir_path
        if full_path.exists():
            print(f"    OK: {dir_path}/")
        else:
            print(f"    INFO: {dir_path}/ (will be created)")

    return True


def main():
    """Main function"""
    print("=" * 60)
    print("Phase 1 Environment Check")
    print("=" * 60)

    results = []

    # Run all checks
    results.append(("Python version", check_python_version()))
    results.append(("Dependencies", check_dependencies()))
    results.append((".env file", check_env_file()))
    results.append(("Configuration", check_config()))
    results.append(("Database", check_database()))
    results.append(("Directories", check_directories()))

    # Summary
    print("\n" + "=" * 60)
    print("Check Results Summary")
    print("=" * 60)

    passed = 0
    failed = 0
    warnings = 0

    for name, result in results:
        if result is True:
            print(f"  OK: {name}")
            passed += 1
        elif result == "warning":
            print(f"  WARNING: {name}")
            warnings += 1
        else:
            print(f"  FAIL: {name}")
            failed += 1

    print("\n" + "=" * 60)

    if failed == 0 and warnings == 0:
        print("SUCCESS: All checks passed! Environment ready!")
        print("\nNext steps:")
        print("  1. Read docs/standards/DATA_QUALITY_STANDARD.md")
        print("  2. Start developing data download module")
        return 0
    elif failed == 0:
        print(f"WARNING: {passed} passed, {warnings} warnings")
        print("\nYou can continue, but please check warnings")
        return 0
    else:
        print(f"FAILED: {failed} failed, {passed} passed")
        print("\nPlease fix failed items before continuing")
        return 1


if __name__ == "__main__":
    sys.exit(main())
