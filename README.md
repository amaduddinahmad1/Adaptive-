# JD + CV Intelligence & Eligibility Engine

**Project:** Adaptive Multimodal AI Interview & Candidate Assessment System  
**Module Owner:** Amad Ud Din Ahmad  

## Overview
This module serves as the primary intelligent screening stage of the pipeline. It parses Job Descriptions (JDs) and Resumes/CVs into strictly validated, structured representations, evaluates mandatory and preferred candidate qualifications, and conducts specific vs. general experience matching before candidates progress to the Adaptive Voice Interview engine.

## Current Phase: JD Parser
This repository currently contains the initial scoped setup for the **JD Parser** subcomponent:
- **`app/schemas/`**: Pydantic v2 schemas defining `JobRequirementProfile` and its sub-models.
- **`app/services/parser/`**: Anthropic Claude-powered structured extraction engine.
- **`tests/`**: Unit tests and sample JD fixtures.

## Getting Started
1. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set your environment variables:
   ```bash
   cp .env.example .env
   ```
4. Run tests:
   ```bash
   pytest
   ```
