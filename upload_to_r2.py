"""
upload_to_r2.py
===============
Uploads the local `logos/` directory to your Cloudflare R2 bucket using boto3.

Prerequisites:
    pip install boto3 python-dotenv

You must add the following variables to your .env file:
    R2_ACCOUNT_ID="your-cloudflare-account-id"
    R2_ACCESS_KEY_ID="your-r2-access-key-id"
    R2_SECRET_ACCESS_KEY="your-r2-secret-access-key"
    R2_BUCKET_NAME="course-logos" (or whatever you named your bucket)
"""
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGOS_DIR = os.path.join(BASE_DIR, "logos")

def main():
    if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME]):
        print("[ERROR] Missing R2 credentials in .env file.")
        print("Please add R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, and R2_BUCKET_NAME.")
        return

    print(f"[*] Connecting to Cloudflare R2 bucket: {R2_BUCKET_NAME}")
    
    s3 = boto3.client(
        's3',
        endpoint_url=f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name='auto'  # R2 uses 'auto'
    )
    
    if not os.path.exists(LOGOS_DIR):
        print(f"[ERROR] No logos directory found at {LOGOS_DIR}. Please run download_logos.py first.")
        return

    files_to_upload = os.listdir(LOGOS_DIR)
    print(f"[*] Found {len(files_to_upload)} files to upload...")

    success = 0
    for i, filename in enumerate(files_to_upload, 1):
        filepath = os.path.join(LOGOS_DIR, filename)
        if not os.path.isfile(filepath):
            continue
            
        print(f"  [{i}/{len(files_to_upload)}] Uploading {filename}...")
        try:
            # Determine correct content type so browsers display the image correctly
            content_type = 'image/png'
            if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif filename.lower().endswith('.svg'):
                content_type = 'image/svg+xml'
            elif filename.lower().endswith('.webp'):
                content_type = 'image/webp'
                
            s3.upload_file(
                filepath, 
                R2_BUCKET_NAME, 
                f"logos/{filename}", # Stores files under a 'logos/' folder in R2
                ExtraArgs={'ContentType': content_type}
            )
            success += 1
        except Exception as e:
            print(f"    [X] Failed to upload {filename}: {e}")

    print(f"\n[OK] Upload complete! {success} files uploaded.")
    print("If you enabled Public Access in the Cloudflare Dashboard, your logos are now accessible at:")
    print(f"https://<your-public-r2-domain>/logos/<filename>")

if __name__ == "__main__":
    main()
