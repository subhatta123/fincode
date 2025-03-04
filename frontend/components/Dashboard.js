const handleScheduleClick = () => {
  // Set up the state for formatting options
  setShowScheduleModal(true);
  setShowFormatOptions(true); // Make sure this is set to true
  
  // Initialize default format options
  setFileFormat('pdf');
  setPaperSize('letter');
  setOrientation('portrait');
  setIncludeFilters(true);
  setIncludeParameters(true);
}; 