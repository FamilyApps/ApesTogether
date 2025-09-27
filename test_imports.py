#!/usr/bin/env python3
"""
Test script to verify all imports work correctly
"""

def test_portfolio_performance_imports():
    """Test that portfolio_performance.py imports work"""
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        print("✅ PortfolioPerformanceCalculator import successful")
        
        # Test instantiation
        calculator = PortfolioPerformanceCalculator()
        print("✅ PortfolioPerformanceCalculator instantiation successful")
        
        return True
    except Exception as e:
        print(f"❌ PortfolioPerformanceCalculator import/instantiation failed: {str(e)}")
        return False

def test_models_imports():
    """Test that models imports work"""
    try:
        from models import db, MarketData, PortfolioSnapshot, User, Stock
        print("✅ Models import successful")
        return True
    except Exception as e:
        print(f"❌ Models import failed: {str(e)}")
        return False

def test_typing_imports():
    """Test typing imports"""
    try:
        from typing import Dict, List
        print("✅ Typing imports successful")
        return True
    except Exception as e:
        print(f"❌ Typing imports failed: {str(e)}")
        return False

if __name__ == "__main__":
    print("🔍 Testing imports...")
    
    success = True
    success &= test_typing_imports()
    success &= test_models_imports()
    success &= test_portfolio_performance_imports()
    
    if success:
        print("\n✅ All imports working correctly!")
    else:
        print("\n❌ Some imports failed!")
