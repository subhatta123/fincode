# Script to fix the daily schedule option in the JavaScript switch statement
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the switch statement in the create/schedule form
switch_content = '''            switch(this.value) {
                                case 'one-time':
                                    document.getElementById('oneTimeOptions').classList.add('active');
                                    break;'''
    
new_switch_content = '''            switch(this.value) {
                                case 'one-time':
                                    document.getElementById('oneTimeOptions').classList.add('active');
                                    break;
                                case 'daily':
                                    document.getElementById('dailyOptions').classList.add('active');
                                    break;'''

# Replace the switch statement
updated_content = content.replace(switch_content, new_switch_content)

# Find the switch statement in the edit schedule form as well (if it exists)
edit_switch_content = '''                        switch(this.value) {
                                case 'one-time':
                                    document.getElementById('oneTimeOptions').classList.add('active');
                                    break;'''
    
new_edit_switch_content = '''                        switch(this.value) {
                                case 'one-time':
                                    document.getElementById('oneTimeOptions').classList.add('active');
                                    break;
                                case 'daily':
                                    document.getElementById('dailyOptions').classList.add('active');
                                    break;'''

# Replace the switch statement in the edit form if it exists
updated_content = updated_content.replace(edit_switch_content, new_edit_switch_content)

# Write the updated content back to the file
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(updated_content)

print("Successfully added 'daily' case to the schedule type switch statement in app.py") 