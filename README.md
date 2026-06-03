# FOMO Firewall

A pre-trade cooling assistant for crypto beginners, built for the SoSoValue Buildathon.

## Buildathon submission snapshot

**One-liner:** FOMO Firewall is an AI-style pre-trade risk gate that turns a crypto impulse into SoSoValue-backed evidence, counter-evidence, execution checks, and a saved decision receipt.

**Target user:** crypto beginners and curious traders who are tempted to chase coins before they have a clear plan.

**Demo flow:** the app opens with a BTC analysis by default. Search any ticker or coin name, review the SoSoValue market evidence, complete the execution gate, then save the pre-trade receipt for later review.

**SoSoValue API usage:** currency discovery, market snapshot, daily K-line data, and related news search are used through the local Python proxy. The frontend shows live/demo/unavailable mode, evidence strength, data coverage, generated time, and direct SoSoValue coin links.

**Safety position:** this is a cooling and research assistant, not financial advice or an auto-trading bot.

The demo helps a user pause before chasing a crypto move. It turns a thought like
`SOL is up 12% today. Should I buy before I miss it?` into a FOMO score, market
evidence, counter-evidence, cooling actions, and a decision receipt.

Users do not need to select a coin manually. The app detects the ticker or asset
name from the text, then uses the detected asset for SoSoValue API lookups.
If no local alias or SoSoValue currency match is found, the app stops and shows
an "asset not found" state instead of fabricating a market report.

The search box updates automatically while the user types. Live mode uses
SoSoValue for current price, 24h change, 24h volume, market cap, market-cap rank,
daily K-line data, and related news. The FOMO report is generated from those live
fields rather than fixed text templates.

For responsiveness, the local proxy caches the SoSoValue currency list for 15
minutes, market snapshots for 20 seconds, and news search results for 60 seconds.
The frontend also cancels stale in-flight searches so older slow responses cannot
overwrite the latest input.

The report adapts to the user profile:

- Beginner: short, plain-language cooling card.
- Crypto curious: medium-depth evidence and counter-evidence.
- Active trader: deeper evidence, invalidation risks, and execution guardrails.

The current product layer also includes:

- Default BTC analysis on page load so judges can see the core workflow immediately.
- Live/demo/unavailable data mode status, generated time, and a clear non-financial-advice note.
- FOMO trigger detection, such as price chase, dip bargain, news FOMO, social FOMO, urgency, and revenge trading.
- A transparent score breakdown showing which factors added to the FOMO score.
- A final decision card: cool down, watch only, or plan first, with three short reasons.
- An execution gate that checks amount, holding time, stop loss, take profit, and invalidation before action.
- A 14-day K-line trend chart from SoSoValue daily K-line data.
- Search suggestions from the SoSoValue currency list.
- Data coverage pills showing whether price, volume, market cap, news, and K-line data were available.
- A SoSoValue evidence card showing endpoints, live fields, evidence strength, generated time, and direct source links.
- Direct links to the matched SoSoValue coin page.
- Local pre-trade receipts saved in the browser, with a full history view and personal FOMO profile for the latest 100 records.

## GitHub and judge setup notes

This repository can be uploaded to GitHub as-is, but live SoSoValue data requires a local API key setup.

- Do not commit `.env`. Keep only `.env.example` in the repository.
- Judges can open `index.html` directly for a static demo, but live market data will not be available in that mode.
- For live mode, judges need Python and their own SoSoValue API key.
- After adding `SOSO_API_KEY` to `.env`, run `python server.py` and open `http://127.0.0.1:8000`.
- If no API key is configured, or an endpoint is unavailable, the app shows `Unavailable` instead of fake live prices.

## Run the static demo

Open `index.html` in a browser. This uses built-in demo data.

## Run with the local API proxy

1. Copy `.env.example` to `.env`.
2. Put your SoSoValue API key in `.env`:

```env
SOSO_API_KEY=your_key_here
PORT=8000
```

3. Start the local server:

```bash
python server.py
```

On Windows, you can also double-click or run:

```bat
run_server.bat
```

4. Open `http://127.0.0.1:8000`.

## API safety

SoSoValue requires this request header:

```http
x-soso-api-key: Your API Key
```

The key should stay in `.env` and be used only by `server.py`. Do not put the key
inside `index.html` or `app.js`, because browser code is visible to users.
