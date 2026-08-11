# Deploying Astra

Astra now runs its models on your own hardware. Transcription is Whisper, summarization and
chat are Ollama, embeddings are sentence-transformers, and the vector store is Chroma on disk.
The only external service left is Supabase, which handles sign-in.

## 1. Prerequisites

| Component | Install | Notes |
|---|---|---|
| Python 3.12 | already installed | `requirements.txt` was frozen on 3.13; markers handle the difference |
| FFmpeg | `winget install Gyan.FFmpeg` | Required for every format except WAV, and for YouTube |
| Ollama | already installed (client 0.22.1) | The LLM runtime |

Ollama must be **serving**, not just installed. Launch the Ollama app, or run:

```
ollama serve
```

Confirm with `curl http://localhost:11434/api/tags`. The sidebar Environment panel checks the
same endpoint.

Set `OLLAMA_MODEL` in `.ENV` to whichever you prefer:

| Model | Size | Context | Notes |
|---|---|---|---|
| `mistral:latest` | 7B | 32k | Default. Good balance of quality and speed |
| `gemma2:latest` | 9B | 8k | Better summaries; context maxes out at `OLLAMA_NUM_CTX=8192` |
| `qwen2.5:3b` | 3B | 32k | Fastest, weaker on long meetings |

A GPU is not required, but on CPU expect a few minutes of summarization per hour of meeting.
Whisper `small` is the transcription default; `medium` is meaningfully better for Hinglish and
costs about 3x the time.

## 2. Install

```
pip install -r requirements.txt
```

Copy `.env.example` to `.ENV` and fill in your Supabase URL and anon key. Note the existing
`.ENV` uses the misspellings `SUPERBASE_URL` and `SUPERNASE_ANON_KEY`; the code reads the
correct spellings first and falls back to those, so either works.

## 3. Run locally

```
python run.py
```

This starts the auth server, starts Streamlit headless, and opens the login page. The sidebar
Environment panel tells you whether Ollama is reachable and whether your model is pulled.

## 4. Expose it to the internet

Two services need to be reachable: the auth pages on 8001 and the workspace on 8501. The
cleanest arrangement puts both behind **one hostname** with path routing, so the browser sees
a single origin and the Supabase session in localStorage stays consistent across login,
workspace, and logout.

### Option A — Cloudflare Tunnel (recommended)

No port forwarding, no firewall holes, no static IP, and TLS is handled for you. Your machine
makes an outbound connection only.

```
winget install Cloudflare.cloudflared
cloudflared tunnel login
cloudflared tunnel create astra
```

Then in `%USERPROFILE%\.cloudflared\config.yml`:

```yaml
tunnel: astra
credentials-file: C:\Users\sujal\.cloudflared\<tunnel-id>.json

ingress:
  - hostname: astra.example.com
    path: ^/(html|css|assets)/.*|^/auth-config\.js$
    service: http://localhost:8001
  - hostname: astra.example.com
    service: http://localhost:8501
  - service: http_status:404
```

Route DNS and start it:

```
cloudflared tunnel route dns astra astra.example.com
cloudflared tunnel run astra
```

Then set these in `.ENV` so every generated link uses the public origin:

```
ASTRA_AUTH_URL=https://astra.example.com
ASTRA_APP_URL=https://astra.example.com
ASTRA_OPEN_BROWSER=0
```

Leave `ASTRA_AUTH_BIND` and `ASTRA_APP_BIND` at `127.0.0.1`. The tunnel reaches them on
loopback, and nothing is exposed on your LAN.

**Be aware:** this does put Cloudflare in the request path, which is a compromise against
"no cloud". Traffic is terminated at their edge. Option B avoids that entirely.

### Option B — Port forward from your own router

Fully self-hosted, nothing in the path but your hardware.

1. Set `ASTRA_AUTH_BIND=0.0.0.0` and `ASTRA_APP_BIND=0.0.0.0`.
2. Forward external 443 to a local reverse proxy (Caddy is simplest) that does the same path
   split as the ingress rules above.
3. Get a certificate — Caddy will fetch one from Let's Encrypt automatically given a domain.
4. Use dynamic DNS if your ISP rotates your IP.
5. Add Windows Firewall rules for the proxy port only.

The tradeoffs versus Option A: your home IP is public, you own the TLS renewal, and you are
directly exposed to internet background scanning. Do not skip the reverse proxy and expose
8501 raw — Streamlit is not built to be an edge server.

## 5. Point Supabase at the public URL

In the Supabase dashboard, **Authentication → URL Configuration**:

- Set **Site URL** to `https://astra.example.com`
- Add `https://astra.example.com/html/login.html` and
  `https://astra.example.com/html/signup.html` to **Redirect URLs**

Google sign-in reads `redirectTo` from the current page URL, so it starts working as soon as
those entries exist. Without them Supabase rejects the OAuth callback.

Also turn **email confirmation on** before going public, or anyone can create an account with
an address they do not own.

## 6. Start on boot

Task Scheduler, "Create Task":

- Trigger: At startup
- Action: Start a program — `pythonw.exe`, arguments `run.py`, start in the project directory
- Check "Run whether user is logged on or not"

Add a second task the same way for `cloudflared tunnel run astra`.

## 7. Capacity

Everything runs in one process on one machine, so be realistic about load:

- Whisper holds one model in memory as a module-level singleton, and Streamlit is
  single-process. **Two people transcribing at once will serialize**, and each holds a full
  recording in memory during conversion.
- Ollama queues requests. A long meeting fires one LLM call per 3000-character chunk for the
  summary and each of the three extractors, so a two-hour meeting is dozens of sequential
  calls.

This is comfortable for a handful of colleagues. It is not sized for open public signup — if
you publish the URL widely, put the signup behind an invite or an allowlist first.
