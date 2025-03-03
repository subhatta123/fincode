# Script to fix the schedule type selection in app.py
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the schedule type selection switch statement
start_marker = "switch(this.value) {"
end_marker = "case 'weekly':"

# Find the position of the markers
start_pos = content.find(start_marker)
end_pos = content.find(end_marker, start_pos)

if start_pos != -1 and end_pos != -1:
    # Extract the part before the switch statement
    before = content[:end_pos]
    # Extract the part after the switch statement
    after = content[end_pos:]
    
    # Insert the daily case
    updated_content = before + "case 'daily':\n                                // For daily schedules, we don't need special options\n                                break;\n                            " + after
    
    # Write the updated content back to the file
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print("Successfully added daily schedule case to app.py")
else:
    print("Could not find the switch statement in app.py") 