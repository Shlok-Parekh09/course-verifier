import re

with open('autonomous_course_verifier.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.strip() == "if os.name == 'nt':" and "                                    if os.name" in line:
        # It's indented by 36 spaces instead of 32
        for j in range(i, i+23):  # Fix the block down to pdf_doc.close()
            if lines[j].startswith("                                    "):
                lines[j] = lines[j][4:]
        break

with open('autonomous_course_verifier.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
