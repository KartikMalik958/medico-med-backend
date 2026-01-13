# Starting the Medical Health Assistant Backend

## Quick Start

1. **Install Dependencies** (if not already done):
   ```powershell
   cd "C:\Users\Kartik Malik\medico\med\backend"
   pip install -r requirements.txt
   ```
   This may take a few minutes. Wait for it to complete.

2. **Verify .env file exists**:
   The .env file should have been copied from the main backend. If not, create it with:
   ```env
   OPENAI_API_KEY=your_openai_api_key_here
   CORS_ORIGINS=http://localhost:3000
   BACKEND_PORT=8001
   ```

3. **Start the Med Backend**:
   ```powershell
   cd "C:\Users\Kartik Malik\medico\med\backend"
   python main.py
   ```
   
   You should see:
   ```
   INFO:     Started server process
   INFO:     Waiting for application startup.
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://0.0.0.0:8001
   ```

4. **Keep this terminal open** - the med backend must stay running.

5. **Test it's working**:
   Open another terminal and run:
   ```powershell
   curl http://localhost:8001/
   ```
   You should see: `{"status":"online","service":"Multilingual Voice Chatbot","version":"1.0.0"}`

## Troubleshooting

- **"ModuleNotFoundError"**: Run `pip install -r requirements.txt` again
- **"OPENAI_API_KEY not found"**: Check that .env file exists and has the API key
- **"Port 8001 already in use"**: Another process is using port 8001, stop it first






