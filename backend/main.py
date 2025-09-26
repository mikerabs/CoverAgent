import os
import tempfile
import subprocess
from pathlib import Path
from typing import List
import aiofiles
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="CoverAgent", description="Generate custom cover letters from resumes and job descriptions")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Configure OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Ensure temp directories exist
os.makedirs("temp_files", exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the frontend HTML page"""
    try:
        async with aiofiles.open("frontend/index.html", mode='r') as f:
            content = await f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Frontend not found</h1>", status_code=404)

async def extract_skills_from_jd(job_description: str) -> List[str]:
    """Extract 3-5 key skills from job description using OpenAI"""
    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = f"""
        Analyze the following job description and extract 3-5 most important technical skills or qualifications required:

        Job Description:
        {job_description}

        Return only a list of skills, one per line, without bullet points or numbers.
        Focus on specific technical skills, tools, or qualifications mentioned.
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3
        )
        
        skills_text = response.choices[0].message.content.strip()
        skills = [skill.strip() for skill in skills_text.split('\n') if skill.strip()]
        return skills[:5]  # Limit to 5 skills max
        
    except Exception as e:
        print(f"Error extracting skills: {e}")
        return ["Python", "Problem Solving", "Communication"]  # Fallback skills

async def generate_bullet_points(resume_content: str, skills: List[str], job_description: str) -> List[str]:
    """Generate resume-grounded bullet points using OpenAI"""
    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = f"""
        Based on the resume content below and the required skills, generate 3-4 compelling bullet points for a cover letter.
        Each bullet point should:
        1. Highlight relevant experience from the resume
        2. Connect to one of the required skills
        3. Be specific and quantifiable when possible
        4. Be written in first person
        5. Start with an action verb

        Resume Content:
        {resume_content}

        Required Skills:
        {', '.join(skills)}

        Job Description Context:
        {job_description[:500]}...

        Generate bullet points that demonstrate how the candidate's background aligns with the job requirements:
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.5
        )
        
        bullet_text = response.choices[0].message.content.strip()
        bullets = [bullet.strip() for bullet in bullet_text.split('\n') if bullet.strip() and not bullet.strip().startswith('#')]
        return bullets[:4]  # Limit to 4 bullet points
        
    except Exception as e:
        print(f"Error generating bullet points: {e}")
        return [
            "I bring strong technical expertise relevant to this position",
            "My experience aligns well with your team's requirements",
            "I have successfully delivered projects using similar technologies"
        ]

def create_cover_letter_latex(company: str, role: str, bullet_points: List[str]) -> str:
    """Create LaTeX cover letter template with injected content"""
    
    bullets_latex = "\n".join([f"\\item {bullet}" for bullet in bullet_points])
    
    latex_template = f"""\\documentclass[11pt,letterpaper]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{enumitem}}
\\usepackage{{parskip}}

\\begin{{document}}

\\noindent
\\today

\\vspace{{1em}}

\\noindent
Hiring Manager \\\\
{company} \\\\

\\vspace{{1em}}

\\noindent
Dear Hiring Manager,

I am writing to express my strong interest in the {role} position at {company}. After reviewing the job description, I am excited about the opportunity to contribute to your team and believe my background aligns well with your requirements.

\\begin{{itemize}}[leftmargin=*]
{bullets_latex}
\\end{{itemize}}

I am particularly drawn to {company} because of your reputation for innovation and excellence. I would welcome the opportunity to discuss how my experience and passion can contribute to your team's continued success.

Thank you for considering my application. I look forward to hearing from you soon.

\\vspace{{1em}}

\\noindent
Sincerely, \\\\
[Your Name]

\\end{{document}}"""

    return latex_template

async def compile_latex_to_pdf(latex_content: str, output_dir: str) -> str:
    """Compile LaTeX content to PDF"""
    
    # Create temporary LaTeX file
    tex_file = os.path.join(output_dir, "cover_letter.tex")
    pdf_file = os.path.join(output_dir, "cover_letter.pdf")
    
    # Write LaTeX content to file
    async with aiofiles.open(tex_file, mode='w') as f:
        await f.write(latex_content)
    
    try:
        # Compile LaTeX to PDF using pdflatex
        process = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-output-directory", output_dir, tex_file],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if process.returncode != 0:
            print(f"LaTeX compilation error: {process.stderr}")
            raise HTTPException(status_code=500, detail="Failed to compile LaTeX to PDF")
        
        if not os.path.exists(pdf_file):
            raise HTTPException(status_code=500, detail="PDF file was not generated")
            
        return pdf_file
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="LaTeX compilation timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="pdflatex not found. Please install LaTeX.")

@app.post("/generate-cover-letter")
async def generate_cover_letter(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
    company: str = Form(...),
    role: str = Form(...)
):
    """Main endpoint to generate cover letter"""
    
    # Validate file type
    if not resume.filename.endswith('.tex'):
        raise HTTPException(status_code=400, detail="Resume must be a .tex file")
    
    # Create temporary directory for this request
    with tempfile.TemporaryDirectory(dir="temp_files") as temp_dir:
        try:
            # Save uploaded resume
            resume_path = os.path.join(temp_dir, resume.filename)
            async with aiofiles.open(resume_path, 'wb') as f:
                content = await resume.read()
                await f.write(content)
            
            # Read resume content
            async with aiofiles.open(resume_path, 'r', encoding='utf-8') as f:
                resume_content = await f.read()
            
            # Extract skills from job description
            skills = await extract_skills_from_jd(job_description)
            
            # Generate bullet points
            bullet_points = await generate_bullet_points(resume_content, skills, job_description)
            
            # Create cover letter LaTeX
            latex_content = create_cover_letter_latex(company, role, bullet_points)
            
            # Compile to PDF
            pdf_path = await compile_latex_to_pdf(latex_content, temp_dir)
            
            # Return PDF file
            return FileResponse(
                pdf_path,
                media_type="application/pdf",
                filename=f"cover_letter_{company}_{role}.pdf"
            )
            
        except Exception as e:
            print(f"Error generating cover letter: {e}")
            raise HTTPException(status_code=500, detail=f"Error generating cover letter: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)