# Colour and Supplier Fields Configuration

## New Environment Variables Added

Add these lines to your `.env` file to configure the new Colour and Supplier fields:

```bash
# New optional fields for asset creation
COLOUR_ATTRIBUTE=Colour
SUPPLIER_ATTRIBUTE=Supplier
```

## Complete .env Template

Your `.env` file should now include these attribute configurations:

```bash
# ... existing configuration ...

# Asset Attribute Names (configure to match your Jira Assets schema)
MODEL_NAME_ATTRIBUTE=Model Name
SERIAL_NUMBER_ATTRIBUTE=Serial Number
INVOICE_NUMBER_ATTRIBUTE=Invoice Number
PURCHASE_DATE_ATTRIBUTE=Purchase Date
COST_ATTRIBUTE=Cost
COLOUR_ATTRIBUTE=Colour
SUPPLIER_ATTRIBUTE=Supplier
```

## New Features Added

### 🎨 Colour Field
- **Type**: Text field
- **Usage**: Optional field in interactive workflow
- **Prompt**: "🎨 Colour (optional, press Enter to skip)"
- **Example**: "Space Grey", "Silver", "Gold"

### 🏢 Supplier Field  
- **Type**: Reference field pointing to Suppliers object type
- **Usage**: Optional field with intelligent supplier management
- **Features**:
  - Lists existing suppliers from Suppliers object type
  - Allows selection by number or name
  - **Automatically creates new suppliers** if they don't exist
  - Skip functionality for optional use
- **Prompt**: Shows available suppliers with option to enter new ones
- **Example**: "Apple", "Dell Technologies", "JB HiFi" (auto-created)

### Interactive Workflow Updated

The asset creation workflow (`--new` command) now includes:

1. 🏷️ Serial number entry
2. 📦 Model selection (25+ options)
3. 📊 Status selection (8 options)  
4. 🌍 Remote user flag
5. 🧾 Invoice Number (optional)
6. 📅 Purchase Date (optional)
7. 💰 Cost (optional)
8. 🎨 **Colour (optional)** ✅ NEW
9. 🏢 **Supplier (optional)** ✅ NEW with auto-creation

All optional fields can be skipped by pressing Enter, maintaining workflow flexibility.

## Technical Implementation

### Auto-Creation Feature
When a custom supplier name is entered:
1. System first checks if supplier exists in Suppliers object type
2. If not found, automatically creates new supplier object
3. Returns object key for proper reference linking
4. New supplier immediately available for future asset creation

This eliminates the need for manual supplier setup before asset creation.

## Example Usage

```bash
# Start interactive asset creation
python3 src/main.py --new --execute

# Follow prompts including new colour and supplier fields
# Suppliers will be auto-created if they don't exist
```