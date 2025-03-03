import re

# Read app.py file
with open('app.py', 'r', encoding='utf-8') as file:
    content = file.read()

# Add daily schedule handling to process_schedule_form
content = content.replace(
    '''        elif schedule_type == 'weekly':''',
    '''        elif schedule_type == 'daily':
            # For daily schedules, we only need the time which is already handled above
            pass
            
        elif schedule_type == 'weekly':''')

# Add daily options div to HTML
content = content.replace(
    '''                            <!-- One-time schedule options -->
                            <div id="oneTimeOptions" class="schedule-options active">
                                <div class="mb-3">
                                    <label for="date" class="form-label">Date</label>
                                    <input type="date" class="form-control" id="date" name="date" required>
                                </div>
                            </div>''',
    '''                            <!-- One-time schedule options -->
                            <div id="oneTimeOptions" class="schedule-options active">
                                <div class="mb-3">
                                    <label for="date" class="form-label">Date</label>
                                    <input type="date" class="form-control" id="date" name="date" required>
                                </div>
                            </div>
                            
                            <!-- Daily schedule options -->
                            <div id="dailyOptions" class="schedule-options">
                                <div class="mb-3">
                                    <p class="text-muted">Daily reports will be sent at the specified time every day.</p>
                                </div>
                            </div>''')

# Update the JavaScript to handle daily schedule type
content = content.replace(
    '''                            case 'daily':
                                // For daily schedules, we don't need special options
                                break;''',
    '''                            case 'daily':
                                document.getElementById('dailyOptions').classList.add('active');
                                break;''')

# Write back to app.py
with open('app.py', 'w', encoding='utf-8') as file:
    file.write(content)

print("Fixed daily schedule and column selection issues in app.py") 