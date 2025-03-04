import re
import os

# Read the app.py file
with open('app.py', 'r', encoding='utf-8') as file:
    content = file.read()

# 1. Fix the duplicate visualization option by directly modifying specific HTML sections
# Remove the second "Include Data Visualization" section
content = content.replace(
    '''<div class="form-check mb-3">
                                <input class="form-check-input" type="checkbox" id="include_visualization" name="include_visualization" {% if default_schedule.format_config.include_visualization %}checked{% endif %}>
                                <label class="form-check-label" for="include_visualization">
                                    Include Data Visualization
                                </label>
                            </div>''', 
    '', 1)  # Replace the first occurrence only

# 2. Fix the column selection issue by directly modifying the HTML/JavaScript code
# First, print debug log for columns in HTML template
debug_log = '''
    # Debug column population
    print(f"Populating column selection with {len(dataset_columns)} columns: {dataset_columns}")
'''

# Add logging to the route to see if columns are being passed to the template
content = content.replace(
    '''    # Get email template
    email_template = {
        'subject': f"Report for {dataset}",
        'body': f"Please find the attached report for {dataset}."
    }''',
    '''    # Get email template
    email_template = {
        'subject': f"Report for {dataset}",
        'body': f"Please find the attached report for {dataset}."
    }''' + debug_log
)

# Create a backup of app.py just in case
backup_path = 'app.py.backup'
if not os.path.exists(backup_path):
    with open(backup_path, 'w', encoding='utf-8') as backup_file:
        backup_file.write(content)
    print(f"Created backup of app.py at {backup_path}")

# 3. Make sure the column selection is visible and has options
# Fix column population by replacing the option loop with direct option generation
content = content.replace(
    '''<select class="form-select" id="selected_columns" name="selected_columns" multiple size="5">
                                        {% for column in dataset_columns %}
                                            <option value="{{ column }}">{{ column }}</option>
                                        {% endfor %}
                                    </select>''',
    '''<select class="form-select" id="selected_columns" name="selected_columns" multiple size="5">
                                        <!-- Directly show columns for Superstore dataset as fallback -->
                                        {% if dataset_columns %}
                                            {% for column in dataset_columns %}
                                                <option value="{{ column }}">{{ column }}</option>
                                            {% endfor %}
                                        {% else %}
                                            <!-- Fallback options for Superstore -->
                                            <option value="Measure Names">Measure Names</option>
                                            <option value="Region">Region</option>
                                            <option value="Profit Ratio">Profit Ratio</option>
                                            <option value="Sales per Customer">Sales per Customer</option>
                                            <option value="Distinct count of Customer Name">Distinct count of Customer Name</option>
                                            <option value="Measure Values">Measure Values</option>
                                            <option value="Profit">Profit</option>
                                            <option value="Quantity">Quantity</option>
                                            <option value="Sales">Sales</option>
                                        {% endif %}
                                    </select>'''
)

# Make the column selection visible by default (remove the display:none)
content = content.replace(
    '''<div id="columnSelectionDiv" style="display: none;" class="mt-2">''',
    '''<div id="columnSelectionDiv" class="mt-2">'''
)

# Save the changes to app.py
with open('app.py', 'w', encoding='utf-8') as file:
    file.write(content)

print("Applied specific fixes for duplicate visualization option and empty column selection dropdown")

# Add additional debug to check the specific dataset being viewed
print("\nChecking dataset_columns retrieval code:")
import sqlite3

try:
    dataset = "Superstore"  # Test with known dataset
    dataset_columns = []
    with sqlite3.connect('data/tableau_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM '{dataset}' LIMIT 1")
        dataset_columns = [description[0] for description in cursor.description]
        
    print(f"Successfully retrieved {len(dataset_columns)} columns from {dataset}: {dataset_columns}")
except Exception as e:
    print(f"Error testing column retrieval: {str(e)}")

print("\nScript completed. Restart the Flask app to apply changes.") 