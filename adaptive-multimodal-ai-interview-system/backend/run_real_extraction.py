"""
run_real_extraction.py

Executes parse_job_description against the live Google Gemini API
for the proposal's canonical JD and prints the resulting
JobRequirementProfile as formatted JSON.
"""

from app.services.jd_intelligence.jd_parser import parse_job_description

PROPOSAL_JD = """Position: Senior Python Developer
Experience: Minimum 3 years
Python Experience: Minimum 2 years
FastAPI: Required
PostgreSQL: Required
Docker: Preferred"""


def run_extraction(jd_text: str, label: str):
    print(f"\n{'=' * 70}")
    print(f"RUNNING LIVE EXTRACTION: {label}")
    print(f"{'=' * 70}\n")
    print("INPUT JD TEXT:")
    print("-" * 40)
    print(jd_text)
    print("-" * 40)
    print("\nCalling Google Gemini API...")

    try:
        profile = parse_job_description(jd_text)
        print("\nSUCCESS! RESULTING JobRequirementProfile JSON:")
        print("-" * 40)
        print(profile.model_dump_json(indent=2))
        return profile
    except Exception as e:
        print(f"\nEXTRACTION FAILED: {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    run_extraction(PROPOSAL_JD, "Proposal Section 4 Example JD")
