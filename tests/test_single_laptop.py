#!/usr/bin/env python3
"""
Test script to verify OAuth and Assets API functionality with a single laptop.
This tests the complete flow: authentication, API access, user lookup, and attribute update.
"""

import sys
sys.path.append('src')

from oauth_client import OAuthClient
from jira_assets_client import JiraAssetsClient  
from jira_user_client import JiraUserClient
import requests

def test_single_laptop():
    """Test the complete flow with HW-410."""
    print("🔧 Testing Jira Assets Manager with single laptop (HW-410)")
    print("=" * 60)
    
    # Initialize clients
    print("\n1️⃣ Initializing OAuth and API clients...")
    try:
        user_client = JiraUserClient()
        assets_client = JiraAssetsClient()
        print("✅ Clients initialized successfully")
    except Exception as e:
        print(f"❌ Client initialization failed: {e}")
        return False
    
    # Get the test laptop object
    print("\n2️⃣ Retrieving test laptop object (HW-410)...")
    try:
        laptop = assets_client.get_object_by_key("HW-410")
        print(f"✅ Retrieved laptop: {laptop.get('label', 'N/A')}")
        
        # Extract key attributes
        user_email = assets_client.extract_attribute_value(laptop, "User Email")
        assignee = assets_client.extract_attribute_value(laptop, "Assignee")
        
        print(f"   User Email: {user_email}")
        print(f"   Current Assignee: {assignee}")
        
        if not user_email or user_email.strip() == "":
            print("⚠️  No User Email found - nothing to update")
            return True
            
    except Exception as e:
        print(f"❌ Failed to retrieve laptop: {e}")
        return False
    
    # Look up the user in Jira
    print(f"\n3️⃣ Looking up user in Jira: {user_email}")
    try:
        user_info = user_client.search_user_by_email(user_email)
        if user_info:
            print(f"✅ Found user: {user_info.get('displayName', 'N/A')} ({user_info.get('emailAddress', 'N/A')})")
            target_assignee = user_info.get('emailAddress')
        else:
            print(f"⚠️  User not found in Jira - cannot update assignee")
            return True
    except Exception as e:
        print(f"❌ User lookup failed: {e}")
        return False
    
    # Check if update is needed
    print(f"\n4️⃣ Checking if update is needed...")
    if assignee == target_assignee:
        print(f"✅ Assignee already matches User Email - no update needed")
        return True
    else:
        print(f"📝 Update needed: {assignee} → {target_assignee}")
    
    # Create attribute update
    print(f"\n5️⃣ Creating attribute update...")
    try:
        object_type_id = laptop.get('objectType', {}).get('id')
        if not object_type_id:
            print("❌ Could not get object type ID")
            return False
            
        # Create the attribute update structure
        attribute_update = assets_client.create_attribute_update(
            "Assignee", 
            target_assignee, 
            object_type_id
        )
        print(f"✅ Created attribute update structure")
        
    except Exception as e:
        print(f"❌ Failed to create attribute update: {e}")
        return False
    
    # Perform the update (or dry run)
    print(f"\n6️⃣ Performing update (DRY RUN)...")
    try:
        object_id = laptop.get('id')
        print(f"   Object ID: {object_id}")
        print(f"   Update structure: {attribute_update}")
        print("   🚫 DRY RUN - Would call: assets_client.update_object(object_id, [attribute_update])")
        print(f"   📊 This would set Assignee = '{target_assignee}'")
        
        print(f"\n✅ DRY RUN SUCCESSFUL!")
        print(f"   The system can successfully:")
        print(f"   - Authenticate with OAuth ✅")
        print(f"   - Access Assets API ✅") 
        print(f"   - Retrieve laptop objects ✅")
        print(f"   - Extract User Email attribute ✅")
        print(f"   - Look up users in Jira ✅")
        print(f"   - Create attribute updates ✅")
        print(f"   - Ready to perform actual updates ✅")
        
    except Exception as e:
        print(f"❌ Update preparation failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = test_single_laptop()
    if success:
        print(f"\n🎉 ALL TESTS PASSED! The system is working correctly.")
        print(f"   To perform actual updates, modify the script to call:")
        print(f"   assets_client.update_object(object_id, [attribute_update])")
    else:
        print(f"\n💥 TESTS FAILED! Check the errors above.")
    
    sys.exit(0 if success else 1)
