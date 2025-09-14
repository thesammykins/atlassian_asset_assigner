#!/usr/bin/env python3

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from jira_assets_client import JiraAssetsClient

def main():
    client = JiraAssetsClient()
    
    print("=== Debugging HW-0001 Asset ===")
    
    try:
        # Get HW-0001
        hw615 = client.get_object_by_key('HW-0001')
        print(f"Asset Key: {hw615.get('objectKey')}")
        print(f"Asset ID: {hw615.get('id')}")
        ot = hw615.get('objectType', {})
        ot_id = ot.get('id')
        print(f"Object Type: {ot.get('name')} (ID: {ot_id}, type: {type(ot_id)})")
        print(f"Full objectType structure: {ot}")
        
        print("\nAll Attributes:")
        for attr in hw615.get('attributes', []):
            attr_name = attr.get('objectTypeAttribute', {}).get('name', 'Unknown')
            attr_value = client.extract_attribute_value(hw615, attr_name)
            print(f"  {attr_name}: {attr_value}")
        
        # Test AQL queries with different variations
        object_type_id = hw615.get('objectType', {}).get('id')
        serial_variations = ['Serial Number', 'SerialNumber', 'Serial_Number', 'serial_number']
        
        print(f"\n=== Testing AQL Queries for Object Type {object_type_id} ===")
        for serial_attr in serial_variations:
            query = f'objectType = {object_type_id} AND "{serial_attr}" = "SERIAL-EXAMPLE-1"'
            print(f"\nTrying: {query}")
            try:
                result = client.find_objects_by_aql(query, limit=5)
                objects = result.get('values', [])
                print(f"  Result: {len(objects)} objects found")
                for obj in objects:
                    print(f"    - {obj.get('objectKey')}")
            except Exception as e:
                print(f"  Error: {e}")
                
        # Try case-insensitive and wildcards
        print(f"\n=== Testing case-insensitive and wildcards ===")
        test_queries = [
            f'objectType = {object_type_id} AND "Serial Number" LIKE "SERIAL-EXAMPLE-1"',
            f'objectType = {object_type_id} AND "Serial Number" ~ "SERIAL-EXAMPLE-1"',
            f'objectType = {object_type_id} AND "Serial Number" LIKE "serial-example-1"',
            f'objectType = {object_type_id} AND "Serial Number" = "serial-example-1"',
            f'Key = "HW-0001"',
            f'objectType = {object_type_id} AND Key = "HW-0001"',
        ]
        
        for query in test_queries:
            print(f"\nTrying: {query}")
            try:
                result = client.find_objects_by_aql(query, limit=5)
                objects = result.get('values', [])
                print(f"  Result: {len(objects)} objects found")
                for obj in objects:
                    print(f"    - {obj.get('objectKey')}")
            except Exception as e:
                print(f"  Error: {e}")
        
        # Test objectType as string
        print(f"\n=== Testing objectType as string ===")
        string_queries = [
            f'objectType = "{object_type_id}" AND Key = "HW-0001"',
            f'objectType = "{object_type_id}" AND "Serial Number" = "SERIAL-EXAMPLE-1"',
            f'objectType = "8" AND Key = "HW-0001"',
            f'objectType = "8" AND "Serial Number" = "SERIAL-EXAMPLE-1"',
        ]
        
        for query in string_queries:
            print(f"\nTrying: {query}")
            try:
                result = client.find_objects_by_aql(query, limit=5)
                objects = result.get('values', [])
                print(f"  Result: {len(objects)} objects found")
                for obj in objects:
                    print(f"    - {obj.get('objectKey')}")
                    # Get the object details to double check serial number
                    if objects:
                        obj_detail = client.get_object_by_key(obj.get('objectKey'))
                        serial = client.extract_attribute_value(obj_detail, 'Serial Number')
                        print(f"      Serial Number in result: {serial}")
            except Exception as e:
                print(f"  Error: {e}")
        
        # Test with parent object type ID
        parent_id = ot.get('parentObjectTypeId')
        if parent_id:
            print(f"\n=== Testing with parent object type {parent_id} ===")
            parent_queries = [
                f'objectType = {parent_id} AND Key = "HW-0001"',
                f'objectType = {parent_id} AND "Serial Number" = "SERIAL-EXAMPLE-1"',
                f'objectType = "{parent_id}" AND Key = "HW-0001"',
                f'objectType = "{parent_id}" AND "Serial Number" = "SERIAL-EXAMPLE-1"',
            ]
            
            for query in parent_queries:
                print(f"\nTrying: {query}")
                try:
                    result = client.find_objects_by_aql(query, limit=5)
                    objects = result.get('values', [])
                    print(f"  Result: {len(objects)} objects found")
                    for obj in objects:
                        print(f"    - {obj.get('objectKey')}")
                        # Get the object details to double check serial number
                        if objects:
                            obj_detail = client.get_object_by_key(obj.get('objectKey'))
                            serial = client.extract_attribute_value(obj_detail, 'Serial Number')
                            print(f"      Serial Number in result: {serial}")
                except Exception as e:
                    print(f"  Error: {e}")
        
        # Try searching for serial number without object type constraint
        print(f"\n=== Testing serial number without object type ===")
        global_queries = [
            f'"Serial Number" = "SERIAL-EXAMPLE-1"',
            f'"Serial Number" LIKE "SERIAL-EXAMPLE-1"',
        ]
        
        for query in global_queries:
            print(f"\nTrying: {query}")
            try:
                result = client.find_objects_by_aql(query, limit=10)
                objects = result.get('values', [])
                print(f"  Result: {len(objects)} objects found")
                for obj in objects:
                    print(f"    - {obj.get('objectKey')} (Type: {obj.get('objectType', {}).get('name', 'Unknown')})")
                    obj_detail = client.get_object_by_key(obj.get('objectKey'))
                    serial = client.extract_attribute_value(obj_detail, 'Serial Number')
                    print(f"      Serial Number: {serial}")
            except Exception as e:
                print(f"  Error: {e}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
