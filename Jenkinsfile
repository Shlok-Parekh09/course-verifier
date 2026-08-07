pipeline {
    agent any

    parameters {
        string(name: 'START_PAGE', defaultValue: '', description: 'Start Page Number (Leave blank to run from page 1)')
        string(name: 'END_PAGE', defaultValue: '', description: 'End Page Number (Leave blank to run to the end)')
        string(name: 'CHUNK_SIZE', defaultValue: '30', description: 'Pages per chunk')
        string(name: 'PDF_URL', defaultValue: 'https://filebin.net/example/link_compile.pdf', description: 'Direct download URL for the PDF (e.g. from Filebin or Transfer.sh). Google Drive links are NOT supported due to their automated virus scan blockers.')
        choice(name: 'LLM_BACKEND', choices: ['api', 'local_ollama', 'cloud_ollama'], description: 'LLM Backend to use')
        string(name: 'MAX_CONCURRENT_CHUNKS', defaultValue: '1', description: 'Max chunks to run at the exact same time (lower this if CPU maxes out)')
        text(name: 'ENV_FILE', defaultValue: '', description: 'Paste your complete .env file contents here')
    }

    environment {
        CI = "true"
        VERIFIER_NUM_BROWSERS = "3"
        VERIFIER_NO_FORCE_EXIT = "true"
        DISPLAY = ":99"
    }

    stages {
        stage('Environment Setup') {
            steps {
                script {
                    echo "Setting up dependencies and swap space for Kali Linux..."
                    sh '''#!/bin/bash
                        sudo apt-get update && sudo apt-get install -y curl xvfb x11-utils libgl1 tesseract-ocr libtesseract-dev jq
                        wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
                        sudo dpkg -i google-chrome-stable_current_amd64.deb || sudo apt-get -f install -y || true

                        echo "Configuring 30GB swap space to prevent memory crashes..."
                        if [ ! -f /swapfile_extra ]; then
                            sudo fallocate -l 30G /swapfile_extra || sudo dd if=/dev/zero of=/swapfile_extra bs=1M count=30720
                            sudo chmod 600 /swapfile_extra
                            sudo mkswap /swapfile_extra || true
                        fi
                        sudo swapon /swapfile_extra || true
                        
                        curl -LsSf https://astral.sh/uv/install.sh | sh || true
                    '''
                }
            }
        }

        stage('Generate Chunks') {
            steps {
                script {
                    sh '''#!/bin/bash
                        export PATH="$HOME/.local/bin:$PATH"
                        uv cache clean || true
                        uv venv --clear .venv
                        uv pip install -r requirements.txt python-dotenv PyMuPDF
                        mkdir -p backend
                        
                        echo "Downloading PDF from URL..."
                        curl -L "${PDF_URL}" -o backend/link_compile.pdf
                        
                        uv run python backend/generate_jenkins_chunks.py
                    '''
                }
            }
        }

        stage('Verify (Parallel)') {
            steps {
                script {
                    def chunksText = readFile('chunks.txt').trim()
                    def lines = chunksText.split('\n')
                    def batchSize = env.MAX_CONCURRENT_CHUNKS ? env.MAX_CONCURRENT_CHUNKS.toInteger() : 2

                    for (int i = 0; i < lines.length; i += batchSize) {
                        def parallelBranches = [:]
                        
                        for (int j = 0; j < batchSize && (i + j) < lines.length; j++) {
                            def line = lines[i + j].trim()
                            if (!line) continue
                            
                            def parts = line.split(',')
                            def start = parts[0]
                            def end = parts[1]
                            def branchName = "Verify ${start}-${end}"
                            
                            parallelBranches[branchName] = {
                                stage(branchName) {
                                    sh """#!/bin/bash
                                        export PATH="\$HOME/.local/bin:\$PATH"
                                        export START_PAGE="${start}"
                                        export END_PAGE="${end}"
                                        export CI="true"
                                        export VERIFIER_NUM_BROWSERS="1"
                                        export OLLAMA_MAX_CONCURRENCY="1"
                                        
                                        # Copy environment file to backend if it exists on the host
                                        if [[ -n "\$ENV_FILE" ]]; then
                                            echo "\$ENV_FILE" > .env
                                        fi

                                        # Start virtual frame buffer for Chrome
                                        if [ "\$(uname)" == "Linux" ]; then Xvfb :99 -screen 0 1280x1024x24 -ac +extension RANDR +extension GLX +render -noreset & sleep 3; fi
                                        
                                        echo "Running chunk ${start} to ${end}"
                                        cd backend && uv run python autonomous_course_verifier.py link_compile.pdf
                                        
                                        # Rename artifacts so they can be securely archived and merged
                                        mv autonomous_verified_link_compile.pdf.json "autonomous_verified_${start}_to_${end}_link_compile.json" || true
                                        mv local_database.db "local_database_${start}_to_${end}.db" || true
                                        mv Autonomous_Course_Verification_Report.pdf "verification-results-${start}-to-${end}-dummy.pdf" || true
                                        
                                        exit 0
                                    """
                                }
                            }
                        }
                        
                        // Execute this batch before starting the next batch
                        parallel parallelBranches
                    }
                }
            }
        }

        stage('Merge Results') {
            steps {
                script {
                    sh '''#!/bin/bash
                        export PATH="$HOME/.local/bin:$PATH"
                        
                        uv run python3 - <<'PYEOF'
import os, json, glob, sqlite3, shutil, fitz, re

merged = []
merged_dict = {}
json_files = sorted(glob.glob("backend/**/*link_compile*.json", recursive=True))
for jf in json_files:
    try:
        with open(jf, encoding="utf-8") as f: data = json.load(f)
        if not isinstance(data, list): continue
        for course in data:
            key = (str(course.get("name", "")).strip().lower(), str(course.get("uni", "")).strip().lower(), course.get("page_num"), course.get("box_index"))
            if key not in merged_dict:
                merged_dict[key] = course
            else:
                is_processed = course.get("processed_this_run") or course.get("reason", "") != ""
                old_is_processed = merged_dict[key].get("processed_this_run") or merged_dict[key].get("reason", "") != ""
                if is_processed and not old_is_processed:
                    merged_dict[key] = course
    except Exception as e: print(f"Error reading {jf}: {e}")
merged = list(merged_dict.values())
merged.sort(key=lambda c: (c.get("page_num", 0), c.get("box_index", 0)))
with open("merged_run.json", "w", encoding="utf-8") as f: json.dump(merged, f, indent=2, ensure_ascii=False)

def get_chunk_start(filepath):
    match = re.search(r'verification-results-(\\d+)-to-', filepath)
    if match: return int(match.group(1))
    return 0

pdf_files = sorted(glob.glob("backend/**/*.pdf", recursive=True), key=get_chunk_start)
if pdf_files:
    merged_pdf = fitz.open()
    for pdf in pdf_files:
        if "link_compile.pdf" in pdf: continue
        try:
            doc = fitz.open(pdf)
            merged_pdf.insert_pdf(doc)
            doc.close()
        except Exception as e: pass
    merged_pdf.save("merged_run.pdf")
    merged_pdf.close()

db_files = glob.glob("backend/**/*.db", recursive=True)
if db_files:
    shutil.copy(db_files[0], "merged_run.db")
    base_conn = sqlite3.connect("merged_run.db")
    base_conn.row_factory = sqlite3.Row
    for db_path in db_files[1:]:
        try:
            src = sqlite3.connect(db_path)
            src.row_factory = sqlite3.Row
            for row in src.execute("SELECT * FROM affiliations"): base_conn.execute("INSERT OR REPLACE INTO affiliations (course_name, university, affiliated_uni) VALUES (?,?,?)", (row["course_name"], row["university"], row["affiliated_uni"]))
            for row in src.execute("SELECT * FROM university_abbreviations"): base_conn.execute("INSERT OR IGNORE INTO university_abbreviations (abbreviation, full_name) VALUES (?,?)", (row["abbreviation"], row["full_name"]))
            for row in src.execute("SELECT university FROM qs_ranking"): base_conn.execute("INSERT OR IGNORE INTO qs_ranking (university) VALUES (?)", (row["university"],))
            for row in src.execute("SELECT university FROM nirf_ranking"): base_conn.execute("INSERT OR IGNORE INTO nirf_ranking (university) VALUES (?)", (row["university"],))
            src.close()
        except Exception as e: pass
    base_conn.commit()
    base_conn.close()
PYEOF
                    '''
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'merged_run.json, merged_run.db, merged_run.pdf', allowEmptyArchive: true
            cleanWs()
        }
    }
}
