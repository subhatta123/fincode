# Tableau Data Reporter

A Flask application for scheduling and generating reports from Tableau data sources.

## Features

- Connect to Tableau Server and download data
- Schedule report generation (One-time, Daily, Weekly, Monthly)
- Send reports via Email and WhatsApp
- Customize report formats and styles
- User Management with different permission levels
- Data visualization and analysis

## Deployment on Render

This application is configured for easy deployment on Render.com. 

### Automated Deployment

1. Fork this repository to your GitHub account
2. Sign up for a Render account at https://render.com
3. Create a new Web Service in Render
4. Connect your GitHub account and select this repository
5. Render will automatically detect the configuration in `render.yaml`
6. Configure the required environment variables (see below)
7. Deploy the service

### Environment Variables

Set the following environment variables in Render dashboard:

- `FLASK_SECRET_KEY`: A secret key for session management (generated automatically by Render)
- `SMTP_SERVER`: SMTP server for sending emails (e.g., smtp.gmail.com)
- `SMTP_PORT`: SMTP port (typically 587 for TLS)
- `SENDER_EMAIL`: Email address used for sending reports
- `SENDER_PASSWORD`: Password for the email account
- `TWILIO_ACCOUNT_SID`: Twilio account SID (for WhatsApp functionality)
- `TWILIO_AUTH_TOKEN`: Twilio auth token
- `TWILIO_WHATSAPP_NUMBER`: Twilio WhatsApp number
- `BASE_URL`: Set to your Render service URL (automatically set by Render)
- `RENDER`: Set to 'true' (set automatically by Render)

### Manual Setup

If you prefer to configure the service manually:

1. Build Command: `pip install -r requirements.txt`
2. Start Command: `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 180`
3. Set Python version to 3.9.0

## Local Development

1. Clone the repository
2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Set up environment variables:
   ```
   cp .env.example .env
   # Edit .env with your values
   ```
5. Run the application:
   ```
   python app.py
   ```

## License

See the [LICENSE](LICENSE) file for details. 