# CoverAgent
An AI-powered web application that generates personalized cover letters from LaTeX resumes and job descriptions.

## Features

- **FastAPI Backend**: Robust API for processing resumes and generating cover letters
- **AI-Powered**: Uses OpenAI GPT-3.5-turbo to extract skills and generate personalized content
- **LaTeX Processing**: Handles LaTeX resume files and compiles cover letters to PDF
- **Modern Frontend**: Clean, responsive HTML interface
- **Containerized**: Full Docker and Docker Compose support
- **No Database**: Temporary file storage for v1 simplicity

## Quick Start

### Prerequisites
- Docker and Docker Compose
- OpenAI API key

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd CoverAgent
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your OpenAI API key
```

3. Run with Docker Compose:
```bash
docker-compose up --build
```

4. Open your browser to `http://localhost:8000`

### Usage

1. Upload a LaTeX (.tex) resume file
2. Enter the company name and role
3. Paste the job description
4. Click "Generate Cover Letter"
5. Download the generated PDF

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Ensure LaTeX is installed (Ubuntu/Debian)
sudo apt-get install texlive-latex-base texlive-latex-recommended texlive-fonts-recommended texlive-latex-extra

# Set environment variables
export OPENAI_API_KEY=your-api-key-here

# Run the application
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

- `GET /`: Serve the frontend application
- `POST /generate-cover-letter`: Generate cover letter from resume and job description
- `GET /health`: Health check endpoint

## Sample Files

A sample LaTeX resume is provided in `templates/sample_resume.tex` for testing.
