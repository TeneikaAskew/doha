# Deployment Guide

## Deploy to Streamlit Community Cloud (Recommended - FREE)

Streamlit Community Cloud is the easiest way to deploy and share your Streamlit app publicly.

### Prerequisites

1. GitHub account
2. This code pushed to a GitHub repository
3. Gemini API key (for LLM analysis features)

### Step-by-Step Deployment

#### 1. Push Code to GitHub

If not already done:

```bash
cd /workspaces/doha
git add .
git commit -m "Add Streamlit demo UI for SEAD-4 analyzer"
git push origin main
```

#### 2. Sign Up for Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "Sign up" and connect your GitHub account
3. Authorize Streamlit to access your repositories

#### 3. Deploy Your App

1. Click "New app" button
2. Select your repository: `your-username/doha`
3. Set the branch: `main`
4. Set the main file path: `sead4_llm/demo_ui.py`
5. Click "Deploy!"

#### 4. Configure Secrets (API Keys)

After deployment, add your API key:

1. Go to your app settings (three dots menu → Settings)
2. Click on "Secrets" in the left sidebar
3. Add your secrets in TOML format:

```toml
GEMINI_API_KEY = "your-actual-api-key-here"
```

4. Click "Save"
5. Your app will automatically restart with the new secrets

#### 5. Access Your App

Your app will be available at:
```
https://share.streamlit.io/[username]/[repo-name]/[branch]/sead4_llm/demo_ui.py
```

Or a shorter custom URL like:
```
https://[your-app-name].streamlit.app
```

### Important Notes

**File Paths:**
- The app expects `test_reports/` directory with PDF files
- Make sure your test PDFs are committed to the repository (or uploaded via Streamlit's file uploader)
- The `llm_cache/` directory with cached responses is included

**Resource Limits (Free Tier):**
- 1 GB RAM
- 1 CPU core
- Sleeping after inactivity (wakes up when accessed)
- Public apps only

**Privacy:**
- The free tier only supports public apps
- Don't commit sensitive API keys to git (use Streamlit secrets)
- Test reports in the repo will be publicly visible

---

## Alternative Deployment Options

### Option 2: Hugging Face Spaces (Free)

1. Create account at [huggingface.co](https://huggingface.co)
2. Create new Space → Select "Streamlit"
3. Upload your code or connect GitHub repo
4. Add secrets in Settings → Variables and secrets
5. App automatically deploys

### Option 3: Local Network (Quick Share)

For temporary sharing on your local network:

```bash
cd /workspaces/doha/sead4_llm
streamlit run demo_ui.py --server.address 0.0.0.0 --server.port 8501
```

Then share your local IP address: `http://[your-ip]:8501`

### Option 4: Docker Deployment

Create a `Dockerfile` in `sead4_llm/`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "demo_ui.py", "--server.address", "0.0.0.0"]
```

Build and run:

```bash
docker build -t sead4-demo .
docker run -p 8501:8501 -e GEMINI_API_KEY=your_key sead4-demo
```

Deploy the container to:
- AWS ECS/Fargate
- Google Cloud Run
- Azure Container Instances
- DigitalOcean App Platform

---

## Troubleshooting

### App won't start on Streamlit Cloud

**Check logs** in the Streamlit Cloud dashboard:
- Python version compatibility (requires Python 3.11+)
- Missing dependencies in requirements.txt
- File path issues

### "GEMINI_API_KEY not set" error

- Add the key to Streamlit Cloud secrets (not in .env file)
- Format: `GEMINI_API_KEY = "your-key"` in TOML format
- Restart the app after adding secrets

### PDF files not found

- Ensure `test_reports/` directory is in the repository
- Check the file path in demo_ui.py matches your structure
- Streamlit Cloud reads from the git repository, not local filesystem

### Out of memory errors

Streamlit Community Cloud has 1GB RAM limit:
- Use `use_embeddings=False` for EnhancedNativeSEAD4Analyzer
- Process fewer documents at once
- Consider upgrading to paid tier or alternative hosting

---

## Production Considerations

For production deployment:

1. **Authentication:** Add login system (Streamlit doesn't have built-in auth on free tier)
2. **Rate Limiting:** Implement API rate limiting to control costs
3. **Error Handling:** Add comprehensive error handling and user feedback
4. **Monitoring:** Set up logging and monitoring (Sentry, DataDog, etc.)
5. **Caching:** Use `@st.cache_data` for expensive operations
6. **Database:** Store results in database instead of JSON files
7. **Queue System:** Use task queue (Celery, Redis) for long-running analyses

---

## Cost Estimation

**Streamlit Community Cloud:**
- Hosting: FREE (with limitations)
- Gemini API: ~$0.02 per analysis
- 100 analyses/day = ~$2/day = ~$60/month

**Paid Hosting (for production):**
- Streamlit Cloud Teams: $250/month (private apps, more resources)
- AWS/GCP/Azure: $20-100/month depending on traffic
- Gemini API costs remain the same

---

## Support

- Streamlit Docs: [docs.streamlit.io](https://docs.streamlit.io)
- Streamlit Community: [discuss.streamlit.io](https://discuss.streamlit.io)
- Deployment Issues: Check app logs in Streamlit Cloud dashboard
