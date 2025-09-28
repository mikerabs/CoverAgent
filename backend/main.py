import os
import re
import tempfile
import subprocess
from pathlib import Path
from typing import List
import uuid
import aiofiles
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
#openai.api_key = os.getenv("OPENAI_API_KEY")

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

async def parse_resume_sections(resume_content: str) -> str:
    """
    Parse a LaTeX resume file and return only the relevant
    information from Professional Experience and Projects sections.
    """
    content = resume_content

    # Regex patterns for your custom resume style
    patterns = [
        r'\\begin{rSection}{EMPLOYMENT HISTORY}(.*?)\\end{rSection}',
        r'\\begin{rSection}{PROJECTS}(.*?)\\end{rSection}',
        r'\\begin{rSection}{Athletics}(.*?)\\end{rSection}'
    ]

    extracted_sections = []
    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            section_text = match.group(1).strip()
            # Clean LaTeX formatting to reduce token usage
            section_text = re.sub(r'\\[a-zA-Z]+\{.*?\}', '', section_text)  # remove commands
            section_text = re.sub(r'\\[a-zA-Z]+', '', section_text)         # remove lone commands
            section_text = re.sub(r'\s+', ' ', section_text).strip()        # normalize whitespace
            extracted_sections.append(section_text)

    if not extracted_sections:
        return "No EMPLOYMENT HISTORY or PROJECTS found in resume."

    print(extracted_sections)
    return "\n\n".join(extracted_sections)

async def extract_skills_from_jd(resume_content: str, job_description: str) -> List[str]:
    """Extract 3-5 key skills from job description using OpenAI"""
    try:
        # Check if we have a real OpenAI API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "test-key-for-development":
            # Use mock response for testing
            print("Using mock skill extraction for testing")
            return ["Python", "Kubernetes", "Microservices", "PostgreSQL", "Cloud Platforms"]

        #client = openai.OpenAI(api_key=openai.api_key)

        prompt = f"""
        Analyze the following job description and extract 3-4 most important technical skills or qualifications required that have strong relation to the resume provided:

        Job Description:
        {job_description}

        Resume information:
        {resume_content}

        Return only a list of skills, one per line, without bullet points or numbers. Do not exceed 4 words per skill, this is a hard limit. 
        Focus on specific technical skills, tools, or qualifications mentioned in the job description, verbatim qualifications from the JD is better.
        Examples might look like: strong Python progamming experience, exceptional comunication skills, excellent data communication, etc.
        """

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=2000
        )

        print(response.model_dump_json(indent=2))
        skills_text = response.choices[0].message.content.strip()
        skills = [skill.strip() for skill in skills_text.split('\n') if skill.strip()]
        return skills[:4]  # Limit to 4 skills max

    except Exception as e:
        print(f"Error extracting skills: {e}")
        return ["Python", "Problem Solving", "Communication"]  # Fallback skills

async def generate_bullet_points(resume_content: str, skills: List[str], job_description: str) -> List[str]:
    """Generate resume-grounded bullet points using OpenAI"""
    try:
        # Check if we have a real OpenAI API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "test-key-for-development":
            # Use mock response for testing based on resume content and skills
            print("Using mock bullet point generation for testing")
            return [
                "I developed and maintained Python applications serving 10,000+ users daily, demonstrating strong Python programming skills",
                "I led a team of 4 developers in implementing microservices architecture using Docker and Kubernetes, directly matching your requirements",
                "I improved system performance by 40% through database optimization including PostgreSQL, aligning with your database needs",
                "I built REST APIs using FastAPI handling 1M+ requests per day, showcasing experience with large-scale distributed systems"
            ]

        #client = openai.OpenAI(api_key=api_key)

        prompt = f"""
        Based on the resume content below and the required skills, generate a corresponding number of compelling bullet points for a cover letter.
        Each bullet point should:
        1. Highlight relevant experience from the resume, do not make anything else up.
        2. Each bullet should be associated with each of the skills provided. No doubling up on one skill.
        3. Be specific and quantifiable when possible
        4. Be written in first person
        5. Start with an action verb, past tense
        6. no long em dashes, and don't precede the skill with a dash
        7. Use backslashes for % signs or special characters like for latex
        8. Never use 'my' or personal pronouns within response

        Resume Content:
        {resume_content}

        Required Skills:
        {', '.join(skills)}

        Job Description Context:
        {job_description[:500]}...

        Generate bullet points that demonstrate how the candidate's background aligns with the job requirements:
        """

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=2000
        )

        print(response.model_dump_json(indent=2))

        bullet_text = response.choices[0].message.content.strip()
        bullets = [bullet.strip() for bullet in bullet_text.split('\n') if bullet.strip() and not bullet.strip().startswith('#')]
        return bullets[:4]  # Limit to 5 bullet points

    except Exception as e:
        print(f"Error generating bullet points: {e}")
        return [
            "I bring strong technical expertise relevant to this position",
            "My experience aligns well with your team's requirements",
            "I have successfully delivered projects using similar technologies"
        ]

