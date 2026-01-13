# How to Run the Medical Health Assistant Backend

## ✅ All Dependencies Installed!

All required packages have been installed successfully. You can now start the med backend.

## 🚀 Quick Start

### Option 1: Run Directly (Recommended)
Open a PowerShell terminal and run:

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

**Keep this terminal open** - the med backend must stay running!

### Option 2: Use the Batch Script
Double-click `start_med_backend.bat` in the `med/backend` folder.

## ✅ Verify It's Working

Open another terminal and test:
```powershell
curl http://localhost:8001/
```

You should see:
```json
{"status":"online","service":"Multilingual Voice Chatbot","version":"1.0.0"}
```

## 📋 Complete Setup Checklist

You need **3 terminals running**:

1. **Main Backend** (Port 8000)
   ```powershell
   cd "C:\Users\Kartik Malik\medico\backend"
   python main.py
   ```

2. **Med Backend** (Port 8001) ← **This is what you just set up!**
   ```powershell
   cd "C:\Users\Kartik Malik\medico\med\backend"
   python main.py
   ```

3. **Frontend** (Port 3000)
   ```powershell
   cd "C:\Users\Kartik Malik\medico\frontend"
   npm start
   ```

## 🔧 Troubleshooting

- **"Port 8001 already in use"**: Another process is using port 8001. Stop it first.
- **"OPENAI_API_KEY not found"**: Make sure `.env` file exists in `med/backend/` with your API key.
- **"Module not found"**: Run `pip install -r requirements.txt` again.

## 🎉 You're All Set!

Once all 3 services are running, you can:
1. Open http://localhost:3000 in your browser
2. Click "Medical Health Assistant" in the sidebar
3. Start chatting with the medical AI assistant!






