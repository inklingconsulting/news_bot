# Hosting the bots on GCP (free-tier VM)

Runs the always-on Telegram bots on one small Compute Engine VM, each as a
`systemd` service (systemd is the cloud replacement for Windows Task Scheduler —
it auto-starts on boot and restarts a bot if it crashes).

- **VM:** `e2-micro` — free-tier eligible in `us-west1`, `us-central1`, `us-east1`.
- **Secrets:** GCP Secret Manager (never committed; fetched onto the VM at boot).
- **Deploy:** the VM's startup script (`bootstrap.sh`) clones this repo, installs
  deps, writes `.env` from Secret Manager, and starts the service. Re-running it
  redeploys.

Project in these commands: `inklingmedicare`. Run from the repo root.

---

## One-time setup

### 1. Enable the APIs
```bash
gcloud services enable compute.googleapis.com secretmanager.googleapis.com
```

### 2. Push your secrets (reads your local .env)
```bash
bash deploy/push-secrets.sh
```

### 3. Let the VM read secrets (grant its service account)
```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${PROJECT_NUM}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### 4. Create the VM (this is the step that runs everything)
```bash
gcloud compute instances create bots \
  --zone=us-east1-b \
  --machine-type=e2-micro \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=30GB --boot-disk-type=pd-standard \
  --scopes=cloud-platform \
  --metadata-from-file=startup-script=deploy/bootstrap.sh
```

### 5. Verify (give it ~2 min to boot + install)
```bash
gcloud compute ssh bots --zone=us-east1-b \
  --command="sudo systemctl status news_bot --no-pager -l | head -20; \
             echo '--- logs ---'; sudo journalctl -u news_bot -n 30 --no-pager"
```
You should see `active (running)` and the bot's startup log.

> ⚠️ **Stop the PC copy.** Telegram allows only one poller per bot token — if
> `python bot.py` is still running on your PC while the VM runs it, you'll get
> `409 Conflict` errors. Stop the PC instance once the VM is live.

---

## Updating after a code change
Push to GitHub, then redeploy on the VM:
```bash
gcloud compute ssh bots --zone=us-east1-b \
  --command="cd /opt/bots/news_bot && sudo -u botrunner git pull --ff-only && sudo systemctl restart news_bot"
```
(If you changed secrets, re-run `push-secrets.sh`, then re-run the whole startup
script: `sudo google_metadata_script_runner startup`, then restart the service.)

---

## Adding another bot (Talk Bot, Trading Agents, Life Organizer, …)
The pattern repeats. For a bot in repo `inklingconsulting/<bot>`:

1. **Secrets:** push its keys as `<bot>-<key>` (mirror `push-secrets.sh`).
2. **Service unit:** add `/etc/systemd/system/<bot>.service` (copy `news_bot.service`,
   change `Description`, `WorkingDirectory`, and `ExecStart` to that repo's entry point).
3. **Provision block:** add a clone+venv+`.env`+`systemctl enable --now` block to
   `bootstrap.sh` for that repo (or drop a small per-bot script in `deploy/`).

Each bot is ~100 MB of RAM, so 3–4 light bots fit on the `e2-micro`. If `free -m`
on the VM shows it's tight, resize once to `e2-small` (~$13/mo):
```bash
gcloud compute instances stop bots --zone=us-east1-b
gcloud compute instances set-machine-type bots --zone=us-east1-b --machine-type=e2-small
gcloud compute instances start bots --zone=us-east1-b
```

### Brain Dump — the Whisper caveat
Brain Dump transcribes voice notes with **Whisper running locally**. That won't fit
on a 1 GB `e2-micro`. Before moving it, switch its transcription step to a **hosted
API** — OpenAI Whisper (`~$0.006/min`), Google Speech-to-Text, or Deepgram — so the
VM only does the light orchestration. After that change it deploys like any other bot.
(That edit lives in the `brain_dump` repo, not here.)
