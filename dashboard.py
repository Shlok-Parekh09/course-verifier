import os
import pandas as pd
from flask import Flask, render_template, jsonify

app = Flask(__name__)

DATA_FILE = "AUTONOMOUS_VERIFIED.xlsx"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def api_data():
    if not os.path.exists(DATA_FILE):
        return jsonify({
            "status": "error",
            "message": "Data file not found."
        })
    
    try:
        df = pd.read_excel(DATA_FILE)
        df = df.fillna('')
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Could not read data: {e}"
        })
    
    total_courses = len(df)
    verified = 0
    errors = 0
    discrepancies = 0
    missing_links = 0
    
    recent_verifications = []
    discrepancy_list = []
    
    # Analyze from bottom to top to get the latest
    for idx, row in df.iloc[::-1].iterrows():
        # Check if the row actually has web data processed
        # A good indicator is if Cost (Web) or Duration (Web) is filled, or if Link Working is set
        if row.get('Cost (Web)') == '' and row.get('Duration (Web)') == '' and row.get('Link Working') == '':
            continue
            
        is_hard_error = str(row.get('Link Working', '')) == 'Error'
        
        # Read the Match columns directly from the Excel
        cost_match_val = str(row.get('Cost Match', ''))
        duration_match_val = str(row.get('Duration Match', ''))
        
        cost_match = (cost_match_val == 'MATCH')
        duration_match = (duration_match_val == 'MATCH')
        
        # Calculate overall status
        status_tag = "Open"
        if is_hard_error:
            status_tag = "Error"
            errors += 1
        else:
            if cost_match and duration_match:
                status_tag = "Verified"
                verified += 1
            else:
                status_tag = "Discrepancy"
                discrepancies += 1
                
        # Keep all recent verifications for the UI
        recent_verifications.append({
            "index": row.get('Index', '?'),
            "name": str(row.get('Course Name', 'Unknown')),
            "university": str(row.get('University (PDF)', 'Unknown')),
            "status": status_tag,
            "cost_match": cost_match,
            "duration_match": duration_match
        })
            
        # Add to discrepancy list if needed
        if status_tag == "Discrepancy":
            if not cost_match and not duration_match:
                disc_reason = "Cost & Duration Mismatch"
            elif not cost_match:
                disc_reason = "Cost Mismatch"
            else:
                disc_reason = "Duration Mismatch"
                
            discrepancy_list.append({
                "name": str(row.get('Course Name', 'Unknown')),
                "university": str(row.get('University (PDF)', 'Unknown')),
                "reason": disc_reason
            })

    return jsonify({
        "status": "success",
        "stats": {
            "total": total_courses,
            "verified": verified,
            "discrepancies": discrepancies,
            "errors": errors,
            "missing_links": missing_links
        },
        "recent": recent_verifications,
        "discrepancy_list": discrepancy_list
    })

if __name__ == "__main__":
    print("[*] Starting Live Verification Dashboard on http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
