============================================================
  Medical Screening Assistant
  Local AI + Prolog — README
============================================================

This repository provides a medical screening tool that combines local 
LLM-based symptom extraction with a formal Prolog reasoning engine.

IMPORTANT: This tool is for educational and screening purposes only. 
It is NOT a diagnostic tool and does not provide medical diagnoses. 
All results are "screening possibilities" and must be verified by 
a qualified clinician.

------------------------------------------------------------
1. REQUIREMENTS
------------------------------------------------------------
  - Python 3.11+
  - SWI-Prolog (provides the `swipl` command)
  - Ollama (running locally on localhost:11434)
    - Required model: `gemma4:12b-mlx` (or similar tool-calling model)
  - pip packages in requirements.txt (Flask, PyYAML, Pydantic, Pytest)

macOS:
    brew install swi-prolog
    brew install ollama
    ollama pull gemma4:12b-mlx

Linux (Debian/Ubuntu):
    sudo apt install swi-prolog python3 python3-pip
    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull gemma4:12b-mlx

Windows:
    1. Install Python from https://www.python.org/downloads/
       - IMPORTANT: check "Add python.exe to PATH" in the installer.
    2. Install SWI-Prolog from https://www.swi-prolog.org/download/stable
    3. Install Ollama from https://ollama.com/download
    4. Run `ollama pull gemma4:12b-mlx` in a terminal.

------------------------------------------------------------
2. SETUP (all platforms)
------------------------------------------------------------
From the project folder:

macOS / Linux:
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

Windows:
    py -m venv venv
    venv\\Scripts\\activate
    py -m pip install -r requirements.txt

------------------------------------------------------------
3. RUNNING THE WEB APP
------------------------------------------------------------
Ensure Ollama is running (`ollama serve` or the desktop app).

macOS / Linux:
    python3 app.py

Windows:
    py app.py

Then open http://localhost:8080 in your browser.

------------------------------------------------------------
3A. PRIVATE TAILSCALE ACCESS
------------------------------------------------------------
When the app is running on the `haipingxu` Windows machine, authorized
Tailscale devices can use either of these private tailnet-only links:

  - HTTPS hostname: https://haipingxu.tail9933e0.ts.net/
  - Tailscale IP:   http://100.72.253.109:8081/

These addresses are not public application endpoints. The accessing device
must be connected to the same Tailscale network, and the Flask app and
Tailscale Serve configuration must be running on the host machine.

------------------------------------------------------------
4. CONFIGURATION & OVERRIDES
------------------------------------------------------------
You can override the following environment variables to change 
the LLM backend:

- OLLAMA_BASE_URL:    Default "http://127.0.0.1:11434"
- OLLAMA_MODEL:       Default "gemma4:12b-mlx"
- OLLAMA_TIMEOUT_SECONDS: Default "30"

Example:
    OLLAMA_MODEL=qwen2.5-coder:32b python3 app.py

------------------------------------------------------------
5. FILE STRUCTURE AND PURPOSE
------------------------------------------------------------
- diseases.yaml:       Declarative source for disease thresholds, 
                       questions, and symptom routing.
- generate_prolog.py:  Compiles diseases.yaml into Prolog logic.
- web_engine.pl:       The non-interactive scoring engine used by Flask.
- app.py:              Flask server, Ollama-based extraction, 
                       deterministic emergency triage, and session management.
- static/index.html:   Browser chat interface.
- test_app.py:         Comprehensive test suite for extraction, 
                       triage, and session security.
- test_llm_extractor.py: Tests for the LLM and fallback extraction logic.

------------------------------------------------------------
6. HOW TO ADD A NEW DISEASE
------------------------------------------------------------
1. Add a block under `diseases:` in diseases.yaml.
2. Add the disease name to the relevant `symptom_routing` lines.
3. Restart app.py — it regenerates the Prolog files automatically.

------------------------------------------------------------
7. TROUBLESHOOTING
------------------------------------------------------------
"Symptom extraction failed":
    Ensure Ollama is running and you have pulled the required model.
    Check that the OLLAMA_BASE_URL is correct.

"swipl is not recognized":
    Ensure SWI-Prolog is installed and the `bin` folder is in your PATH.

Port 8080 already in use:
    Edit the port number in the last line of app.py (app.run(..., port=8080)).
============================================================
