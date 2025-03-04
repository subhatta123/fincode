import re
import sqlite3

# Read app.py file
with open('app.py', 'r', encoding='utf-8') as file:
    content = file.read()

# Fix 1: Remove the duplicate "Include Data Visualization" and "Limit Number of Rows" sections
# First, identify the duplicate sections
visualization_pattern = re.compile(r'''<div class="form-check mb-3">
                                <input class="form-check-input" type="checkbox" id="include_visualization" name="include_visualization".*?>
                                <label class="form-check-label" for="include_visualization">
                                    Include Data Visualization
                                </label>
                            </div>''', re.DOTALL)

limit_rows_pattern = re.compile(r'''<div class="form-check mb-3">
                                <input class="form-check-input" type="checkbox" id="limitRows" name="limit_rows".*?>
                                <label class="form-check-label" for="limitRows">
                                    Limit Number of Rows
                                </label>
                            </div>

                            <div class="mb-3">
                                <label for="maxRows" class="form-label">Maximum Rows</label>
                                <input type="number" class="form-control" id="maxRows" name="max_rows".*?>
                            </div>''', re.DOTALL)

# Find all matches
visualization_matches = list(visualization_pattern.finditer(content))
limit_rows_matches = list(limit_rows_pattern.finditer(content))

# Only keep the first occurrence of each
if len(visualization_matches) > 1:
    # Remove the second occurrence
    second_vis_match = visualization_matches[1]
    content = content[:second_vis_match.start()] + content[second_vis_match.end():]

if len(limit_rows_matches) > 1:
    # Remove the second occurrence
    second_limit_match = limit_rows_matches[1]
    content = content[:second_limit_match.start()] + content[second_limit_match.end():]

# Fix 2: Print debugging info about dataset columns
debugging_code = '''
    # Add debugging for dataset columns
    print(f"Dataset: {dataset}")
    print(f"Dataset columns: {dataset_columns}")
    if not dataset_columns:
        print("WARNING: No columns found for dataset")
'''

# Add debugging after the dataset_columns retrieval
content = content.replace(
    '''    except Exception as e:
        print(f"Error getting columns for dataset {dataset}: {str(e)}")''',
    '''    except Exception as e:
        print(f"Error getting columns for dataset {dataset}: {str(e)}")''' + debugging_code
)

# Fix 3: Make sure columns show up by default for debugging
content = content.replace(
    '''<div id="columnSelectionDiv" style="display: none;" class="mt-2">''',
    '''<div id="columnSelectionDiv" class="mt-2">'''
)

# Write back to app.py
with open('app.py', 'w', encoding='utf-8') as file:
    file.write(content)

print("Fixed duplicate form elements and added column selection debugging")

# Test database connection to verify columns
try:
    datasets = []
    with sqlite3.connect('data/tableau_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = cursor.fetchall()
        datasets = [table[0] for table in tables]
        
        print(f"Found {len(datasets)} datasets in database: {', '.join(datasets)}")
        
        # Try getting columns for the first dataset as a test
        if datasets:
            test_dataset = datasets[0]
            cursor.execute(f"SELECT * FROM '{test_dataset}' LIMIT 1")
            columns = [description[0] for description in cursor.description]
            print(f"Test dataset '{test_dataset}' has {len(columns)} columns: {', '.join(columns)}")
except Exception as e:
    print(f"Error testing database: {str(e)}") 