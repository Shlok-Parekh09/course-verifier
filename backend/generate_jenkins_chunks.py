import os
import json
import fitz

def main():
    pdf_path = "backend/link_compile.pdf"
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found.")
        # Fallback to 1 chunk if no PDF found (shouldn't happen in pipeline)
        with open("chunks.txt", "w") as f:
            f.write("1,1\n")
        return

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    in_start = os.environ.get("START_PAGE", "").strip()
    in_end = os.environ.get("END_PAGE", "").strip()
    chunk_size_str = os.environ.get("CHUNK_SIZE", "30").strip()
    
    chunk_size = int(chunk_size_str) if chunk_size_str.isdigit() else 30
    start_page = int(in_start) if in_start.isdigit() else 1
    end_page = int(in_end) if in_end.isdigit() else total_pages

    if start_page < 1: start_page = 1
    if end_page > total_pages: end_page = total_pages
    if start_page > end_page: start_page = end_page

    chunks = []
    for i in range(start_page, end_page + 1, chunk_size):
        start = i
        end = min(i + chunk_size - 1, end_page)
        chunks.append({"start": start, "end": end})

    print(f"Generated {len(chunks)} chunks from page {start_page} to {end_page}.")
    
    with open("chunks.txt", "w") as f:
        for c in chunks:
            f.write(f"{c['start']},{c['end']}\n")

if __name__ == "__main__":
    main()
