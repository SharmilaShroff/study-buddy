https://study-buddy-ljekjhter6d4dh6kvymbdp.streamlit.app/



# 🎓 StudyBuddy AI — Smart Learning Assistant Platform

An AI-Powered Smart Learning Assistant built with **Streamlit** + **MySQL** + **Google Gemini API**.

## ✨ Features

### 🔐 Authentication
- Secure login with email/password
- Create new account with validation
- Forgot password with **OTP email verification**

### 📊 Dashboard (3-Panel Layout)
- **Left Sidebar**: Upload documents (PDF, DOCX, TXT, PPTX), website links, YouTube links
- **Center**: 8 AI learning tools + question box + YouTube recommendations
- **Right Sidebar**: Quick-access tool icons (open in new pages)

### 🛠 8 Learning Tools
1. **PPT Generator** — Downloadable & editable PPTX presentations
2. **Flashcards** — Interactive flip cards with Q&A
3. **Poster Generator** — Academic poster content
4. **Report Generator** — Formal PDF reports
5. **Mind Map** — Hierarchical concept maps
6. **Video Overview** — Educational video scripts
7. **Quiz Generator** — Interactive MCQ quizzes with scoring
8. **Audio Overview** — Text-to-speech audio summaries

### 🎯 Advanced Tools (Right Sidebar)
- **Exam Question Predictor** — ML-powered exam question prediction from past papers
- **Revision Tool** — Comprehensive revision summaries
- **Learn Together** — Collaborative study rooms with real-time chat
- **Textbook Search** — Search & share textbooks with the community
- **Community** — Twitter-style discussion forum

### 🧠 AI-Powered Features
- **Critical Thinking Mode** — AI analyzes, compares, and explains deeply
- **Student Mode** — Simple, beginner-friendly outputs
- **Developer Mode** — Technical, detailed outputs with API insights

## 🚀 Quick Start

### 1. Set up MySQL
```sql
mysql -u root -p < schema.sql
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your MySQL password, Gemini API key, and SMTP settings
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the app
```bash
python -m streamlit run app.py
```

## 📁 Project Structure
```
studybuddy/
├── app.py                          # Entry point
├── schema.sql                      # MySQL database schema
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment config template
├── app/
│   ├── core/
│   │   ├── config.py               # Settings from .env
│   │   └── database.py             # MySQL connection manager
│   ├── services/
│   │   ├── ai_service.py           # Gemini AI — all generation methods
│   │   ├── auth_service.py         # Login, signup, OTP, password reset
│   │   ├── content_service.py      # PDF/DOCX/YouTube/web extraction
│   │   ├── export_service.py       # PDF/PPTX/audio file export
│   │   ├── recommendation_service.py  # YouTube recommendations
│   │   └── repository.py           # Database CRUD operations
│   ├── ui/
│   │   └── streamlit_app.py        # Complete UI — all pages
│   └── utils/
│       └── helpers.py              # Helper functions
└── exports/                        # Generated files (audio, etc.)
```

## 🔑 Required API Keys
- **Google Gemini API Key** — For all AI features
- **Gmail App Password** — For OTP email (enable 2FA, create app password)
