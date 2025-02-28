<div className="report-formatting-section">
  <h3>Report Formatting</h3>
  
  <div className="format-option">
    <label>File Format:</label>
    <select value={fileFormat} onChange={handleFormatChange}>
      <option value="pdf">PDF</option>
      <option value="csv">CSV</option>
      <option value="excel">Excel</option>
      <option value="png">PNG Image</option>
    </select>
  </div>
  
  <div className="format-option">
    <label>Paper Size:</label>
    <select value={paperSize} onChange={handlePaperSizeChange}>
      <option value="letter">Letter</option>
      <option value="legal">Legal</option>
      <option value="a4">A4</option>
      <option value="a3">A3</option>
    </select>
  </div>
  
  <div className="format-option">
    <label>Orientation:</label>
    <select value={orientation} onChange={handleOrientationChange}>
      <option value="portrait">Portrait</option>
      <option value="landscape">Landscape</option>
    </select>
  </div>
  
  <div className="checkbox-option">
    <input 
      type="checkbox" 
      checked={includeFilters} 
      onChange={() => setIncludeFilters(!includeFilters)} 
    />
    <label>Include Filters</label>
  </div>
  
  <div className="checkbox-option">
    <input 
      type="checkbox" 
      checked={includeParameters} 
      onChange={() => setIncludeParameters(!includeParameters)} 
    />
    <label>Include Parameters</label>
  </div>
</div> 