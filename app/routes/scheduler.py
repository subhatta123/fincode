from flask import Blueprint, request, jsonify

# Create a blueprint
scheduler_bp = Blueprint('scheduler', __name__)

@scheduler_bp.route('/api/schedule/create', methods=['POST'])
def create_schedule():
    data = request.json
    
    # Get basic schedule info
    schedule_name = data.get('name')
    schedule_frequency = data.get('frequency')
    # ...other scheduling parameters
    
    # Get report formatting options (restore this section)
    report_format = data.get('format', 'pdf')
    paper_size = data.get('paperSize', 'letter')
    orientation = data.get('orientation', 'portrait')
    include_filters = data.get('includeFilters', False)
    include_parameters = data.get('includeParameters', False)
    
    # Create schedule with formatting options
    schedule = {
        'name': schedule_name,
        'frequency': schedule_frequency,
        # Add formatting options
        'formatting': {
            'format': report_format,
            'paperSize': paper_size,
            'orientation': orientation,
            'includeFilters': include_filters,
            'includeParameters': include_parameters
        }
    }
    
    # Save schedule to database
    # ...
    
    return jsonify({'success': True, 'schedule': schedule}) 