def create_cover_letter_latex(your_email:str, your_phone: str, company: str, role: str, source: str, skills: List[str], bullet_points: List[str]) -> str:
    """Create LaTeX cover letter template with injected content"""

    #bullets_latex = "\n".join([f"\\item {bullet}" for bullet in bullet_points])

    #bullets_latex = "\n".join(
        #[f"\\item \\textbf{{{skill}}} - {bullet}"
         #for skill, bullet in zip(skills, bullet_points)]
    #)
    STOPWORDS = {"and", "or", "of", "in", "on", "for", "with", "to", "a", "an", "the"}

    def smart_capitalize(skill: str) -> str:
        words = skill.split()
        formatted = []
        for i, w in enumerate(words):
            # preserve acronyms or stylized casing
            if w.isupper() or any(ch.isupper() for ch in w[1:]):  
                formatted.append(w)
            # lowercase stopwords (unless first word)
            elif w.lower() in STOPWORDS and i != 0:
                formatted.append(w.lower())
            else:
                formatted.append(w.capitalize())
        return " ".join(formatted)

    #addressing the capitalization of skills, took out - as LLM was putting it in anyway
    bullets_latex = "\n".join([f"\\item \\textbf{{{smart_capitalize(skill)}}} {bullet}" for skill, bullet in zip(skills, bullet_points)])
    #skills_latex = ", ".join([f"{skill}" for skill in skills])

    #This addresses the 'and' after the last skill
    skills_latex = (
    " and ".join(skills) if len(skills) <= 2
    else ", ".join(skills[:-1]) + ", and " + skills[-1])
    

    latex_template = f"""
\\documentclass[11pt,letterpaper]{{article}}
\\usepackage[margin=1in]{{geometry}}
\\usepackage{{enumitem}}
\\usepackage{{parskip}}

\\begin{{document}}
\\pagestyle{{empty}}
\\noindent
{{\\LARGE \\textbf{{Mike Rabayda}}}} \\\\
{your_email} \\\\
{your_phone} \\\\
\\today

\\vspace{{2em}}

\\noindent
To the {company} Hiring Committee,

My name is Mike Rabayda, and I am currently a M.S. Data Science student at Fordham University in New York, NY.  I recently came across your position for {company}'s {role} position from {source}, and I would like to state my candidacy for the position.

Your position calls for {skills_latex}.  I can offer the following qualifications to you:

\\begin{{itemize}}[leftmargin=*]
{bullets_latex}
\\end{{itemize}}

In addition to providing you with the skills that you require, it has also been commonplace for me to work with many different personalities, and sometimes under difficult circumstances. Each has taught me the importance of being a team player, and drove me into positions of leadership. Furthermore, I am comfortable working independently and as part of a team. In addition to bringing you a strong skillset, I also bring interpersonal skills that would fit well with your team and clients.

Thank you for your time and consideration, I will contact you within two weeks' time to follow up on my candidacy. Should you need to reach me before then, please do not hesitate. I look forward to hearing back from you.

\\vspace{{1em}}

\\noindent
Sincerely, \\\\
Mike Rabayda \\\\

Enclosed: Resume

\\end{{document}}
"""

    return latex_template

async def compile_latex_to_pdf(latex_content: str, output_dir: str, company: str, role: str) -> str:
    """Compile LaTeX content to PDF"""

    # Create temporary LaTeX file
    tex_file = os.path.join(output_dir, f"cover_letter_{company}_{role}.tex")
    pdf_file = os.path.join(output_dir, f"cover_letter_{company}_{role}.pdf")

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

        # Check if PDF was created (even if there were warnings)
        if not os.path.exists(pdf_file):
            print(f"LaTeX compilation failed. Return code: {process.returncode}")
            print(f"stdout: {process.stdout}")
            print(f"stderr: {process.stderr}")
            raise HTTPException(status_code=500, detail="PDF file was not generated")

        # Log warnings but don't fail if PDF was created
        if process.returncode != 0:
            print(f"LaTeX compilation completed with warnings. Return code: {process.returncode}")
            print(f"stderr: {process.stderr}")

        return pdf_file

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="LaTeX compilation timed out")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="pdflatex not found. Please install LaTeX.")

def cleanup_file(file_path: str):
    """Clean up temporary file"""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
    except Exception as e:
        print(f"Error cleaning up file {file_path}: {e}")

@app.post("/generate-cover-letter")
async def generate_cover_letter(
    background_tasks: BackgroundTasks,
    resume: UploadFile = File(...),
    job_description: str = Form(...),
    your_email: str = Form(...),
    your_phone: str = Form(...),
    company: str = Form(...),
    role: str = Form(...),
    source: str = Form(...)
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

            #Parse the .tex resume for professional experience and projects 
            resume_content_parsed = await parse_resume_sections(resume_content)            

            # Extract skills from job description
            skills = await extract_skills_from_jd(resume_content_parsed,job_description)

            # Generate bullet points
            bullet_points = await generate_bullet_points(resume_content_parsed, skills, job_description)

            # Create cover letter LaTeX
            latex_content = create_cover_letter_latex(your_email, your_phone, company, role, source, skills, bullet_points)

            # Compile to PDF
            pdf_path = await compile_latex_to_pdf(latex_content, temp_dir, company, role)

            # Copy PDF to a permanent location for serving
            permanent_filename = f"cover_letter_{uuid.uuid4().hex[:8]}.pdf"
            permanent_path = os.path.join("temp_files", permanent_filename)

            # Copy the PDF file
            async with aiofiles.open(pdf_path, 'rb') as src:
                content = await src.read()
                async with aiofiles.open(permanent_path, 'wb') as dst:
                    await dst.write(content)

            # Schedule cleanup of the permanent file
            background_tasks.add_task(cleanup_file, permanent_path)

            safe_company = re.sub(r'[^A-Za-z0-9]+', '_', company)
            safe_role = re.sub(r'[^A-Za-z0-9]+', '_', role)

            # Return PDF file
            return FileResponse(
                permanent_path,
                media_type="application/pdf",
                filename=f"Rabayda_Cover_{safe_company}_{safe_role}.pdf"
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
