from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import PyPDF2
import zipfile
import io
import tempfile
import os
from typing import List, Dict, Any
import google.generativeai as genai
from pydantic import BaseModel
import json
import re
from dotenv import load_dotenv
load_dotenv()

# Configure Gemini API (you'll need to set your API key)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
print(os.getenv("GOOGLE_API_KEY"))


app = FastAPI(title="Invoice Reimbursement Analysis API")

class InvoiceAnalysis(BaseModel):
    invoice_id: str
    reimbursement_status: str
    reimbursable_amount: int
    reason: str

class ReimbursementResponse(BaseModel):
    analyses: List[InvoiceAnalysis]
    total_invoices_processed: int

def extract_text_from_pdf(pdf_file_bytes: bytes) -> str:
    """Extract text from PDF bytes."""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_file_bytes))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error extracting PDF text: {str(e)}")

def extract_invoices_from_zip(zip_file_bytes: bytes) -> Dict[str, str]:
    """Extract invoice PDFs from ZIP file and return filename->text mapping."""
    invoices = {}
    try:
        with zipfile.ZipFile(io.BytesIO(zip_file_bytes), 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                if file_info.filename.lower().endswith('.pdf'):
                    with zip_ref.open(file_info) as pdf_file:
                        pdf_bytes = pdf_file.read()
                        invoice_text = extract_text_from_pdf(pdf_bytes)
                        invoices[file_info.filename] = invoice_text
        return invoices
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing ZIP file: {str(e)}")

# Optimized System Prompt
OPTIMIZED_SYSTEM_PROMPT = """
You are a precision-focused HR expense analyst. Your task is to evaluate invoices against company reimbursement policies with absolute accuracy and consistency.

CORE RESPONSIBILITIES:
1. Extract key invoice data: date, vendor, amount, expense category, purpose, line items
2. Map expenses to appropriate policy categories and limits  
3. Apply all policy restrictions systematically
4. Calculate exact reimbursable amounts as integers
5. Provide clear, policy-backed reasoning

ANALYSIS WORKFLOW:
For EACH invoice, execute these steps sequentially:

STEP 1 - INVOICE PARSING:
- Extract: Total amount, date, vendor/merchant, expense purpose, individual line items
- Identify primary expense category (meals, travel, office supplies, etc.)

STEP 2 - POLICY MAPPING:
- Locate relevant policy section for this expense category
- Identify applicable limits (daily, monthly, per-item, percentage-based)
- Note any categorical restrictions or exclusions

STEP 3 - RESTRICTION ANALYSIS:
- Check date validity against policy timeframes
- Verify expense falls within allowed categories
- Apply any caps, limits, or percentage restrictions
- Identify prohibited items or vendors

STEP 4 - CALCULATION:
- Calculate maximum allowable amount based on policy
- Compare against actual invoice amount
- Determine final reimbursable amount (integer only)

STEP 5 - CLASSIFICATION:
- FULLY REIMBURSED: Entire amount within policy limits
- PARTIALLY REIMBURSED: Amount exceeds limits but partially eligible  
- DECLINED: Violates policy restrictions or prohibited category

CRITICAL REQUIREMENTS:
- Use ONLY the provided company policy - no external assumptions
- All amounts must be integers (round down if necessary)
- Provide specific policy citations in reasoning
- Be consistent in applying rules across all invoices
- Process each invoice independently

RESPONSE FORMAT:
For each invoice, provide:
{
  "invoice_id": "filename.pdf",
  "reimbursement_status": "Fully Reimbursed|Partially Reimbursed|Declined", 
  "reimbursable_amount": integer_value,
  "reason": "Specific policy-based explanation with section references"
}

IMPORTANT: Analyze all invoices in a single response to minimize API calls. Be thorough but concise in reasoning.
"""

def analyze_invoices_with_llm(policy_text: str, invoices: Dict[str, str]) -> List[InvoiceAnalysis]:
    """Analyze all invoices against policy using Gemini in a single call."""
    
    # Prepare combined prompt with policy and all invoices
    combined_prompt =  f""" COMPANY REIMBURSEMENT POLICY:{policy_text} INVOICES TO ANALYZE:"""
    
    for filename, invoice_text in invoices.items():
        combined_prompt += f"\n--- INVOICE: {filename} ---\n{invoice_text}\n"
    
    combined_prompt += """
Please analyze each invoice against the policy and provide a JSON array response with the exact format specified in the system prompt.
"""
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(
            [OPTIMIZED_SYSTEM_PROMPT, combined_prompt],
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=4000,
            ),
        )
        
        # Extract JSON from response
        response_text = response.text
        
        # Try to find and parse JSON array
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            analyses_data = json.loads(json_str)
        else:
            # Fallback: try to parse entire response as JSON
            analyses_data = json.loads(response_text)
        
        # Convert to InvoiceAnalysis objects
        analyses = []
        for analysis_data in analyses_data:
            analysis = InvoiceAnalysis(
                invoice_id=analysis_data['invoice_id'],
                reimbursement_status=analysis_data['reimbursement_status'],
                reimbursable_amount=int(analysis_data['reimbursable_amount']),
                reason=analysis_data['reason']
            )
            analyses.append(analysis)
        
        return analyses
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM analysis failed: {str(e)}")

@app.post("/analyze-invoices", response_model=ReimbursementResponse)
async def analyze_invoices(
    hr_policy: UploadFile = File(..., description="HR Reimbursement Policy PDF"),
    invoices_zip: UploadFile = File(..., description="ZIP file containing invoice PDFs")
):
    """
    Analyze employee expense invoices against HR reimbursement policy.
    
    Args:
        hr_policy: PDF file containing the HR reimbursement policy
        invoices_zip: ZIP file containing one or more invoice PDF files
    
    Returns:
        JSON response with analysis results for each invoice
    """
    
    # Validate file types
    if not hr_policy.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="HR policy must be a PDF file")
    
    if not invoices_zip.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Invoices must be in a ZIP file")
    
    try:
        # Extract policy text
        policy_bytes = await hr_policy.read()
        policy_text = extract_text_from_pdf(policy_bytes)
        
        if not policy_text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from policy PDF")
        
        # Extract invoices from ZIP
        invoices_bytes = await invoices_zip.read()
        invoices = extract_invoices_from_zip(invoices_bytes)
        
        if not invoices:
            raise HTTPException(status_code=400, detail="No PDF invoices found in ZIP file")
        
        # Analyze invoices with LLM (single call for efficiency)
        analyses = analyze_invoices_with_llm(policy_text, invoices)
        
        return ReimbursementResponse(
            analyses=analyses,
            total_invoices_processed=len(analyses)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Invoice Reimbursement Analysis API", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)