
# Invoice Reimbursement Analysis API

This FastAPI-based application automates the analysis of employee invoice reimbursement claims by comparing each invoice against a provided HR Reimbursement Policy using an LLM (Google Gemini). The system processes multiple invoice files in one go and returns a structured reimbursement decision for each.

---

##  Features

- Upload HR Reimbursement Policy (PDF)
- Upload ZIP file containing invoice PDFs
- Uses **Google Gemini (gemini-2.0-flash)** to evaluate invoices
- JSON response with:
  - Invoice ID
  - Reimbursement Status: `Fully Reimbursed`, `Partially Reimbursed`, or `Declined`
  - Reimbursable Amount (integer)
  - Reason with specific policy references
- Single-shot LLM prompt to minimize cost and latency

---

## Project Structure

```
.
├── task1_invoice_api.py       # FastAPI application
├── .env                       # Contains your Gemini API key
├── requirements.txt           # Python dependencies
```

---

## Installation & Setup

### 1. Clone the Repository

```bash
git clone <your_repo_url>
cd <your_repo_name>
```

### 2. Set up your Python Environment

```bash
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### 3. Add Your API Key

Create a `.env` file in the root directory with:

```env
GOOGLE_API_KEY=your_google_gemini_api_key
```

---

## Running the App

```bash
uvicorn task1_invoice_api:app --reload
```

Visit the API docs at:  
[http://localhost:8000/docs](http://localhost:8000/docs)

---

## API Usage

### `POST /analyze-invoices`

#### Request:
- `hr_policy`: PDF file (HR Reimbursement Policy)
- `invoices_zip`: ZIP file (containing invoice PDFs)

#### Response:
```json
{
  "analyses": [
    {
      "invoice_id": "invoice1.pdf",
      "reimbursement_status": "Partially Reimbursed",
      "reimbursable_amount": 800,
      "reason": "Only meals under ₹500/day are reimbursable as per Section 3.2"
    }
  ],
  "total_invoices_processed": 1
}
```

---

## LLM Details

- **Model**: Google Gemini (gemini-2.0-flash)
- **Strategy**: One-shot prompt with policy + all invoices analyzed together
- **Prompt Highlights**:
  - Step-by-step workflow (parsing → mapping → restrictions → calculation → decision)
  - Structured JSON response
  - Mandatory policy citation for every decision
  - Integer-only reimbursement

---

## Testing

Use the sample dataset provided in the assignment. Make sure:
- HR policy is well-structured and legible
- Invoices contain clear breakdowns (amounts, purpose, vendor)

---

## Notes

- The API is **stateless** and does not store files or data.
- Only policy rules in the uploaded PDF are considered — **no external assumptions**.

