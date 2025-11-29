#!/usr/bin/env python3
"""
Simple test script to verify MongoDB connection and basic functionality
"""
import sys
import os
import asyncio
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.mongo import get_db, check_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_mongodb():
    """Test MongoDB connection and basic operations"""
    
    print("🧪 Testing MongoDB connection...")
    
    # Test connection
    is_connected = await check_connection()
    if not is_connected:
        print("❌ MongoDB connection failed!")
        return False
    
    print("✅ MongoDB connection successful!")
    
    # Test basic operations
    try:
        db = await get_db()
        
        # Test insert
        test_doc = {
            "test": True,
            "timestamp": "2023-01-01T00:00:00Z",
            "message": "Test document"
        }
        
        result = await db.test_collection.insert_one(test_doc)
        print(f"✅ Insert test successful! ID: {result.inserted_id}")
        
        # Test find
        found_doc = await db.test_collection.find_one({"_id": result.inserted_id})
        if found_doc:
            print("✅ Find test successful!")
        else:
            print("❌ Find test failed!")
            return False
            
        # Test delete (cleanup)
        await db.test_collection.delete_one({"_id": result.inserted_id})
        print("✅ Delete test successful!")
        
        # Check collections exist
        collections = await db.list_collection_names()
        expected_collections = ["access_logs", "service_logs", "users", "config"]
        
        for collection in expected_collections:
            if collection in collections:
                print(f"✅ Collection '{collection}' exists")
            else:
                print(f"⚠️  Collection '{collection}' not found")
        
        return True
        
    except Exception as e:
        print(f"❌ Database operations failed: {e}")
        return False

if __name__ == "__main__":
    # Load environment variables
    if os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value
    
    success = asyncio.run(test_mongodb())
    sys.exit(0 if success else 1)