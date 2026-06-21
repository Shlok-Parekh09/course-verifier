# Free Deployment Options for Course Verifier

## Quick Comparison

| Platform | Cost | RAM | Chrome | Email | Persistent | Best For |
|---|---|---|---|---|---|---|
| **Google Colab** | Free | 12 GB | ✅ | ✅ | Manual save | Immediate run, occasional use |
| **Oracle Cloud** | Free forever | 24 GB | ✅ | ✅ | Full server | Permanent, scheduled runs |
| **GitHub Actions** | Free 2K min/mo | 7 GB | ✅ | ✅ | Artifacts only | CI/CD integration |
| **Render** | $0 / sleeps | 512 MB | ❌ | ❌ | None | Static sites only |
| **Your PC + Tunnel** | $0 | Whatever you have | ✅ | ✅ | Your PC | Testing, local dev |

---

## Recommended: Google Colab (Fastest)

**Zero infrastructure. Open and run today.**

1. Go to https://colab.research.google.com
2. **File → Upload notebook → Select `scripts/colab_setup.py`**
3. Upload `link_compile.pdf` and `.env` to the Files panel (left side)
4. Run cells top to bottom
5. Wait for email!

**Pros:**
- No signup other than Google
- Up to 12 hours per session
- Results auto-saved to Google Drive
- Powerful CPU/GPU available

**Cons:**
- Session may disconnect after ~90 min idle (keep browser open)
- Must re-upload files each session

---

## Recommended: Oracle Cloud Free Tier (Permanent)

**A real Linux server that's free forever.**

1. Sign up at [cloud.oracle.com/free](https://www.oracle.com/cloud/free/)
2. Create an **Ampere A1** instance (VM.Standard.A1.Flex)
3. Set **OCPU = 4**, **Memory = 24 GB** — all free
4. SSH in and run the one-liner:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/Shlok-Parekh09/course-verifier/yug-render-deploy/scripts/oracle_deploy.sh | bash
   ```
5. Upload `link_compile.pdf` and edit `.env`
6. The verifier runs **every Sunday at 2 AM** automatically via cron

**Pros:**
- Truly free forever (no credit card needed for free tier)
- 24 GB RAM = Chrome runs smoothly
- Scheduled weekly runs with email reports
- Full Linux server you control

**Cons:**
- Requires initial setup (~30 minutes)
- Need to upload PDF once to the server

---

## Not Recommended

### Render Free
- Only 512 MB RAM → Chrome crashes
- Sleeps after 15 min idle → verifier gets killed mid-run
- **Skip this.**

### GitHub Pages
- **Static hosting only** — cannot run Python code
- Good for dashboard UI, useless for verifier
- **Skip this for running code.**

---

## Emergency: Run on Your Own PC + Cloudflare Tunnel

If everything else fails, run locally and tunnel out:

```bash
# Install cloudflared
winget install cloudflare.cloudflared

# Start tunnel to your local dashboard
cloudflared tunnel --url http://localhost:5000
```

You'll get a public URL like `https://abc123.trycloudflare.com` that points to your local machine.

---

## My Recommendation

| Your Situation | Choose |
|---|---|
| "I need results TODAY" | **Google Colab** |
| "I want it to run every week automatically" | **Oracle Cloud** |
| "I want to share the dashboard publicly" | **Firebase Hosting** (already set up) |
| "I only have my laptop" | **Your PC + Tunnel** |

---

*Need help with any of these? Open an issue or ask in the discussion.*
