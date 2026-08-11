# Deploying Astra

Astra now runs its models on your own hardware. Transcription is Whisper, summarization and
chat are Ollama, embeddings are sentence-transformers, and the vector store is Chroma on disk.
The only external service left is Supabase, which handles sign-in.

## 1. Prerequisites

| Component | Install | Notes |
|---|---|---|
| Python 3.14 | already installed | |
| FFmpeg | `winget install Gyan.FFmpeg` | Required for every format except WAV, and for YouTube |
| Ollama | already installed | The LLM runtime |
| Deno | `winget install DenoLand.Deno` | yt-dlp uses it to solve YouTube's JS challenges |

Ollama must be **serving**, not just installed. Launch the Ollama app, or run:

```
ollama serve
```

Confirm with `curl http://localhost:11434/api/tags`. The sidebar Environment panel checks the
same endpoint.

The model is `qwen2.5:3b`, set by `OLLAMA_MODEL`. At 3B it fits in about 3 GB of RAM and stays
responsive on CPU, which is what makes an always-on self-hosted demo practical — a 7B model
would leave a visitor waiting minutes per summary. Its context window is 32k, so
`OLLAMA_NUM_CTX=8192` has plenty of headroom.

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

## 4. Go public with no domain and no account

```
.\venv\Scripts\python.exe publish.py
```

Use the venv interpreter, not the bare `python` on PATH — that one is a different 3.12 install
without the dependencies. `publish.py` launches Streamlit with `sys.executable`, so whichever
Python starts it is the one that runs the app.

That is the whole thing. It starts Caddy, opens a Cloudflare quick tunnel, reads the URL
Cloudflare hands back, feeds it into `ASTRA_AUTH_URL`/`ASTRA_APP_URL`, then starts the auth
server and Streamlit behind it. It prints the live URL and takes everything down on Ctrl+C.

Prerequisites, both free and already installed on this machine:

```
winget install CaddyServer.Caddy
winget install Cloudflare.cloudflared
```

### Why Caddy is in the picture

Astra runs two servers — auth pages on 8001, workspace on 8501 — but a free tunnel gives you
exactly one URL. `Caddyfile` merges them onto port 8080: `/html/*`, `/css/*`, `/assets/*` and
`/auth-config.js` go to the auth server, everything else goes to Streamlit. Caddy also upgrades
the WebSocket that Streamlit's `/_stcore/stream` needs, which a naive proxy would drop.

### What you give up

The quick-tunnel URL is random and **changes every restart**. `publish.py` handles that for
Astra itself, but not for Supabase:

- **`/?demo=1` works immediately.** No auth, no configuration. This is the link to send.
- **Email and password sign-in works immediately.** Supabase does not check the origin for it.
- **Google sign-in does not**, until you add the current URL to Supabase redirect URLs — and
  it breaks again on the next restart.

For a URL that survives restarts you need a named tunnel, which needs a domain on Cloudflare.
Section 5 covers that; until then, lead recruiters to the demo link.

## 5. A permanent URL, once you have a domain

Inference stays on this machine; the tunnel only carries HTTP. No port forwarding, no firewall
holes, no static IP, no exposed home address — your machine makes an outbound connection only,
and TLS terminates at Cloudflare's edge.

Two services need to be reachable: the auth pages on 8001 and the workspace on 8501. Both go
behind **one hostname** with path routing, so the browser sees a single origin and the Supabase
session in localStorage stays consistent across login, workspace, and logout.

### You need a domain on Cloudflare

A **named** tunnel requires a domain whose nameservers point at Cloudflare. This matters
because the alternative — a quick tunnel — hands you a random `*.trycloudflare.com` URL that
**changes every restart**. A URL on a CV or a portfolio has to be stable, so buy a cheap
domain and add it to Cloudflare (free plan) before starting.

Use quick tunnels (`cloudflared tunnel --url http://localhost:8501`) for a one-off share only.

### Set up the tunnel

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

Cloudflare does sit in the request path and terminates TLS. The models and every recording
still stay on this machine.

### Alternative: port forward from your own router

Only if you want nothing but your own hardware in the path. Set both binds to `0.0.0.0`,
forward external 443 to a local Caddy doing the same path split, let Caddy fetch a Let's
Encrypt certificate, and add dynamic DNS if your ISP rotates your IP. The costs: your home IP
becomes public, you own TLS renewal, and you take internet background scanning directly. Do
not skip the reverse proxy and expose 8501 raw — Streamlit is not built to be an edge server.

## 6. Point Supabase at the public URL

In the Supabase dashboard, **Authentication → URL Configuration**:

- Set **Site URL** to `https://astra.example.com`
- Add `https://astra.example.com/html/login.html` and
  `https://astra.example.com/html/signup.html` to **Redirect URLs**

Google sign-in reads `redirectTo` from the current page URL, so it starts working as soon as
those entries exist. Without them Supabase rejects the OAuth callback.

Also turn **email confirmation on** before going public, or anyone can create an account with
an address they do not own.

## 7. Keep it running

The link is only as good as this machine's uptime. Four things to set:

**Never sleep.** A sleeping laptop is a dead link. Control Panel → Power Options → set sleep
and hibernate to Never on AC, and disable "USB selective suspend" if the machine drops network
on idle.

```
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

**Start Astra on boot.** Task Scheduler → Create Task:

- Trigger: At startup
- Action: Start a program — `pythonw.exe`, arguments `run.py`, start in the project directory
- Check "Run whether user is logged on or not"

**Install the tunnel as a Windows service** so it restarts with the machine and recovers on its
own — better than a second scheduled task:

```
cloudflared service install
```

**Let Ollama autostart.** The desktop app does this by default; confirm it survives a reboot
with `curl http://localhost:11434/api/tags`.

## 8. Capacity and abuse

Everything runs in one process on one machine, so be realistic:

- faster-whisper holds one model as a module-level singleton and Streamlit is single-process,
  so **two people transcribing at once will serialize**.
- Ollama queues requests. `qwen2.5:3b` keeps each call fast, and `meeting_analysis.py` does a
  single JSON pass per transcript chunk rather than one call per section, but a long meeting
  is still a sequence of calls.

A public URL means strangers can spend your CPU. Before sharing it widely:

- Turn **email confirmation on** in Supabase so signups need a real address.
- Consider an allowlist — check the signed-in email against a list before rendering the
  workspace — if you only want specific people running transcriptions.
- Keep an eye on `downloads/`; failed runs can leave files behind.
