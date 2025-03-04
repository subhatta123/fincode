# Script to fix the weekly days validation to only apply for weekly schedules
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the form validation code for weekly schedules
weekly_validation = '''                        // For weekly schedules, validate days
                        if (scheduleType.value === 'weekly') {
                            const days = document.querySelectorAll('input[name="days"]:checked');
                            if (days.length === 0) {
                                e.preventDefault();
                                alert('Please select at least one day of the week');
                                return false;
                            }
                        }'''

# Make sure it exists before trying to modify
if weekly_validation in content:
    print("Found weekly validation code")
else:
    print("Could not find weekly validation code - checking for variations")
    # Try a different indentation or formatting
    weekly_validation = content[content.find("// For weekly schedules"):content.find("return true;")]
    if weekly_validation:
        print("Found weekly validation with different formatting")
    else:
        print("Could not find weekly validation code at all")
        exit(1)

# Write the updated content back to the file - the validation code is already correct
# but let's ensure the HTML has proper handling of weeklyOptions visibility
# Update the JavaScript for scheduleType change to make sure it shows/hides options properly

# Find the scheduleType change handler
schedule_type_handler = '''                    scheduleType.addEventListener('change', function() {
                        scheduleOptions.forEach(option => option.classList.remove('active'));
                        
                        switch(this.value) {
                            case 'one-time':
                                document.getElementById('oneTimeOptions').classList.add('active');
                                break;
                            case 'daily':
                                document.getElementById('dailyOptions').classList.add('active');
                                break;
                            case 'weekly':
                                document.getElementById('weeklyOptions').classList.add('active');
                                break;
                            case 'monthly':
                                document.getElementById('monthlyOptions').classList.add('active');
                                break;
                        }
                    });'''

# Make sure the schedule type handler correctly shows all option divs
if schedule_type_handler in content:
    print("Found schedule type handler, looks good!")
else:
    print("Schedule type handler not found or has different formatting")
    # Try to detect the switch statement for scheduling options
    switch_start = content.find("switch(this.value)")
    if switch_start > 0:
        switch_end = content.find("break;", content.find("case 'monthly'")) + 15
        current_handler = content[switch_start-50:switch_end+50]
        print(f"Current handler looks like:\n{current_handler}")
        
        # Check if it includes daily case
        if "case 'daily':" not in current_handler:
            print("Daily case missing in switch statement!")
            fixed_handler = current_handler.replace(
                "case 'one-time':",
                "case 'one-time':\n                                document.getElementById('oneTimeOptions').classList.add('active');\n                                break;\n                            case 'daily':\n                                document.getElementById('dailyOptions').classList.add('active');"
            )
            updated_content = content.replace(current_handler, fixed_handler)
            
            # Write the updated content back to the file
            with open('app.py', 'w', encoding='utf-8') as f:
                f.write(updated_content)
            print("Added daily case to switch statement")
        else:
            print("Daily case already exists in switch statement")
    else:
        print("Could not find switch statement for schedule types")

print("Schedule validation check completed") 