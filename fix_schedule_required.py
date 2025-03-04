# Script to fix the required attribute on the date input that may prevent form submission
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the one-time date input with required attribute
date_input = '''<input type="date" class="form-control" id="date" name="date" required>'''
fixed_date_input = '''<input type="date" class="form-control" id="date" name="date" data-required="one-time">'''

# Replace the input to use data-required attribute instead of required
updated_content = content.replace(date_input, fixed_date_input)

# Now add JavaScript to handle the conditional validation
js_validation = '''
                    // Add conditional validation for date input based on schedule type
                    const dateInput = document.getElementById('date');
                    scheduleType.addEventListener('change', function() {
                        if (this.value === 'one-time') {
                            dateInput.setAttribute('required', '');
                        } else {
                            dateInput.removeAttribute('required');
                        }
                    });
'''

# Find the position to insert this code - after the schedule type switch statement
insert_marker = '''                        });
                        
                        // Monthly day option'''

updated_content = updated_content.replace(insert_marker, js_validation + insert_marker)

# Write the updated content back to the file
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(updated_content)

print("Successfully modified date input to use conditional required attribute") 