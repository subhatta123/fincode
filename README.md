# Tableau Data Reporter

A Streamlit-based web application for analyzing and reporting Tableau data.

## Features

- Connect to Tableau Server and download data
- Analyze datasets with natural language questions
- Schedule automated reports
- Support for email and WhatsApp notifications
- Interactive data visualizations
- User management with different permission levels

## Requirements

- Python 3.7+
- Streamlit
- Pandas
- Plotly
- Tableau Server Client
- OpenAI API (for Q&A functionality)
- SQLite3

## Installation

1. Clone the repository:
```bash
git clone https://github.com/subhatta123/fincode.git
cd fincode
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
OPENAI_API_KEY=your_openai_api_key
SMTP_SERVER=your_smtp_server
SMTP_PORT=your_smtp_port
SENDER_EMAIL=your_sender_email
SENDER_PASSWORD=your_sender_password
```

## Usage

Run the application:
```bash
streamlit run tableau_streamlit_app.py
```

## License

MIT License 