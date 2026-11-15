# FinQuiz Live: submission note

**Links**
- Host screen (laptop/projector): https://finquizlive.pages.dev/host
- Players (phones): https://finquizlive.pages.dev/ (or scan the QR code on the host screen)
- Code: https://github.com/Kuldip8975/finquiz-live

**What works**
- The full flow from the brief: room code (plus QR), join with code and name, five questions with a 20-second server-side timer, the correct answer and leaderboard on the host after each question, and the final ranking.
- All six rules, each with automated tests: 50 unit tests and 63 end-to-end checks with a host and ten real socket clients. The same 15 requirement checks also pass against the live site.
  - Answers never reach a phone before the question closes.
  - Refresh, app-switching and even a full server restart keep players and scores.
  - Every failure shows a message and a retry button, and phones say so if the teacher's screen closes.
  - gitleaks scans the whole git history in CI.
  - No URL returns names or scores.
- Tested on 5 real phones against the live site. That testing found a real bug: when the host tab was closed, players sat on "Next question coming up…" forever. Phones now say the teacher's screen has disconnected, and the message clears when the host comes back.
- Hardening: rate limits and brute-force protection, strict CSP and HSTS, locked-down containers, pinned and audited dependencies.

**What is not finished**
- The room code is the only key to a room, as the brief describes. Someone in the room who controls many IP addresses could still add fake players. The full fix is a host "remove player" control, which I left out to stay within the brief.
- The host token lives in the browser that created the room. If that projector laptop dies, the teacher cannot take the room over from another device.
- There are no automated database backups and no alerting yet. Games only live for 12 hours, so that risk is small.
- The backend is a single process on one server. That is right for a classroom, but scaling to many rooms would need Redis and sticky sessions.

**AI tools used**
- Claude Code (Anthropic) wrote most of the code, tests, CI and deploy files from my instructions.
- I chose the stack (React + TypeScript, Flask + Socket.IO, PostgreSQL, AWS EC2, Cloudflare). I kept the scope strictly to the brief, asked for security and requirement reviews, set up the AWS and Cloudflare accounts, and tested on 5 phones, which is how the frozen-screen bug was found and fixed.
- I have read and run every part, and I can explain and change any file.

**One thing I'd change with another week**
- Real-device load tests (50+ phones on throttled 3G) plus monitoring: error tracking, uptime checks and nightly Postgres backups to S3.
