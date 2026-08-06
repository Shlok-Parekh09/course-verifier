import os, fitz, json

doc = fitz.open("backend/link_compile.pdf")

in_start = os.environ.get("START_PAGE", "").strip()
in_end = os.environ.get("END_PAGE", "").strip()
chunk_size_str = os.environ.get("CHUNK_SIZE", "30").strip()
chunk_size = int(chunk_size_str) if chunk_size_str.isdigit() else 30

start_page = int(in_start) if in_start.isdigit() else 1
end_page = int(in_end) if in_end.isdigit() else len(doc)

if start_page < 1: start_page = 1
if end_page > len(doc): end_page = len(doc)
if start_page > end_page: start_page = end_page

chunks = []
for i in range(start_page, end_page + 1, chunk_size):
    start = i
    end = min(i + chunk_size - 1, end_page)
    chunks.append({"start": start, "end": end})

print(f"Generated {len(chunks)} chunks from page {start_page} to {end_page}.")

# Generate the child-pipeline.yml
yaml_lines = [
    "stages:",
    "  - verify",
    "  - merge"
]

verify_jobs = []

for idx, chunk in enumerate(chunks):
    start = chunk['start']
    end = chunk['end']
    job_name = f"verify-{start}-to-{end}"
    verify_jobs.append(job_name)
    
    yaml_lines.extend([
        "",
        f"{job_name}:",
        "  stage: verify",
        "  image: python:3.12",
        "  tags:",
        "    - $RUNNER_TYPE",
        "  variables:",
        f"    START_PAGE: \"{start}\"",
        f"    END_PAGE: \"{end}\"",
        "    CI: \"true\"",
        "    VERIFIER_NUM_BROWSERS: \"3\"",
        "    VERIFIER_NO_FORCE_EXIT: \"true\"",
        "    DISPLAY: \":99\"",
        "  script:",
        "    - |",
        "      if [ \"$RUNNER_TYPE\" == \"saas-linux-small-amd64\" ]; then",
        "        apt-get update && apt-get install -y curl xvfb x11-utils libgl1 tesseract-ocr libtesseract-dev",
        "        wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb",
        "        dpkg -i google-chrome-stable_current_amd64.deb || apt-get -f install -y",
        "        echo \"Setting up 10GB swap for cloud runner...\"",
        "        fallocate -l 10G /swapfile_extra || dd if=/dev/zero of=/swapfile_extra bs=1M count=10240",
        "        chmod 600 /swapfile_extra && mkswap /swapfile_extra || true && swapon /swapfile_extra || true",
        "      else",
        "        echo \"Assuming self-hosted Kali runner with swap already configured.\"",
        "        sudo apt-get update && sudo apt-get install -y xvfb x11-utils libgl1 tesseract-ocr libtesseract-dev",
        "        wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb",
        "        sudo dpkg -i google-chrome-stable_current_amd64.deb || sudo apt-get -f install -y || true",
        "      fi",
        "      curl -LsSf https://astral.sh/uv/install.sh | sh || true",
        "      export PATH=\"$HOME/.cargo/bin:$PATH\"",
        "      uv cache clean || true",
        "      uv venv .venv",
        "      uv pip install -r requirements.txt python-dotenv gdown",
        "      if [ -n \"$ENV_FILE\" ]; then echo \"$ENV_FILE\" > backend/.env; fi",
        "      if [ \"$(uname)\" == \"Linux\" ]; then Xvfb :99 -screen 0 1280x1024x24 -ac +extension RANDR +extension GLX +render -noreset & sleep 3; fi",
        "      cd backend && uv run python autonomous_course_verifier.py link_compile.pdf || echo 'Verifier exited with non-zero status'",
        "      rm -f link_compile.pdf ndu.pdf",
        "  artifacts:",
        "    paths:",
        "      - backend/*.pdf",
        "      - backend/autonomous_verified_*.json",
        "      - backend/local_database.db",
        "    expire_in: 1 day"
    ])

