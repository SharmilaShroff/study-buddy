# StudyBuddy Setup Guide

## 1. Open in VS Code

1. Open the `studybuddy` folder in VS Code.
2. Open the integrated terminal.
3. Create a virtual environment.

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

## 2. Install Packages

```powershell
pip install -r requirements.txt
```

## 3. Configure Environment Variables

1. Copy `.env.example` to `.env`.
2. Add your values for:
   - MySQL
   - Gemini API
   - Gmail SMTP

## 4. Setup MySQL

1. Start MySQL server.
2. Create the database and tables with `database/schema.sql`.
3. Example:

```sql
SOURCE database/schema.sql;
```

## 5. API Setup

- Gemini API:
  - Get an API key from Google AI Studio.
  - Paste it into `GEMINI_API_KEY`.
- Gmail SMTP:
  - Turn on Gmail 2-step verification.
  - Generate an App Password.
  - Put the Gmail address in `SMTP_EMAIL`.
  - Put the App Password in `SMTP_PASSWORD`.
- YouTube transcript:
  - `youtube-transcript-api` works for many videos without an API key.

## 6. Run the App

```powershell
streamlit run app.py
```

## 7. Main Flow

1. Sign up or log in.
2. Upload files or paste YouTube/website links.
3. Click `Process Sources`.
4. Select one or more outputs from the choice menu.
5. Click `Generate Selected Outputs`.
6. Export PDF, PPT, or audio as needed.

## 8. Important Note

StudyBuddy does not auto-generate every output. It only generates the options chosen by the user.
