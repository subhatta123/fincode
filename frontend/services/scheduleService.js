const createSchedule = async (scheduleData) => {
  // Make sure formatting options are included in the request
  const payload = {
    name: scheduleData.name,
    frequency: scheduleData.frequency,
    // Include formatting options
    format: scheduleData.fileFormat,
    paperSize: scheduleData.paperSize,
    orientation: scheduleData.orientation,
    includeFilters: scheduleData.includeFilters,
    includeParameters: scheduleData.includeParameters
  };
  
  try {
    const response = await fetch('/api/schedule/create', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    
    return await response.json();
  } catch (error) {
    console.error('Error creating schedule:', error);
    throw error;
  }
}; 