# Add the merge job
yaml_lines.extend([
    "",
    "merge-results:",
    "  stage: merge",
    "  image: python:3.12",
    "  tags:",
    "    - $RUNNER_TYPE",
    "  needs: [" + ", ".join([f'"{j}"' for j in verify_jobs]) + "]",
    "  script:",
    "    - curl -LsSf https://astral.sh/uv/install.sh | sh || true",
    "    - export PATH=\"$HOME/.cargo/bin:$PATH\"",
    "    - uv venv --clear .venv",
    "    - uv pip install PyMuPDF",
    "    - |",
    "      uv run python3 - <<'PYEOF'",
    "      import os, json, glob",
    "      merged = []",
    "      merged_dict = {}",
    "      json_files = sorted(glob.glob(\"backend/**/*link_compile*.json\", recursive=True))",
    "      for jf in json_files:",
    "          try:",
    "              with open(jf, encoding=\"utf-8\") as f:",
    "                  data = json.load(f)",
    "              if not isinstance(data, list): continue",
    "              for course in data:",
    "                  key = (str(course.get(\"name\", \"\")).strip().lower(), str(course.get(\"uni\", \"\")).strip().lower(), course.get(\"page_num\"), course.get(\"box_index\"))",
    "                  if key not in merged_dict:",
    "                      merged_dict[key] = course",
    "                  else:",
    "                      is_processed = course.get(\"processed_this_run\") or course.get(\"reason\", \"\") != \"\"",
    "                      old_is_processed = merged_dict[key].get(\"processed_this_run\") or merged_dict[key].get(\"reason\", \"\") != \"\"",
    "                      if is_processed and not old_is_processed:",
    "                          merged_dict[key] = course",
    "          except Exception as e: print(f\"Error reading {jf}: {e}\")",
    "      merged = list(merged_dict.values())",
    "      merged.sort(key=lambda c: (c.get(\"page_num\", 0), c.get(\"box_index\", 0)))",
    "      with open(\"merged_run.json\", \"w\", encoding=\"utf-8\") as f: json.dump(merged, f, indent=2, ensure_ascii=False)",
    "      import fitz, re",
    "      def get_chunk_start(filepath):",
    "          match = re.search(r'verification-results-(\d+)-to-', filepath)",
    "          if match: return int(match.group(1))",
    "          return 0",
    "      pdf_files = sorted(glob.glob(\"backend/**/*.pdf\", recursive=True), key=get_chunk_start)",
    "      if pdf_files:",
    "          merged_pdf = fitz.open()",
    "          for pdf in pdf_files:",
    "              try:",
    "                  doc = fitz.open(pdf)",
    "                  merged_pdf.insert_pdf(doc)",
    "                  doc.close()",
    "              except Exception as e: pass",
    "          merged_pdf.save(\"merged_run.pdf\")",
    "          merged_pdf.close()",
    "      PYEOF",
    "    - |",
    "      uv run python3 - <<'DBEOF'",
    "      import glob, sqlite3, os, shutil",
    "      db_files = glob.glob(\"backend/**/*.db\", recursive=True)",
    "      if db_files:",
    "          shutil.copy(db_files[0], \"merged_run.db\")",
    "          base_conn = sqlite3.connect(\"merged_run.db\")",
    "          base_conn.row_factory = sqlite3.Row",
    "          for db_path in db_files[1:]:",
    "              try:",
    "                  src = sqlite3.connect(db_path)",
    "                  src.row_factory = sqlite3.Row",
    "                  for row in src.execute(\"SELECT * FROM affiliations\"): base_conn.execute(\"INSERT OR REPLACE INTO affiliations (course_name, university, affiliated_uni) VALUES (?,?,?)\", (row[\"course_name\"], row[\"university\"], row[\"affiliated_uni\"]))",
    "                  for row in src.execute(\"SELECT * FROM university_abbreviations\"): base_conn.execute(\"INSERT OR IGNORE INTO university_abbreviations (abbreviation, full_name) VALUES (?,?)\", (row[\"abbreviation\"], row[\"full_name\"]))",
    "                  for row in src.execute(\"SELECT university FROM qs_ranking\"): base_conn.execute(\"INSERT OR IGNORE INTO qs_ranking (university) VALUES (?)\", (row[\"university\"],))",
    "                  for row in src.execute(\"SELECT university FROM nirf_ranking\"): base_conn.execute(\"INSERT OR IGNORE INTO nirf_ranking (university) VALUES (?)\", (row[\"university\"],))",
    "                  src.close()",
    "              except Exception as e: pass",
    "          base_conn.commit()",
    "          base_conn.close()",
    "      DBEOF",
    "  artifacts:",
    "    paths:",
    "      - merged_run.json",
    "      - merged_run.pdf",
    "      - merged_run.db"
])

with open("child-pipeline.yml", "w") as f:
    f.write("\n".join(yaml_lines))

print(f"child-pipeline.yml generated successfully!")
